# Cabaka Credit — Care-to-Home Copilot

**Live app: https://cabaka-credit.onrender.com**
*(Free hosting: if nobody has used it for 15 minutes the server sleeps, so the first load can take ~50 seconds. Please wait, then refresh.)*

Cabaka Credit is a multi-agent AI app that stops a medical bill from turning into a mortgage denial.
At a clinic front desk it designs a medical payment plan the patient can actually afford, one that keeps
them mortgage-ready. At a community bank, the **same agents** underwrite a small (<$150k) mortgage at a
fraction of the usual origination cost. A human loan officer always makes the final call.

| Agent | Model | Job | Tools |
|---|---|---|---|
| Gatekeeper | Claude Haiku 5.5 | Screens untrusted free text for prompt injection | regex pre-filter + structured output |
| Underwriter | Claude Opus 5.5 | Cash-flow + medical-excluded credit underwriting | `analyze_cash_flow`, `get_credit_report`, `lookup_procedure_benchmark`, `check_financial_assistance`, `compute_mortgage_ratios`, `check_program_eligibility`, `get_county_lending_context` |
| Offer Architect | Claude Opus 5.5 | Designs and compares offers | `amortize`, `simulate_deferred_interest_card`, `project_mortgage_readiness`, `estimate_origination_cost` |
| Compliance & Explainer | Claude Opus 5.5 | Policy + fair-lending review, plain-language letter in the borrower's language | `submit_review` |
| Verifier | plain Python | Re-computes math, traces every $ and % to a tool, caps payment/APR, blocks prompt leaks | — |

All applicants are **fictional** (see `scripts/make_synthetic_data.py`). This is a prototype, not a lending offer.

## Run it locally (about 5 minutes)

You need Python 3.10+ and an Anthropic API key.

```bash
git clone https://github.com/CarsonAoTavares/cabaka-credit.git
cd cabaka-credit
python -m venv .venv
```

Activate the virtual environment: on Windows run `.venv\Scripts\activate`, on Mac or Linux run `source .venv/bin/activate`. Then:

```bash
pip install -r requirements.txt
```

Create a `.env` file with your key. Copy `.env.example` to `.env` and fill in `ANTHROPIC_API_KEY`.
The app looks for `.env` in this folder first and then in the folder **one level above**, so a shared
`submissions/.env` also works.

```bash
python app.py
```

Open http://localhost:5000, pick an applicant, and click **Run Cabaka agents**. A run takes about 1–2 minutes.

### Try the safety defenses
* Pick **Jordan Test (red-team file)**: its notes contain a prompt-injection attack. Watch the Gatekeeper block it.
* Or type your own attack into any applicant's notes box.
* Offline tests of every defense (no API key needed): `python -m pytest -q`

## Deploy online (Render, free)
1. Push this repo to GitHub.
2. On https://render.com choose **New → Blueprint**, pick the repo (it reads `render.yaml`).
3. Set the secret `ANTHROPIC_API_KEY` in the Render dashboard. Never commit it.

## Cost controls
Daily dollar budget (`CABAKA_DAILY_BUDGET_USD`, default $5), per-run token cap, max 8 turns per agent,
6 runs per visitor per 10 minutes, prompt caching on every agent. Every call's real token usage is in
`logs/usage.jsonl` and on the **Usage & cost** tab.

## Evidence for the report
`docs/evidence/` holds the real run logs (every agent step, tool call and token count), the per-call usage ledger,
and the model comparison. `scripts/run_all.py` reruns the applicants, `scripts/compare_models.py` reruns the comparison,
and `scripts/build_docs.py` rebuilds `report.html` / `slides.html` from `docs/*_src.html`.

## Project layout
```
app.py                  Flask server + JSON API
cabaka/pipeline.py      Orchestrator (Gatekeeper → Underwriter → Offer Architect → Compliance → Verifier)
cabaka/agents.py        Prompts, product policies, tool schemas
cabaka/llm.py           Claude tool-use loop, token accounting, applicant lock
cabaka/tools.py         Deterministic financial calculators
cabaka/safety.py        Injection filter, verifier, budget + rate limits
data/                   Synthetic applicants, 90-day bank transactions, reference tables
static/                 Web UI
tests/                  Offline tests
```
