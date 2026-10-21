"""Cost-vs-quality test: the same applicants under different model / effort settings.

Usage:  python scripts/compare_models.py            (runs configs B, C, D; A = existing baseline runs)
Writes logs/model_comparison.json. Real API calls: about $1-1.50 in total.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cabaka import config, pipeline  # noqa: E402

APPLICANTS = ["maria_bronx", "dale_pike", "kwame_staten", "tina_steuben"]
CONFIGS = {
    "B: Opus 5.5 · medium": ("claude-opus-5-5", "medium"),
    "C: Sonnet 5.5 · low": ("claude-sonnet-5-5", "low"),
    "D: Haiku 5.5 · low (all agents)": ("claude-haiku-5-5", "low"),
}
OUT = config.LOG_DIR / "model_comparison.json"


def summarize(label, run):
    res = run.get("result") or {}
    offers = res.get("offers", {})
    rec = next((o for o in offers.get("offers", []) if o.get("name") == offers.get("recommended_offer_name")), {})
    return {
        "config": label, "applicant": run["applicant_id"], "run_id": run["id"], "status": run["status"],
        "error": run.get("error"),
        "final": res.get("status"),
        "needed_repair": any(e["agent"] == "Verifier" and e["kind"] == "security" for e in run["events"]),
        "failed_checks": [c["check"] for c in res.get("hard_checks", []) if not c["passed"]],
        "recommended_type": rec.get("type"), "recommended_payment": rec.get("monthly_payment"),
        "tool_calls": sum(1 for e in run["events"] if e["kind"] == "tool_call"),
        **run["totals"],
    }


def baseline():
    """Config A = the most recent Opus-low run per applicant already in logs/runs."""
    rows = {}
    for p in sorted(pipeline.RUN_DIR.glob("*.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        models = {u["model"] for a, u in (r.get("usage") or {}).items() if a != "Gatekeeper"}
        if r["applicant_id"] in APPLICANTS and models == {"claude-opus-5-5"} and r.get("result"):
            rows[r["applicant_id"]] = summarize("A: Opus 5.5 · low (default)", r)
    return [rows[a] for a in APPLICANTS if a in rows]


def main():
    rows = baseline()
    for label, (model, effort) in CONFIGS.items():
        config.MAIN_MODEL, config.MAIN_EFFORT = model, effort
        for aid in APPLICANTS:
            rid = pipeline.new_run(aid)
            print(f"{label} · {aid} ...", flush=True)
            pipeline.execute(rid)
            rows.append(summarize(label, pipeline.RUNS[rid]))
            print("  ", json.dumps({k: rows[-1][k] for k in ("final", "needed_repair", "recommended_type", "cost_usd", "seconds")}), flush=True)
            OUT.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    print("->", OUT)


if __name__ == "__main__":
    main()
