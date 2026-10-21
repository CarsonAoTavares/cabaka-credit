# Project status: Cabaka Credit final project

*Last updated: 2026-10-21. Due: Monday, October 26, 2026, 6:00 PM on Canvas.*

Hand this file to any new Claude Code session to pick up where we left off.

## Decisions already made
- **App:** Cabaka Credit, Care-to-Home Copilot. Multi-agent Claude app: Gatekeeper (Haiku 5.5) → Underwriter → Offer Architect → Compliance (Opus 5.5, low effort) → code Verifier → human loan officer. Two products on the same agents: clinic medical loans and small (<$150k) mortgages.
- **Model access:** Claude only, via `ANTHROPIC_API_KEY` (no Portkey, no OpenAI). The app will be **hosted online** (Render, `render.yaml`), because the teaching staff only have OpenAI/Portkey keys.
- **Data:** 5 fictional applicants (`scripts/make_synthetic_data.py`); `jordan_test` is the prompt-injection red-team file.

## Done
- [x] App code: `app.py`, `cabaka/` (tools, agents, pipeline, safety, llm), web UI in `static/`
- [x] 17 offline tests pass (`python -m pytest -q`), including the full pipeline with a fake Claude
- [x] README, `.env.example`, `.gitignore` (real `.env` is never committed), `render.yaml`
- [x] Fresh-clone dry run: install takes ~30s, tests pass, `.env` one folder up is found
- [x] Facts checked against sources (Freddie Mac, Pew, CFPB, KFF, HHS 2026 FPL); the 2025 CFPB medical-debt rule was **vacated July 2025**
- [x] report.html (8 pages now) and slides.html (9 slides) drafts; build with `python scripts/build_docs.py`
- [x] Screenshots: `docs/img/01_applicant.png` (retake once the key is set), `docs/img/07_tests.png`
- [x] Local git repo with commits

## To do (in order)
1. **User:** create an Anthropic API key (platform.claude.com → Billing $10 → API Keys) and paste it into `.env`.
2. Real runs: Maria, Dale, Kwame, Tina, Jordan Test (injection) → `logs/runs/*.json`, `logs/usage.jsonl`.
3. Screenshots from runs: `python scripts/screenshots.py run <run_id> <name>` →
   `02_timeline`, `03_offers`, `04_letter`, `05_receipt`, `06_injection`; retake `01_applicant`.
4. Cost-vs-quality test: Opus low vs Opus medium vs Sonnet 5.5 on the 4 normal applicants
   (cost, time, Verifier pass rate). Set the model with `CABAKA_MAIN_MODEL` / `CABAKA_MAIN_EFFORT`.
5. Fill every **TBD** in `docs/report_src.html` and `docs/slides_src.html`, rebuild, check 10–15 printed pages.
6. ~~GitHub repo~~ **Done:** public at https://github.com/CarsonAoTavares/cabaka-credit (push with `git push`).
7. ~~Deploy~~ **Done:** live at https://cabaka-credit.onrender.com (Render free plan, auto-deploys on every push to `main`).
   **Still needed:** the user pastes `ANTHROPIC_API_KEY` in Render → cabaka-credit → Environment → Save (it redeploys).
8. **User:** one real person tries the app (loan officer, clinic front desk, or patient). Get a quote and their time today vs. with the app.
9. Optional: 2–3 minute demo video.
10. Submit on Canvas: repo link, report.html, slides.html (+ video).

## Notes
- Python 3.12 is at `C:\Users\carso\AppData\Local\Programs\Python\Python312-arm64\python.exe`; project venv is `.venv`.
- Git is at `%LOCALAPPDATA%\Programs\Git\cmd\git.exe` (not on PATH in older shells).
- Research PDFs in the Cabaka Google Drive are OneDrive cloud-only files and could not be opened from Claude Code.
- Estimated cost: ~$0.15–0.40 per run; the whole project ~$5–10. The app stops at $5/day (`CABAKA_DAILY_BUDGET_USD`).
