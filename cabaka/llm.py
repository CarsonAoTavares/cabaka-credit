"""Claude client, the tool-use loop every agent runs on, and token accounting."""
import json
import time

import anthropic

from . import config, safety
from .tools import REGISTRY

_client = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY is missing. Add it to .env (see README).")
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, max_retries=2, timeout=120)
    return _client


class RunContext:
    """Shared state for one pipeline run: event log, token totals, applicant lock."""

    def __init__(self, run_id: str, applicant_id: str):
        self.run_id = run_id
        self.applicant_id = applicant_id
        self.events: list[dict] = []
        self.usage_by_agent: dict[str, dict] = {}
        self.tool_facts: list = []
        self.started = time.time()

    def emit(self, agent: str, kind: str, **data):
        self.events.append({"t": round(time.time() - self.started, 2), "agent": agent, "kind": kind, **data})

    def total_tokens(self) -> int:
        return sum(u["input"] + u["output"] + u["cache_read"] + u["cache_write"]
                   for u in self.usage_by_agent.values())

    def add_usage(self, agent: str, model: str, u) -> dict:
        row = self.usage_by_agent.setdefault(agent, {"model": model, "calls": 0, "input": 0, "output": 0,
                                                     "cache_read": 0, "cache_write": 0, "cost_usd": 0.0})
        delta = {
            "input": u.input_tokens or 0,
            "output": u.output_tokens or 0,
            "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
            "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0,
        }
        cost = config.cost_usd(model, delta)
        row["calls"] += 1
        for k, v in delta.items():
            row[k] += v
        row["cost_usd"] = round(row["cost_usd"] + cost, 6)
        safety.record_usage({"run_id": self.run_id, "agent": agent, "model": model, **delta,
                             "cost_usd": round(cost, 6)})
        return {**delta, "cost_usd": round(cost, 6)}


def _guard_budget(ctx: RunContext):
    safety.check_daily_budget()
    if ctx.total_tokens() > config.MAX_RUN_TOKENS:
        raise safety.BudgetExceeded(f"Run token cap of {config.MAX_RUN_TOKENS:,} reached.")


def run_tool(ctx: RunContext, agent: str, name: str, args: dict):
    """Execute one tool call. The applicant_id is locked to the file being reviewed."""
    if name not in REGISTRY:
        return {"error": f"Unknown tool {name}"}
    if "applicant_id" in args and args["applicant_id"] != ctx.applicant_id:
        ctx.emit(agent, "security", message=f"Blocked access to another applicant's file "
                                            f"('{args['applicant_id']}'); locked to '{ctx.applicant_id}'.")
        args = {**args, "applicant_id": ctx.applicant_id}
    try:
        result = REGISTRY[name](**args)
    except (TypeError, ValueError, KeyError) as e:
        result = {"error": f"{type(e).__name__}: {e}"}
    ctx.tool_facts.append(result)
    return result


def run_agent(ctx: RunContext, agent: str, *, system: str, user: str, tools: list[dict],
              final_tool: str, model: str | None = None, effort: str | None = None) -> dict:
    """Manual tool-use loop. Ends when the agent calls `final_tool` (its structured answer)."""
    model = model or config.MAIN_MODEL
    effort = effort or config.MAIN_EFFORT
    messages = [{"role": "user", "content": user}]
    ctx.emit(agent, "start", model=model)
    for turn in range(config.MAX_TOOL_TURNS):
        _guard_budget(ctx)
        resp = client().messages.create(
            model=model,
            max_tokens=8000,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            tools=tools,
            messages=messages,
            output_config={"effort": effort},
            cache_control={"type": "ephemeral"},
        )
        used = ctx.add_usage(agent, model, resp.usage)
        ctx.emit(agent, "usage", turn=turn + 1, **used)
        if resp.stop_reason == "refusal":
            raise RuntimeError(f"{agent}: model declined the request")
        messages.append({"role": "assistant", "content": resp.content})
        for b in resp.content:
            if b.type == "text" and b.text.strip():
                ctx.emit(agent, "thought", text=b.text.strip()[:600])
        calls = [b for b in resp.content if b.type == "tool_use"]
        if not calls:
            messages.append({"role": "user", "content": f"Please finish by calling {final_tool}."})
            continue
        results, final = [], None
        for c in calls:
            args = dict(c.input) if isinstance(c.input, dict) else {}
            if c.name == final_tool:
                final = args
                ctx.emit(agent, "final", tool=c.name, output=args)
                results.append({"type": "tool_result", "tool_use_id": c.id, "content": "Recorded."})
                continue
            ctx.emit(agent, "tool_call", tool=c.name, input=args)
            out = run_tool(ctx, agent, c.name, args)
            ctx.emit(agent, "tool_result", tool=c.name, output=out)
            results.append({"type": "tool_result", "tool_use_id": c.id, "content": json.dumps(out),
                            **({"is_error": True} if "error" in out else {})})
        messages.append({"role": "user", "content": results})
        if final is not None:
            return final
    raise RuntimeError(f"{agent}: stopped after {config.MAX_TOOL_TURNS} turns without an answer (loop guard)")


def run_json(ctx: RunContext, agent: str, *, system: str, user: str, schema: dict,
             model: str, effort: str = "low") -> dict:
    """Single structured-output call (used by the gatekeeper)."""
    _guard_budget(ctx)
    ctx.emit(agent, "start", model=model)
    resp = client().messages.create(
        model=model,
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    )
    used = ctx.add_usage(agent, model, resp.usage)
    ctx.emit(agent, "usage", turn=1, **used)
    text = "".join(b.text for b in resp.content if b.type == "text")
    out = json.loads(text)
    ctx.emit(agent, "final", tool="screen", output=out)
    return out
