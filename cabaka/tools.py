"""Deterministic financial tools the agents can call.

Every number an agent shows a borrower must come out of one of these functions,
so the math is exact and auditable. The LLM decides *which* tools to call and
how to explain the result; it never does the arithmetic itself.
"""
import statistics
from collections import defaultdict

from .data import get_applicant, get_transactions, reference

ESSENTIAL = {"rent", "utilities", "groceries", "transport", "insurance", "childcare", "medical", "phone"}
DEBT = {"debt_payment"}


def _r(x, n=2):
    return round(float(x), n)


def _payment(principal: float, apr_pct: float, months: int) -> float:
    if months <= 0:
        raise ValueError("months must be positive")
    r = apr_pct / 100 / 12
    if r == 0:
        return principal / months
    return principal * r / (1 - (1 + r) ** -months)


# ---------------------------------------------------------------- shared tools

def analyze_cash_flow(applicant_id: str) -> dict:
    """Summarise 90 days of bank transactions into monthly cash-flow figures."""
    tx = get_transactions(applicant_id)
    by_month = defaultdict(lambda: {"income": 0.0, "essential": 0.0, "debt": 0.0, "other": 0.0})
    overdrafts = 0
    for t in tx:
        m = by_month[t["date"][:7]]
        if t["amount"] > 0:
            m["income"] += t["amount"]
        elif t["category"] in ESSENTIAL:
            m["essential"] += -t["amount"]
        elif t["category"] in DEBT:
            m["debt"] += -t["amount"]
        else:
            m["other"] += -t["amount"]
        if t["category"] == "overdraft_fee":
            overdrafts += 1
    months = sorted(by_month)
    inc = [by_month[k]["income"] for k in months]
    avg = lambda key: statistics.mean(by_month[k][key] for k in months)
    avg_income = statistics.mean(inc)
    residual = avg_income - avg("essential") - avg("debt")
    # Volatility = spread of individual deposits (a steady paycheck is ~0%, gig payouts are high).
    deposits = [t["amount"] for t in tx if t["amount"] > 0]
    vol = 100 * statistics.pstdev(deposits) / statistics.mean(deposits) if deposits else 0
    return {
        "months_of_data": len(months),
        "avg_monthly_income": _r(avg_income),
        "income_volatility_pct": _r(vol, 1),
        "avg_monthly_essential_spend": _r(avg("essential")),
        "avg_monthly_debt_payments": _r(avg("debt")),
        "avg_monthly_discretionary_spend": _r(avg("other")),
        "monthly_residual_income": _r(residual),
        "min_balance_90d": _r(min(t["balance"] for t in tx)),
        "overdraft_count_90d": overdrafts,
    }


def get_credit_report(applicant_id: str) -> dict:
    """Bureau-style snapshot, including the score with medical collections removed."""
    c = get_applicant(applicant_id)["credit"]
    med = sum(x["amount"] for x in c["medical_collections"])
    return {
        "score": c["score"],
        "score_excluding_medical_collections": c["score_without_medical"],
        "medical_collections_total": _r(med),
        "medical_collections": c["medical_collections"],
        "non_medical_tradelines": c["tradelines"],
        "late_payments_24m_non_medical": c["late_payments_24m"],
        "note": "Medical collections are a weak predictor of repayment (CFPB 2022/2025); "
                "Cabaka policy underwrites on the medical-excluded score plus cash flow.",
    }


# ---------------------------------------------------------------- medical-loan tools

def lookup_procedure_benchmark(procedure_code: str) -> dict:
    """Fair-price range for a procedure, to flag over-priced quotes."""
    table = reference("procedures")
    if procedure_code not in table:
        return {"error": f"No benchmark for '{procedure_code}'", "known_codes": sorted(table)}
    return {"procedure_code": procedure_code, **table[procedure_code]}


def check_financial_assistance(applicant_id: str) -> dict:
    """Income as % of the federal poverty guideline and the typical charity-care tier."""
    a = get_applicant(applicant_id)
    fpl = reference("fpl")
    size = a["household_size"]
    line = fpl["base"] + fpl["per_extra_person"] * (size - 1)
    pct = 100 * a["annual_income"] / line
    if pct <= 200:
        tier = "likely FREE care under a typical nonprofit-hospital financial assistance policy"
    elif pct <= 400:
        tier = "likely DISCOUNTED care (sliding scale) under a typical nonprofit-hospital policy"
    else:
        tier = "unlikely to qualify for charity care"
    return {
        "household_size": size,
        "annual_income": a["annual_income"],
        "poverty_guideline": line,
        "income_pct_of_fpl": _r(pct, 1),
        "assistance_tier": tier,
        "provider_is_nonprofit": a["medical"]["provider_nonprofit"],
        "source": fpl["source"],
    }


def amortize(principal: float, apr_pct: float, months: int) -> dict:
    """Fixed monthly payment and total interest for a simple-interest installment loan."""
    pay = _payment(principal, apr_pct, months)
    return {
        "principal": _r(principal), "apr_pct": apr_pct, "months": months,
        "monthly_payment": _r(pay), "total_interest": _r(pay * months - principal),
        "total_paid": _r(pay * months),
    }


def simulate_deferred_interest_card(principal: float, monthly_payment: float,
                                    promo_months: int = 12, standard_apr_pct: float = 26.99) -> dict:
    """Typical medical credit card: 0% promo, but ALL interest since day one is charged
    if the balance is not fully paid by the end of the promo period."""
    balance = principal
    for _ in range(promo_months):
        balance -= monthly_payment
    paid_off = balance <= 0.005
    retro = 0.0 if paid_off else principal * standard_apr_pct / 100 * promo_months / 12
    return {
        "principal": _r(principal), "monthly_payment": _r(monthly_payment),
        "promo_months": promo_months, "standard_apr_pct": standard_apr_pct,
        "paid_off_in_promo": paid_off,
        "balance_at_promo_end": _r(max(balance, 0)),
        "retroactive_interest_charged": _r(retro),
        "payment_needed_to_avoid_penalty": _r(principal / promo_months),
    }


def project_mortgage_readiness(applicant_id: str, new_monthly_payment: float,
                               medical_bill_goes_to_collections: bool = False) -> dict:
    """How a medical payment plan changes the borrower's path to their target home."""
    a = get_applicant(applicant_id)
    cf = analyze_cash_flow(applicant_id)
    goal = a["housing_goal"]
    terms = reference("mortgage_terms")
    gross = a["annual_income"] / 12
    other_debt = cf["avg_monthly_debt_payments"] + new_monthly_payment
    loan = goal["target_price"] - goal["down_payment_saved"]
    pmt = _payment(loan, terms["rate_pct"], 360) + goal["target_price"] * terms["tax_ins_pct_of_value"] / 100 / 12
    dti = 100 * (pmt + other_debt) / gross
    max_housing = gross * terms["max_dti_pct"] / 100 - other_debt
    score = get_applicant(applicant_id)["credit"]["score"]
    if medical_bill_goes_to_collections:
        score -= terms["collections_score_hit"]
    return {
        "target_home_price": goal["target_price"],
        "planned_purchase_in_months": goal["months_until_purchase"],
        "estimated_mortgage_payment_piti": _r(pmt),
        "back_end_dti_pct": _r(dti, 1),
        "max_dti_pct_allowed": terms["max_dti_pct"],
        "max_affordable_housing_payment": _r(max_housing),
        "projected_credit_score": score,
        "min_score_needed": terms["min_score"],
        "mortgage_ready": dti <= terms["max_dti_pct"] and score >= terms["min_score"],
        "assumptions": f"30-yr fixed at {terms['rate_pct']}%, taxes+insurance "
                       f"{terms['tax_ins_pct_of_value']}%/yr of value",
    }


# ---------------------------------------------------------------- small-mortgage tools

def compute_mortgage_ratios(applicant_id: str) -> dict:
    """LTV and DTI for the mortgage being applied for."""
    a = get_applicant(applicant_id)
    app = a["mortgage_application"]
    cf = analyze_cash_flow(applicant_id)
    terms = reference("mortgage_terms")
    pi = _payment(app["loan_amount"], app["rate_pct"], app["term_months"])
    ti = app["property_value"] * terms["tax_ins_pct_of_value"] / 100 / 12
    gross = a["annual_income"] / 12
    return {
        "loan_amount": app["loan_amount"], "property_value": app["property_value"],
        "ltv_pct": _r(100 * app["loan_amount"] / app["property_value"], 1),
        "monthly_principal_interest": _r(pi), "monthly_taxes_insurance": _r(ti),
        "front_end_dti_pct": _r(100 * (pi + ti) / gross, 1),
        "back_end_dti_pct": _r(100 * (pi + ti + cf["avg_monthly_debt_payments"]) / gross, 1),
        "residual_income_after_housing": _r(cf["monthly_residual_income"] - pi - ti),
    }


def check_program_eligibility(applicant_id: str) -> dict:
    """Screen against common small-mortgage programs (simplified rules)."""
    a = get_applicant(applicant_id)
    app = a["mortgage_application"]
    ami = reference("county_context").get(a["location"]["county"], {}).get("area_median_income")
    score = a["credit"]["score_without_medical"]
    ratios = compute_mortgage_ratios(applicant_id)
    pct_ami = 100 * a["annual_income"] / ami if ami else None
    res = {}
    res["USDA_502_guaranteed"] = {
        "eligible": bool(a["location"]["rural"] and pct_ami is not None and pct_ami <= 115),
        "why": f"rural={a['location']['rural']}, income={_r(pct_ami or 0, 0)}% of area median (limit 115%)",
    }
    res["FHA"] = {
        "eligible": score >= 580 and ratios["ltv_pct"] <= 96.5,
        "why": f"score {score} (min 580), LTV {ratios['ltv_pct']}% (max 96.5%)",
    }
    res["Fannie_HomeReady"] = {
        "eligible": score >= 620 and pct_ami is not None and pct_ami <= 80 and ratios["ltv_pct"] <= 97,
        "why": f"score {score} (min 620), income {_r(pct_ami or 0, 0)}% AMI (max 80%)",
    }
    res["note"] = "Simplified screening rules for demo; a loan officer confirms final eligibility."
    res["small_loan"] = app["loan_amount"] < 150_000
    return res


def get_county_lending_context(county: str) -> dict:
    """Local market facts for the county (rural flag, denial rates, lender count)."""
    ctx = reference("county_context")
    if county not in ctx:
        return {"error": f"No data for county '{county}'", "known_counties": sorted(ctx)}
    return {"county": county, **ctx[county]}


def estimate_origination_cost(loan_amount: float) -> dict:
    """Fixed cost of originating this loan, traditional vs. agent-assisted, and lender profit."""
    c = reference("origination_costs")
    revenue = loan_amount * c["revenue_bps"] / 10_000
    trad, ai = c["traditional_cost_per_loan"], c["agent_assisted_cost_per_loan"]
    return {
        "loan_amount": loan_amount,
        "lender_revenue_estimate": _r(revenue),
        "traditional_origination_cost": trad,
        "agent_assisted_origination_cost": ai,
        "profit_traditional": _r(revenue - trad),
        "profit_agent_assisted": _r(revenue - ai),
        "breakeven_loan_size_traditional": _r(trad * 10_000 / c["revenue_bps"], 0),
        "breakeven_loan_size_agent_assisted": _r(ai * 10_000 / c["revenue_bps"], 0),
        "source": c["source"],
    }


REGISTRY = {f.__name__: f for f in [
    analyze_cash_flow, get_credit_report, lookup_procedure_benchmark, check_financial_assistance,
    amortize, simulate_deferred_interest_card, project_mortgage_readiness,
    compute_mortgage_ratios, check_program_eligibility, get_county_lending_context,
    estimate_origination_cost,
]}
