# Project status: Cabaka Credit final project

*Last updated: 2026-10-21. Due: Monday, October 26, 2026, 6:00 PM on Canvas.*

Hand this file to any new Claude Code session to pick up where we left off.

## Links
- Repo (public): https://github.com/CarsonAoTavares/cabaka-credit
- Live app: https://cabaka-credit.onrender.com (Render free plan; auto-deploys on push to `main`; `ANTHROPIC_API_KEY` set in Render → Environment)

## Decisions already made
- **App:** Cabaka Credit, Care-to-Home Copilot. Gatekeeper (Haiku 5.5) → Underwriter → Offer Architect → Compliance (Opus 5.5, low effort) → code Verifier → human loan officer. Two products on the same agents: clinic medical loans and small (<$150k) mortgages.
- **Model access:** Claude only, via `ANTHROPIC_API_KEY` (no Portkey, no OpenAI). Hosted online because the staff only have OpenAI/Portkey keys.
- **Shipped config:** Opus 5.5 at low effort. The comparison showed medium effort adds 31% cost for no gain, and Sonnet/Haiku make judgment errors.

## Done
- [x] App, 17 offline tests, README, `.env.example`, `render.yaml`, fresh-clone dry run
- [x] Live deploy working with the key (live run on Render: $0.10, 40 s, all checks passed)
- [x] Real runs: all 5 applicants pass; the red-team injection was blocked live. Average $0.124/run, ~25k tokens, 46 s
- [x] Model comparison (Opus low/medium, Sonnet, Haiku × 4 applicants), in `docs/evidence/model_comparison.json`
- [x] Screenshots `docs/img/01`–`07`; report.html is 13 pages; slides.html has 9 slides
- [x] Evidence logs in `docs/evidence/` (19 runs, 131 calls, $1.63 total spend)
- [x] Facts checked against sources (Freddie Mac, Pew, CFPB, KFF, HHS 2026)

## To do
1. ~~Real-user test~~ **Done** (Oct 24): loan officer, 1 hr → 2 min, trust 3/5, approved; run 20261024-150218-4905e1.
2. Optional: demo video (2–3 min).
3. The day you submit: open the live link so the free server is awake; check the key has not expired (keys expire on a date you chose; the first ones expired Nov 20, 2026).
4. Submit on Canvas: the repo link, report.html, slides.html.

## Notes
- Python venv: `.venv`. Git: `C:\Program Files\Git\cmd\git.exe`.
- Run locally: `.venv\Scripts\python.exe app.py` → http://localhost:5000. Deep links: `#maria_bronx`, `#run=<id>`, `#run=<id>&full`.
- Never paste the API key into chat. It lives only in `.env` (git-ignored) and in Render's Environment page.
