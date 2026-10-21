"""Cabaka Credit web app.  Run:  python app.py  then open http://localhost:5000"""
import json
import os
import threading

from flask import Flask, jsonify, request, send_from_directory

from cabaka import config, pipeline, safety
from cabaka.data import get_applicant, get_transactions, list_applicants

app = Flask(__name__, static_folder="static", static_url_path="/static")


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/api/status")
def status():
    return jsonify({"key_configured": bool(config.ANTHROPIC_API_KEY), "main_model": config.MAIN_MODEL,
                    "guard_model": config.GUARD_MODEL, "effort": config.MAIN_EFFORT,
                    "spent_today_usd": round(safety.spent_today(), 4),
                    "daily_budget_usd": config.DAILY_BUDGET_USD})


@app.get("/api/applicants")
def applicants():
    return jsonify(list_applicants())


@app.get("/api/applicants/<aid>/transactions")
def transactions(aid):
    try:
        get_applicant(aid)
    except KeyError:
        return jsonify({"error": "unknown applicant"}), 404
    return jsonify(get_transactions(aid))


@app.post("/api/runs")
def start_run():
    body = request.get_json(force=True, silent=True) or {}
    aid = str(body.get("applicant_id", ""))
    try:
        get_applicant(aid)
    except KeyError:
        return jsonify({"error": "unknown applicant"}), 400
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()
    if safety.rate_limited(ip):
        return jsonify({"error": f"Rate limit: max {config.RATE_LIMIT_RUNS} runs per "
                                 f"{config.RATE_LIMIT_WINDOW_S // 60} minutes. Please wait."}), 429
    try:
        safety.check_daily_budget()
    except safety.BudgetExceeded as e:
        return jsonify({"error": str(e)}), 429
    if not config.ANTHROPIC_API_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY is not set on the server. See README."}), 500
    notes = body.get("notes")
    notes = str(notes)[: config.MAX_NOTE_CHARS] if notes is not None else None
    run_id = pipeline.new_run(aid, notes)
    threading.Thread(target=pipeline.execute, args=(run_id,), daemon=True).start()
    return jsonify({"run_id": run_id})


@app.get("/api/runs/<run_id>")
def get_run(run_id):
    run = pipeline.RUNS.get(run_id)
    if run is None:
        path = pipeline.RUN_DIR / f"{os.path.basename(run_id)}.json"
        if not path.exists():
            return jsonify({"error": "not found"}), 404
        run = json.loads(path.read_text(encoding="utf-8"))
    return jsonify(run)


@app.get("/api/usage")
def usage():
    rows = []
    if safety.LEDGER.exists():
        rows = [json.loads(l) for l in safety.LEDGER.read_text(encoding="utf-8").splitlines() if l.strip()]
    return jsonify(rows[-500:])


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    print(f"Cabaka Credit running on http://localhost:{port}  (API key set: {bool(config.ANTHROPIC_API_KEY)})")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
