"""Runs the real pipeline (real Claude calls) for applicants and prints a summary.

Usage:  python scripts/run_all.py [applicant_id ...]     (default: all five)
Each run is saved to logs/runs/<run_id>.json and every call to logs/usage.jsonl.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cabaka import pipeline  # noqa: E402

DEFAULT = ["maria_bronx", "dale_pike", "kwame_staten", "tina_steuben", "jordan_test"]


def main(ids):
    rows = []
    for aid in ids:
        rid = pipeline.new_run(aid)
        print(f"running {aid} ({rid}) ...", flush=True)
        pipeline.execute(rid)
        run = pipeline.RUNS[rid]
        res = run.get("result") or {}
        t = run["totals"]
        rows.append({"applicant": aid, "run_id": rid, "status": run["status"], "result": res.get("status"),
                     "failed_checks": [c["check"] for c in res.get("hard_checks", []) if not c["passed"]],
                     "security_events": sum(1 for e in run["events"] if e["kind"] == "security"),
                     **t})
        print(json.dumps(rows[-1]), flush=True)
    out = Path(pipeline.config.LOG_DIR) / "run_summary.json"
    out.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    print("summary ->", out)


if __name__ == "__main__":
    main(sys.argv[1:] or DEFAULT)
