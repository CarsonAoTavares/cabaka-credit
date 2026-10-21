"""Offline tests (no API key needed):  python -m pytest -q"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cabaka import config, safety, tools  # noqa: E402
from cabaka.llm import RunContext, run_tool  # noqa: E402


# ------------------------------------------------------------- calculators

def test_amortize_matches_textbook_formula():
    r = tools.amortize(10000, 6, 60)  # standard textbook case: $193.33/month
    assert r["monthly_payment"] == pytest.approx(193.33, abs=0.01)


def test_zero_apr_is_simple_division():
    assert tools.amortize(1200, 0, 12)["monthly_payment"] == 100


def test_deferred_interest_trap_triggers_when_payment_too_small():
    r = tools.simulate_deferred_interest_card(6800, 450)
    assert not r["paid_off_in_promo"] and r["retroactive_interest_charged"] > 1500


def test_deferred_interest_no_penalty_when_paid_in_promo():
    r = tools.simulate_deferred_interest_card(6000, 500)
    assert r["paid_off_in_promo"] and r["retroactive_interest_charged"] == 0


def test_collections_hurt_mortgage_readiness():
    ok = tools.project_mortgage_readiness("dale_pike", 150)
    bad = tools.project_mortgage_readiness("dale_pike", 0, medical_bill_goes_to_collections=True)
    assert bad["projected_credit_score"] < ok["projected_credit_score"]


def test_small_mortgage_unprofitable_traditionally():
    r = tools.estimate_origination_cost(112000)
    assert r["profit_traditional"] < 0 < r["profit_agent_assisted"]


# ------------------------------------------------------------- safety: prompt injection

def test_prefilter_flags_red_team_notes():
    from cabaka.data import get_applicant
    assert safety.prefilter(get_applicant("jordan_test")["notes"])["flagged"]


def test_prefilter_passes_normal_notes():
    from cabaka.data import get_applicant
    assert not safety.prefilter(get_applicant("maria_bronx")["notes"])["flagged"]


# ------------------------------------------------------------- safety: data leak

def test_agent_cannot_read_another_applicants_file():
    ctx = RunContext("test", "maria_bronx")
    out = run_tool(ctx, "Underwriter", "get_credit_report", {"applicant_id": "tina_steuben"})
    assert out["score"] == 598  # Maria's score, not Tina's
    assert any(e["kind"] == "security" for e in ctx.events)


# ------------------------------------------------------------- safety: hallucinated numbers

def test_verifier_catches_invented_number():
    facts = [tools.amortize(6800, 9.9, 24)]
    assert safety.unsupported_numbers("Your payment is $313.47 at 9.9% APR.", facts) == []
    assert safety.unsupported_numbers("Your payment is $199.00 at 3% APR.", facts) == ["$199.00", "3%"]


def test_verifier_blocks_unaffordable_and_trap_offers():
    cash = tools.analyze_cash_flow("maria_bronx")
    bad_offers = {"recommended_offer_name": "Card", "offers": [
        {"name": "Card", "type": "deferred_interest_card", "principal": 6800, "apr_pct": 26.99,
         "months": 12, "monthly_payment": 900, "total_cost": 6800}]}
    review = {"borrower_letter": "Pay $900 per month.", "officer_summary": "ok"}
    checks = {c["check"]: c["passed"] for c in safety.verify_plan(
        "medical", cash, {}, bad_offers, review, [cash], tools.amortize)}
    assert not checks["Payment <= 40% of residual income"]
    assert not checks["APR <= 18% policy cap"]
    assert not checks["No deferred-interest product recommended"]


def test_verifier_flags_prompt_leak_and_prohibited_basis():
    review = {"borrower_letter": f"{safety.CANARY} Because of your nationality we...", "officer_summary": ""}
    checks = {c["check"]: c["passed"] for c in safety.verify_plan(
        "medical", tools.analyze_cash_flow("maria_bronx"), {}, {"offers": []}, review, [], tools.amortize)}
    assert not checks["No system-prompt leak"]
    assert not checks["No prohibited-basis language (ECOA)"]


# ------------------------------------------------------------- safety: overspending

def test_daily_budget_guard(monkeypatch, tmp_path):
    monkeypatch.setattr(safety, "LEDGER", tmp_path / "usage.jsonl")
    monkeypatch.setattr(config, "DAILY_BUDGET_USD", 0.01)
    safety.record_usage({"run_id": "x", "cost_usd": 0.02})
    with pytest.raises(safety.BudgetExceeded):
        safety.check_daily_budget()


def test_rate_limit():
    ip = "test-ip"
    results = [safety.rate_limited(ip) for _ in range(config.RATE_LIMIT_RUNS + 1)]
    assert results[-1] is True and not any(results[:-1])
