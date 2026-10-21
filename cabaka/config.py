"""Settings, model prices and .env loading.

The .env file is looked up in the repo folder first, then one folder above it
(the teaching staff keep their shared .env in the parent `submissions/` folder).
"""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Repo .env wins; parent .env fills in anything still missing.
load_dotenv(ROOT / ".env", override=False)
load_dotenv(ROOT.parent / ".env", override=False)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()

# Main reasoning agents and the cheap gatekeeper agent.
MAIN_MODEL = os.getenv("CABAKA_MAIN_MODEL", "claude-opus-5-5")
GUARD_MODEL = os.getenv("CABAKA_GUARD_MODEL", "claude-haiku-5-5")
MAIN_EFFORT = os.getenv("CABAKA_MAIN_EFFORT", "low")

# USD per 1M tokens: input, output, cache read, cache write (5-minute TTL = 1.25x input).
PRICES = {
    "claude-opus-5-5": {"input": 4.00, "output": 20.00, "cache_read": 0.20, "cache_write": 5.00},
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "cache_read": 0.20, "cache_write": 2.50},
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cache_read": 0.01, "cache_write": 0.125},
}

# Overspending guards.
MAX_TOOL_TURNS = int(os.getenv("CABAKA_MAX_TOOL_TURNS", "8"))        # per agent
MAX_RUN_TOKENS = int(os.getenv("CABAKA_MAX_RUN_TOKENS", "150000"))   # all agents, one run
DAILY_BUDGET_USD = float(os.getenv("CABAKA_DAILY_BUDGET_USD", "5.00"))
RATE_LIMIT_RUNS = int(os.getenv("CABAKA_RATE_LIMIT_RUNS", "6"))      # per IP ...
RATE_LIMIT_WINDOW_S = int(os.getenv("CABAKA_RATE_LIMIT_WINDOW_S", "600"))  # ... per 10 minutes
MAX_NOTE_CHARS = 2000


def cost_usd(model: str, usage: dict) -> float:
    p = PRICES.get(model, PRICES["claude-opus-5-5"])
    return (
        usage.get("input", 0) * p["input"]
        + usage.get("output", 0) * p["output"]
        + usage.get("cache_read", 0) * p["cache_read"]
        + usage.get("cache_write", 0) * p["cache_write"]
    ) / 1_000_000
