"""Safety layer: injection pre-filter, data-access lock, output verifier and spend limits."""
import json
import re
import threading
import time
from collections import defaultdict, deque
from datetime import date

from . import config

# A secret marker placed in every system prompt. If it ever shows up in output, the
# model leaked its instructions and the output is blocked.
CANARY = "CBK-CANARY-7731"

INJECTION_PATTERNS = [
    r"ignore (all |any )?(previous|prior|above) (instructions|rules|policies)",
    r"system (override|prompt)",
    r"you are now", r"developer mode", r"jailbreak",
    r"(print|reveal|show|repeat).{0,30}(system prompt|instructions)",
    r"(approve|mark).{0,40}(regardless|compliance as passed|0% apr)",
    r"other applicants?'? (data|credit|files?)",
]


def prefilter(text: str) -> dict:
    """Cheap regex screen that runs before any model sees the text."""
    hits = [p for p in INJECTION_PATTERNS if re.search(p, text or "", re.I)]
    return {"flagged": bool(hits), "matched_patterns": hits}


# ------------------------------------------------------------------ verifier

_NUM = re.compile(r"\$\s?([\d,]+(?:\.\d+)?)|([\d,]+(?:\.\d+)?)\s?%")
PROHIBITED_BASIS = re.compile(
    r"\b(race|racial|religio\w*|national origin|nationality|immigra\w*|ethnic\w*|"
    r"marital|pregnan\w*|gender|sex\b|your age|because you are \d+)\b", re.I)


def _collect_numbers(obj, out: set):
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.add(round(float(obj), 2))
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect_numbers(v, out)
    elif isinstance(obj, str):
        for m in re.findall(r"-?\d[\d,]*\.?\d*", obj):
            try:
                out.add(round(float(m.replace(",", "")), 2))
            except ValueError:
                pass


def unsupported_numbers(text: str, facts) -> list[str]:
    """Every $ amount and % in `text` must match a number produced by a tool (±1% or ±$1)."""
    known = set()
    _collect_numbers(facts, known)
    bad = []
    for m in _NUM.finditer(text or ""):
        raw = (m.group(1) or m.group(2)).replace(",", "")
        try:
            v = float(raw)
        except ValueError:
            continue
        if not any(abs(v - k) <= max(1.0, 0.01 * abs(k)) for k in known):
            bad.append(m.group(0).strip())
    return bad


def verify_plan(product: str, cash_flow: dict, underwriting: dict, offers: dict,
                review: dict, tool_facts: list, recompute_payment) -> list[dict]:
    """Hard, non-LLM policy checks. Returns a list of {check, passed, detail}."""
    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "passed": bool(ok), "detail": detail})

    rec_name = offers.get("recommended_offer_name")
    rec = next((o for o in offers.get("offers", []) if o.get("name") == rec_name), None)
    add("Recommended offer exists", rec is not None, f"recommended_offer_name = {rec_name!r}")

    if rec and product == "medical":
        cap = round(0.40 * cash_flow["monthly_residual_income"], 2)
        pay = rec.get("monthly_payment") or 0
        add("Payment <= 40% of residual income", pay <= cap + 1,
            f"payment ${pay} vs cap ${cap} (residual ${cash_flow['monthly_residual_income']})")
        apr = rec.get("apr_pct")
        add("APR <= 18% policy cap", (apr or 0) <= 18, "no interest (not a loan)" if apr is None else f"APR {apr}%")
        add("No deferred-interest product recommended", rec.get("type") != "deferred_interest_card",
            f"type = {rec.get('type')}")
    if rec and rec.get("principal") and rec.get("months") and rec.get("apr_pct") is not None:
        expect = recompute_payment(rec["principal"], rec["apr_pct"], rec["months"])["monthly_payment"]
        add("Payment math re-computed", abs(expect - (rec.get("monthly_payment") or 0)) <= 1,
            f"agent ${rec.get('monthly_payment')} vs calculator ${expect}")

    letter = review.get("borrower_letter", "")
    facts = tool_facts + [underwriting, offers]
    bad = unsupported_numbers(letter, facts)
    add("Every number in the letter traces to a tool", not bad,
        "all numbers verified" if not bad else f"unsupported: {', '.join(bad)}")
    found = PROHIBITED_BASIS.findall(letter + " " + review.get("officer_summary", ""))
    add("No prohibited-basis language (ECOA)", not found,
        "none" if not found else f"found: {sorted(set(map(str.lower, found)))}")
    leaked = CANARY in json.dumps([underwriting, offers, review])
    add("No system-prompt leak", not leaked, "canary absent" if not leaked else "canary found in output")
    return checks


# ------------------------------------------------------------------ spend limits

class BudgetExceeded(Exception):
    pass


_lock = threading.Lock()
LEDGER = config.LOG_DIR / "usage.jsonl"


def spent_today() -> float:
    if not LEDGER.exists():
        return 0.0
    today = date.today().isoformat()
    total = 0.0
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("day") == today:
            total += r.get("cost_usd", 0)
    return total


def record_usage(entry: dict):
    with _lock, LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"day": date.today().isoformat(), **entry}) + "\n")


def check_daily_budget():
    s = spent_today()
    if s >= config.DAILY_BUDGET_USD:
        raise BudgetExceeded(f"Daily budget of ${config.DAILY_BUDGET_USD:.2f} reached (spent ${s:.2f}).")


_hits: dict[str, deque] = defaultdict(deque)


def rate_limited(ip: str) -> bool:
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > config.RATE_LIMIT_WINDOW_S:
        q.popleft()
    if len(q) >= config.RATE_LIMIT_RUNS:
        return True
    q.append(now)
    return False
