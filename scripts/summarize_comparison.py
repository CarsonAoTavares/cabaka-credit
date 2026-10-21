"""Prints a per-run decision table for logs/model_comparison.json (plus the Haiku retry run)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from cabaka import tools  # noqa: E402

rows = json.loads((ROOT / "logs" / "model_comparison.json").read_text(encoding="utf-8"))
for a in ("maria_bronx", "dale_pike", "kwame_staten", "tina_steuben"):
    cf = tools.analyze_cash_flow(a)
    print(f"{a}: residual {cf['monthly_residual_income']}, volatility {cf['income_volatility_pct']}%")
for x in rows:
    if x["status"] != "done":
        continue
    r = json.loads((ROOT / "logs" / "runs" / f"{x['run_id']}.json").read_text(encoding="utf-8"))
    res = r["result"]
    uw, of = res["underwriting"], res["offers"]
    rec = next((o for o in of["offers"] if o["name"] == of["recommended_offer_name"]), {})
    print(f"{x['config'][:24]:24} {x['applicant']:13} {uw['decision_recommendation']:22} "
          f"cap {uw['max_affordable_monthly_payment']:<8} rec {rec.get('type', ''):20} apr {rec.get('apr_pct')} | "
          + str([(o.get('type', '')[:9], o.get('monthly_payment'), o.get('apr_pct')) for o in of['offers']]))
