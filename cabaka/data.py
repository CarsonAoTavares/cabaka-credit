"""Loads the synthetic applicant files and reference tables from data/."""
import csv
import json
from functools import lru_cache

from .config import DATA_DIR


@lru_cache(maxsize=None)
def reference(name: str) -> dict:
    return json.loads((DATA_DIR / "reference" / f"{name}.json").read_text(encoding="utf-8"))


def list_applicants() -> list[dict]:
    out = []
    for p in sorted((DATA_DIR / "applicants").glob("*.json")):
        a = json.loads(p.read_text(encoding="utf-8"))
        out.append(a)
    # Medical files first, then mortgages, red-team file last.
    return sorted(out, key=lambda a: ("red-team" in a["name"], a["product"] != "medical", a["name"]))


def get_applicant(applicant_id: str) -> dict:
    path = DATA_DIR / "applicants" / f"{applicant_id}.json"
    if not path.exists() or not applicant_id.replace("_", "").isalnum():
        raise KeyError(f"Unknown applicant_id '{applicant_id}'")
    return json.loads(path.read_text(encoding="utf-8"))


def get_transactions(applicant_id: str) -> list[dict]:
    path = DATA_DIR / "transactions" / f"{applicant_id}.csv"
    with path.open(newline="", encoding="utf-8") as f:
        return [
            {"date": r["date"], "description": r["description"],
             "category": r["category"], "amount": float(r["amount"]), "balance": float(r["balance"])}
            for r in csv.DictReader(f)
        ]
