const $ = (s) => document.querySelector(s);
const money = (n) => n == null || isNaN(n) ? "—" : "$" + Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 });
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const AGENTS = ["Gatekeeper", "Underwriter", "Offer Architect", "Compliance", "Verifier"];

let applicants = [], current = null, pollTimer = null;

// ---------------------------------------------------------------- tabs + status
document.querySelectorAll(".tab").forEach((b) => b.onclick = () => {
  document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === b));
  document.querySelectorAll(".tabpane").forEach((p) => p.classList.toggle("active", p.id === "tab-" + b.dataset.tab));
  if (b.dataset.tab === "usage") loadUsage();
});

async function loadStatus() {
  const s = await (await fetch("/api/status")).json();
  const pill = $("#statusPill");
  pill.textContent = s.key_configured
    ? `${s.main_model} · spent today ${money(s.spent_today_usd)} / ${money(s.daily_budget_usd)}`
    : "No API key set";
  pill.classList.toggle("bad", !s.key_configured);
}

// ---------------------------------------------------------------- applicants
async function loadApplicants() {
  applicants = await (await fetch("/api/applicants")).json();
  $("#applicants").innerHTML = applicants.map((a) => `
    <div class="appl" data-id="${a.id}">
      <b>${esc(a.name)}</b>
      <span class="badge ${a.product}">${a.product === "medical" ? "Medical loan" : "Small mortgage"}</span>
      <div class="muted">${esc(a.location.city)}, ${esc(a.location.state)}${a.location.rural ? " · rural" : ""} ·
        ${a.product === "medical" ? esc(a.medical.procedure) : "Loan " + money(a.mortgage_application.loan_amount)}</div>
    </div>`).join("");
  document.querySelectorAll(".appl").forEach((el) => el.onclick = () => select(el.dataset.id));
}

function fact(label, value) { return `<div class="fact"><span>${label}</span><b>${value}</b></div>`; }

function select(id) {
  current = applicants.find((a) => a.id === id);
  document.querySelectorAll(".appl").forEach((el) => el.classList.toggle("sel", el.dataset.id === id));
  $("#empty").classList.add("hidden");
  $("#detail").classList.remove("hidden");
  ["#pipe", "#results", "#receipt"].forEach((s) => $(s).classList.add("hidden"));
  const a = current, c = a.credit;
  $("#dName").textContent = a.name;
  $("#dMeta").textContent = `${a.age} · ${a.occupation} · ${a.location.county} · household of ${a.household_size} · prefers ${a.preferred_language}`;
  const p = $("#dProduct");
  p.textContent = a.product === "medical" ? "Medical loan" : "Small mortgage";
  p.className = "badge " + a.product;
  const med = c.medical_collections.reduce((s, x) => s + x.amount, 0);
  let f = fact("Annual income", money(a.annual_income)) +
    fact("Credit score", c.score) + fact("Score w/o medical debt", c.score_without_medical) +
    fact("Medical collections", money(med));
  if (a.product === "medical") {
    f += fact("Procedure", esc(a.medical.procedure)) + fact("Patient owes", money(a.medical.quoted_patient_responsibility)) +
      fact("Home goal", `${money(a.housing_goal.target_price)} in ${a.housing_goal.months_until_purchase} mo`);
  } else {
    const m = a.mortgage_application;
    f += fact("Loan requested", money(m.loan_amount)) + fact("Property value", money(m.property_value)) +
      fact("Property", esc(m.property_type));
  }
  $("#dFacts").innerHTML = f;
  $("#dNotes").value = a.notes;
  $("#runInfo").textContent = "";
}

// ---------------------------------------------------------------- run
$("#runBtn").onclick = async () => {
  if (!current) return;
  $("#runBtn").disabled = true;
  $("#runInfo").textContent = "Starting…";
  const r = await fetch("/api/runs", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ applicant_id: current.id, notes: $("#dNotes").value }),
  });
  const body = await r.json();
  if (!r.ok) { $("#runInfo").textContent = "⚠ " + body.error; $("#runBtn").disabled = false; return; }
  $("#pipe").classList.remove("hidden");
  ["#results", "#receipt"].forEach((s) => $(s).classList.add("hidden"));
  $("#timeline").innerHTML = "";
  document.querySelectorAll(".node").forEach((n) => n.className = "node");
  clearInterval(pollTimer);
  pollTimer = setInterval(() => poll(body.run_id), 900);
};

async function poll(id) {
  const run = await (await fetch("/api/runs/" + id)).json();
  renderTimeline(run.events || []);
  renderReceipt(run);
  const secs = run.events?.length ? run.events[run.events.length - 1].t : 0;
  $("#runInfo").textContent = run.status === "running" ? `Running… ${secs}s` : `Finished in ${run.totals?.seconds ?? secs}s · run ${run.id}`;
  if (run.status !== "running") {
    clearInterval(pollTimer);
    $("#runBtn").disabled = false;
    document.querySelectorAll(".node.active").forEach((n) => n.classList.replace("active", "done"));
    if (run.result) renderResult(run.result);
    if (run.error) $("#runInfo").textContent = "⚠ " + run.error;
    loadStatus();
  }
}

function describe(e) {
  switch (e.kind) {
    case "start": return `started (${esc(e.model)})`;
    case "usage": return `<span class="muted">call ${e.turn}: ${e.input} in · ${e.cache_read} cached · ${e.output} out · ${money(e.cost_usd)}</span>`;
    case "thought": return `<i>${esc(e.text)}</i>`;
    case "tool_call": return `<details><summary>🔧 calls <b>${esc(e.tool)}</b></summary><pre>${esc(JSON.stringify(e.input, null, 1))}</pre></details>`;
    case "tool_result": return `<details><summary>↳ result of <b>${esc(e.tool)}</b></summary><pre>${esc(JSON.stringify(e.output, null, 1))}</pre></details>`;
    case "final": return `<details><summary>✅ submitted answer</summary><pre>${esc(JSON.stringify(e.output, null, 1))}</pre></details>`;
    case "security": return `🛡 ${esc(e.message)}${e.reasons ? "<br><small>" + esc(e.reasons.join("; ")) + "</small>" : ""}${e.failed ? "<br><small>" + esc(e.failed.map((f) => f.check + ": " + f.detail).join("; ")) + "</small>" : ""}`;
    case "error": return `❌ ${esc(e.message)}`;
    default: return esc(e.kind);
  }
}

function renderTimeline(events) {
  const tl = $("#timeline");
  const atBottom = tl.scrollTop + tl.clientHeight >= tl.scrollHeight - 30;
  tl.innerHTML = events.map((e) => `<div class="ev ${e.kind}"><span class="t">${e.t}s</span><span class="who">${esc(e.agent)}</span>${describe(e)}</div>`).join("");
  if (atBottom) tl.scrollTop = tl.scrollHeight;
  const started = new Set(events.filter((e) => e.kind === "start" || e.kind === "final").map((e) => e.agent));
  let last = null;
  events.forEach((e) => { if (AGENTS.includes(e.agent)) last = e.agent; });
  document.querySelectorAll(".node").forEach((n) => {
    const a = n.dataset.agent;
    n.classList.toggle("done", started.has(a) && a !== last);
    n.classList.toggle("active", a === last);
    n.classList.toggle("alert", events.some((e) => e.agent === a && e.kind === "security"));
  });
}

function renderReceipt(run) {
  const u = run.usage || {};
  const names = Object.keys(u);
  if (!names.length) return;
  $("#receipt").classList.remove("hidden");
  const rows = names.map((n) => { const x = u[n]; return `<tr><td>${esc(n)}</td><td>${esc(x.model)}</td><td class="num">${x.calls}</td><td class="num">${x.input.toLocaleString()}</td><td class="num">${x.cache_read.toLocaleString()}</td><td class="num">${x.cache_write.toLocaleString()}</td><td class="num">${x.output.toLocaleString()}</td><td class="num">${money(x.cost_usd)}</td></tr>`; });
  const t = names.reduce((s, n) => { ["calls", "input", "cache_read", "cache_write", "output", "cost_usd"].forEach((k) => s[k] = (s[k] || 0) + u[n][k]); return s; }, {});
  $("#rTokens").innerHTML = `<table><tr><th>Agent</th><th>Model</th><th class="num">Calls</th><th class="num">Input</th><th class="num">Cached input</th><th class="num">Cache write</th><th class="num">Output</th><th class="num">Cost</th></tr>${rows.join("")}
    <tr><th colspan="2">Total</th><th class="num">${t.calls}</th><th class="num">${t.input.toLocaleString()}</th><th class="num">${t.cache_read.toLocaleString()}</th><th class="num">${t.cache_write.toLocaleString()}</th><th class="num">${t.output.toLocaleString()}</th><th class="num">${money(t.cost_usd)}</th></tr></table>`;
}

function renderResult(r) {
  $("#results").classList.remove("hidden");
  const uw = r.underwriting, of = r.offers, rv = r.review;
  const st = $("#rStatus");
  st.textContent = r.status === "ready_for_officer" ? "All checks passed · ready for loan officer" : "Needs human review";
  st.className = "badge " + (r.status === "ready_for_officer" ? "ok" : "warn");
  $("#rDecision").innerHTML = `<b>Underwriter:</b> ${esc(uw.decision_recommendation.replaceAll("_", " "))} · risk tier ${esc(uw.risk_tier)} ·
    max affordable payment <b>${money(uw.max_affordable_monthly_payment)}/mo</b><br><span class="muted">${esc(uw.rationale)}</span>
    ${(uw.key_findings || []).length ? "<ul>" + uw.key_findings.map((k) => `<li>${esc(k)}</li>`).join("") + "</ul>" : ""}
    <b>Offer Architect recommends:</b> ${esc(of.recommended_offer_name)} — <span class="muted">${esc(of.why)}</span>
    ${of.lender_economics ? `<p><b>Lender economics:</b> ${esc(of.lender_economics)}</p>` : ""}`;
  const offers = of.offers || [];
  $("#rOffers").innerHTML = `<table><tr><th>Option</th><th class="num">Monthly</th><th class="num">APR</th><th class="num">Months</th><th class="num">Total cost</th><th class="num">If a payment slips</th><th>Mortgage-ready?</th><th>Trade-offs</th></tr>
    ${offers.map((o) => `<tr class="${o.name === of.recommended_offer_name ? "rec" : ""}"><td><b>${esc(o.name)}</b></td><td class="num">${money(o.monthly_payment)}</td><td class="num">${o.apr_pct ?? "—"}${o.apr_pct != null ? "%" : ""}</td><td class="num">${o.months ?? "—"}</td><td class="num">${money(o.total_cost)}</td><td class="num">${money(o.worst_case_cost)}</td><td>${o.mortgage_ready_after == null ? "—" : o.mortgage_ready_after ? "✅ yes" : "❌ no"}</td><td><small>+ ${esc(o.pros)}<br>− ${esc(o.cons)}</small></td></tr>`).join("")}</table>`;
  const max = Math.max(...offers.map((o) => Math.max(o.total_cost || 0, o.worst_case_cost || 0)), 1);
  $("#rChart").innerHTML = "<h4>Total cost to the borrower (green) vs. worst case if one payment slips (red)</h4>" + offers.map((o) => `
    <div class="bar-row"><div>${esc(o.name)}</div><div>
      <div class="bar" style="width:${70 * (o.total_cost || 0) / max}%"><span>${money(o.total_cost)}</span></div>
      ${o.worst_case_cost ? `<div class="bar worst" style="width:${70 * o.worst_case_cost / max}%;margin-top:3px"><span>${money(o.worst_case_cost)}</span></div>` : ""}
    </div></div>`).join("");
  $("#rLetter").textContent = rv.borrower_letter;
  $("#rOfficer").textContent = rv.officer_summary;
  $("#rChecks").innerHTML = "<h4>Hard checks (code, not AI)</h4>" + r.hard_checks.map((c) => `<div class="check"><span class="${c.passed ? "ok" : "no"}">${c.passed ? "✓" : "✗"}</span> ${esc(c.check)} <span class="muted">— ${esc(c.detail)}</span></div>`).join("") +
    "<h4>Compliance agent's checks</h4>" + (rv.policy_checks || []).map((c) => `<div class="check"><span class="${c.passed ? "ok" : "no"}">${c.passed ? "✓" : "✗"}</span> ${esc(c.check)} <span class="muted">— ${esc(c.detail)}</span></div>`).join("");
  $("#officerMsg").textContent = "";
}

$("#approveBtn").onclick = () => $("#officerMsg").textContent = "Recorded: officer approved. (Demo — nothing is sent.)";
$("#rejectBtn").onclick = () => $("#officerMsg").textContent = "Recorded: sent back for manual underwriting. (Demo — nothing is sent.)";

// ---------------------------------------------------------------- usage tab
async function loadUsage() {
  const rows = await (await fetch("/api/usage")).json();
  const runs = {};
  rows.forEach((r) => { const x = runs[r.run_id] ||= { run_id: r.run_id, day: r.day, calls: 0, input: 0, cache_read: 0, cache_write: 0, output: 0, cost: 0 };
    x.calls++; x.input += r.input; x.cache_read += r.cache_read; x.cache_write += r.cache_write; x.output += r.output; x.cost += r.cost_usd; });
  const list = Object.values(runs).reverse();
  const tot = list.reduce((s, x) => s + x.cost, 0);
  $("#usageSummary").innerHTML = fact("Runs logged", list.length) + fact("Total spend", money(tot.toFixed(4))) +
    fact("Avg cost / run", list.length ? money((tot / list.length).toFixed(4)) : "—") +
    fact("Avg tokens / run", list.length ? Math.round(list.reduce((s, x) => s + x.input + x.cache_read + x.cache_write + x.output, 0) / list.length).toLocaleString() : "—");
  $("#usageTable").innerHTML = `<table><tr><th>Run</th><th>Day</th><th class="num">Calls</th><th class="num">Input</th><th class="num">Cached</th><th class="num">Cache write</th><th class="num">Output</th><th class="num">Cost</th></tr>
    ${list.map((x) => `<tr><td>${esc(x.run_id)}</td><td>${x.day}</td><td class="num">${x.calls}</td><td class="num">${x.input.toLocaleString()}</td><td class="num">${x.cache_read.toLocaleString()}</td><td class="num">${x.cache_write.toLocaleString()}</td><td class="num">${x.output.toLocaleString()}</td><td class="num">${money(x.cost.toFixed(4))}</td></tr>`).join("")}</table>`;
}

// Deep links: #maria_bronx preselects an applicant; #run=<id> replays a finished run.
async function openFromHash() {
  const h = decodeURIComponent(location.hash.slice(1));
  if (!h) return;
  if (h.startsWith("run=")) {
    const run = await (await fetch("/api/runs/" + h.slice(4))).json();
    if (run.error) return;
    select(run.applicant_id);
    if (run.notes_override != null) $("#dNotes").value = run.notes_override;
    $("#pipe").classList.remove("hidden");
    await poll(run.id);
  } else if (applicants.some((a) => a.id === h)) {
    select(h);
  }
}

loadStatus();
loadApplicants().then(openFromHash);
