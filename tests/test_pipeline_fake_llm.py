"""Drives the full pipeline with a scripted fake Claude client (no API key, no cost).

Checks the orchestration: tool dispatch, the applicant lock, injection blocking,
the verifier and token accounting.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cabaka import config, llm, pipeline, safety  # noqa: E402

USAGE = NS(input_tokens=100, output_tokens=50, cache_read_input_tokens=400, cache_creation_input_tokens=0)


def text(t):
    return NS(type="text", text=t)


def tool(name, args, i):
    return NS(type="tool_use", name=name, input=args, id=f"tu_{i}")


def resp(*blocks, stop="tool_use"):
    return NS(content=list(blocks), usage=USAGE, stop_reason=stop)


class FakeMessages:
    def __init__(self):
        self.calls = 0

    def create(self, **kw):
        self.calls += 1
        sys_text = kw["system"] if isinstance(kw["system"], str) else kw["system"][0]["text"]
        n = len(kw["messages"])
        if "screen free-text" in sys_text:
            injected = "SYSTEM OVERRIDE" in kw["messages"][0]["content"]
            return resp(text(json.dumps({"injection_detected": injected, "risk_level": "high" if injected else "none",
                                         "reasons": ["asks to ignore rules"] if injected else [],
                                         "safe_summary": "Patient needs surgery."})), stop="end_turn")
        if "UNDERWRITER" in sys_text:
            if n == 1:  # also tries to read another applicant's file: must be blocked
                return resp(tool("analyze_cash_flow", {"applicant_id": "maria_bronx"}, 1),
                            tool("get_credit_report", {"applicant_id": "tina_steuben"}, 2))
            return resp(tool("submit_underwriting", {"decision_recommendation": "offer", "risk_tier": "B",
                        "max_affordable_monthly_payment": 300, "key_findings": ["ok"], "rationale": "ok"}, 3))
        if "OFFER ARCHITECT" in sys_text:
            if n == 1:
                return resp(tool("amortize", {"principal": 4300, "apr_pct": 8, "months": 24}, 4))
            return resp(tool("submit_offers", {"recommended_offer_name": "Cabaka plan", "why": "affordable",
                        "offers": [{"name": "Cabaka plan", "type": "cabaka_installment", "principal": 4300,
                                    "apr_pct": 8, "months": 24, "monthly_payment": 194.48, "total_cost": 4667.52,
                                    "pros": "low", "cons": "interest"}]}, 5))
        if "COMPLIANCE" in sys_text:
            return resp(tool("submit_review", {"policy_checks": [], "approved_for_borrower": True,
                        "borrower_letter": "Your plan is $194.48 per month at 8% APR for 24 months.",
                        "officer_summary": "Affordable."}, 6))
        raise AssertionError("unexpected agent")


def run_with_fake(monkeypatch, tmp_path, applicant):
    fake = NS(messages=FakeMessages())
    monkeypatch.setattr(llm, "client", lambda: fake)
    monkeypatch.setattr(safety, "LEDGER", tmp_path / "usage.jsonl")
    monkeypatch.setattr(pipeline, "RUN_DIR", tmp_path)
    rid = pipeline.new_run(applicant)
    pipeline.execute(rid)
    return pipeline.RUNS[rid]


def test_full_pipeline_with_injection(monkeypatch, tmp_path):
    run = run_with_fake(monkeypatch, tmp_path, "jordan_test")
    assert run["status"] == "done", run["error"]
    sec = [e["message"] for e in run["events"] if e["kind"] == "security"]
    assert any("Prompt injection blocked" in m for m in sec)
    assert any("another applicant" in m for m in sec)
    assert run["result"]["status"] == "ready_for_officer"
    assert run["totals"]["cache_read"] > 0 and run["totals"]["cost_usd"] > 0


def test_invented_number_goes_to_human_review(monkeypatch, tmp_path):
    orig = FakeMessages.create

    def lying(self, **kw):
        r = orig(self, **kw)
        for b in r.content:
            if getattr(b, "name", "") == "submit_review":
                b.input = {**b.input, "borrower_letter": "Great news: only $99 per month at 2% APR!"}
        return r
    monkeypatch.setattr(FakeMessages, "create", lying)
    run = run_with_fake(monkeypatch, tmp_path, "maria_bronx")
    assert run["result"]["status"] == "needs_human_review"
    failed = [c["check"] for c in run["result"]["hard_checks"] if not c["passed"]]
    assert "Every number in the letter traces to a tool" in failed


def test_loop_guard_stops_runaway_agent(monkeypatch, tmp_path):
    def chatty(self, **kw):
        return resp(text("Thinking more..."), stop="end_turn")
    monkeypatch.setattr(FakeMessages, "create", chatty)
    monkeypatch.setattr(config, "MAX_TOOL_TURNS", 3)
    run = run_with_fake(monkeypatch, tmp_path, "maria_bronx")
    assert run["status"] == "error"
