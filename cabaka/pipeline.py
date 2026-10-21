"""Orchestrator: Gatekeeper -> Underwriter -> Offer Architect -> Compliance, then hard checks."""
import json
import time
import traceback
import uuid

from . import agents as A
from . import config, safety
from .data import get_applicant
from .llm import RunContext, run_agent, run_json
from .tools import amortize, analyze_cash_flow

RUNS: dict[str, dict] = {}   # in-memory state the UI polls
RUN_DIR = config.LOG_DIR / "runs"
RUN_DIR.mkdir(exist_ok=True)


def applicant_brief(a: dict, notes: str) -> str:
    """The structured file every agent receives (notes are wrapped as untrusted)."""
    file = {k: v for k, v in a.items() if k not in ("notes",)}
    return (f"Applicant file (JSON):\n{json.dumps(file, indent=1)}\n\n"
            f"<applicant_notes>\n{notes}\n</applicant_notes>")


def new_run(applicant_id: str, notes_override: str | None = None) -> str:
    run_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    RUNS[run_id] = {"id": run_id, "applicant_id": applicant_id, "status": "running",
                    "config": {"main_model": config.MAIN_MODEL, "effort": config.MAIN_EFFORT,
                               "guard_model": config.GUARD_MODEL},
                    "events": [], "result": None, "error": None, "notes_override": notes_override}
    return run_id


def execute(run_id: str):
    run = RUNS[run_id]
    a = get_applicant(run["applicant_id"])
    product = a["product"]
    ctx = RunContext(run_id, a["id"])
    run["events"] = ctx.events          # shared list, so the UI sees events live
    run["usage"] = ctx.usage_by_agent
    notes = (run["notes_override"] if run["notes_override"] is not None else a.get("notes", ""))
    notes = notes[: config.MAX_NOTE_CHARS]
    ctx.tool_facts.append({k: v for k, v in a.items() if k != "notes"})  # notes are untrusted, not facts
    try:
        # 1. Gatekeeper: regex screen + cheap model screen of the free text.
        pre = safety.prefilter(notes)
        if pre["flagged"]:
            ctx.emit("Gatekeeper", "security", message="Regex pre-filter flagged the notes.",
                     patterns=pre["matched_patterns"])
        screen = run_json(ctx, "Gatekeeper", system=A.GATEKEEPER_SYSTEM,
                          user=f"<applicant_notes>\n{notes}\n</applicant_notes>",
                          schema=A.GATEKEEPER_SCHEMA, model=config.GUARD_MODEL)
        if pre["flagged"] or screen["injection_detected"] or screen["risk_level"] == "high":
            notes = f"[Original notes withheld by Gatekeeper: possible prompt injection.] {screen['safe_summary']}"
            ctx.emit("Gatekeeper", "security", message="Prompt injection blocked. Downstream agents only "
                     "see the neutral summary.", reasons=screen["reasons"])
        brief = applicant_brief(a, notes)

        # 2. Underwriter
        uw = run_agent(ctx, "Underwriter", system=A.underwriter_system(product),
                       user=brief + f"\n\nUnderwrite this {A.PRODUCTS[product]['label'].lower()} application.",
                       tools=A.tools_for(A.PRODUCTS[product]["underwriter_tools"], A.SUBMIT_UNDERWRITING),
                       final_tool="submit_underwriting")

        # 3. Offer Architect
        offers = run_agent(ctx, "Offer Architect", system=A.offer_system(product),
                           user=brief + "\n\nUnderwriting findings:\n" + json.dumps(uw, indent=1),
                           tools=A.tools_for(A.PRODUCTS[product]["offer_tools"], A.SUBMIT_OFFERS),
                           final_tool="submit_offers")

        # 4. Compliance & Explainer (+ one repair round if the hard checks fail)
        comp_user = (brief + "\n\nUnderwriting:\n" + json.dumps(uw, indent=1) +
                     "\n\nOffers:\n" + json.dumps(offers, indent=1))
        review = run_agent(ctx, "Compliance", system=A.compliance_system(product), user=comp_user,
                           tools=[A.SUBMIT_REVIEW], final_tool="submit_review")
        cash = analyze_cash_flow(a["id"])
        checks = safety.verify_plan(product, cash, uw, offers, review, ctx.tool_facts, amortize)
        failed = [c for c in checks if not c["passed"]]
        if failed:
            ctx.emit("Verifier", "security", message="Hard checks failed; sending back for one repair.",
                     failed=failed)
            review = run_agent(ctx, "Compliance", system=A.compliance_system(product),
                               user=comp_user + "\n\nYour previous review failed these automatic checks. "
                               "Fix the letter so every number comes from the data above:\n" + json.dumps(failed),
                               tools=[A.SUBMIT_REVIEW], final_tool="submit_review")
            checks = safety.verify_plan(product, cash, uw, offers, review, ctx.tool_facts, amortize)
        ok = all(c["passed"] for c in checks)
        ctx.emit("Verifier", "final", output={"all_passed": ok, "checks": checks})

        run["result"] = {
            "product": product, "applicant": {k: a[k] for k in ("id", "name", "location", "product")},
            "gatekeeper": screen, "underwriting": uw, "offers": offers, "review": review,
            "hard_checks": checks, "status": "ready_for_officer" if ok else "needs_human_review",
            "cash_flow": cash,
        }
        run["status"] = "done"
    except safety.BudgetExceeded as e:
        ctx.emit("Budget guard", "security", message=str(e))
        run["status"], run["error"] = "stopped", str(e)
    except Exception as e:  # noqa: BLE001 - surface any failure to the UI instead of crashing
        ctx.emit("System", "error", message=f"{type(e).__name__}: {e}")
        run["status"], run["error"] = "error", f"{type(e).__name__}: {e}"
        traceback.print_exc()
    finally:
        totals = {k: sum(u[k] for u in ctx.usage_by_agent.values())
                  for k in ("input", "output", "cache_read", "cache_write", "cost_usd")}
        run["totals"] = {**totals, "cost_usd": round(totals["cost_usd"], 5),
                         "seconds": round(time.time() - ctx.started, 1)}
        (RUN_DIR / f"{run_id}.json").write_text(json.dumps(run, indent=1, default=str), encoding="utf-8")
