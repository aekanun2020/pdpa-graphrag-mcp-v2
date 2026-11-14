"""Run labs/lab8 unchanged over a list of questions and record what it did.

lab8 prints only tool names and arguments. This wrapper calls lab8's own run_agent() and SYSTEM prompt, and
records, without changing lab8: every tool result the agent received, every model response's metadata, the
printed transcript, the final answer and the time taken. A question that crashes (for example an MCP timeout,
which lab8 does not handle) is recorded as an error, as a learner would see it.

Run from the repo root (the folder that contains labs/ and .env), with the agent venv:
    MCP_SERVER_URL=http://127.0.0.1:8100/mcp python eval/lab8/run_lab8.py <questions.json> <out dir> [ID ...]
"""
import contextlib, io, json, os, sys, time, traceback
from pathlib import Path

sys.path.insert(0, os.getcwd())
import labs.lab8.agent_pdpa_mcp as L          # noqa: E402
from labs.core import config                   # noqa: E402
from labs.core.registry import ToolRegistry    # noqa: E402

qfile, out = Path(sys.argv[1]), Path(sys.argv[2]); ids = sys.argv[3:]
out.mkdir(parents=True, exist_ok=True)
questions = [q for q in json.loads(qfile.read_text()) if not ids or q["id"] in ids]
orig_chat = L.llm.chat

for q in questions:
    dst = out / f"{q['id']}.json"
    if dst.exists():
        print("skip", q["id"]); continue
    rec = {"id": q["id"], "question": q["q"], "mcp_server_url": config.MCP_SERVER_URL,
           "agent_model_setting": config.OPENROUTER_MODEL, "tool_calls": [], "model_calls": []}

    def chat(*a, _rec=rec, **k):
        t = time.time(); resp = orig_chat(*a, **k)
        d = resp.model_dump() if hasattr(resp, "model_dump") else {}
        _rec["model_calls"].append({"seconds": round(time.time() - t, 2), "model": d.get("model"),
                                    "provider": d.get("provider"), "usage": d.get("usage"),
                                    "finish_reason": (d.get("choices") or [{}])[0].get("finish_reason")})
        return resp

    L.llm.chat = chat
    buf = io.StringIO(); t0 = time.time(); registry = None
    try:
        with contextlib.redirect_stdout(buf):
            registry = ToolRegistry(); registry.add_server(config.MCP_SERVER_URL)
            orig_dispatch = registry.dispatch

            def dispatch(name, args, _rec=rec, _orig=orig_dispatch):
                t = time.time(); res = _orig(name, args)
                _rec["tool_calls"].append({"name": name, "arguments": args, "seconds": round(time.time() - t, 2), "result": res})
                return res

            registry.dispatch = dispatch
            ans = L.run_agent(q["q"], registry)
        rec["status"] = "ok" if ans else "no_answer"; rec["answer"] = ans
    except Exception as e:  # what a learner would see as a traceback
        rec["status"] = "error"; rec["answer"] = None
        rec["error"] = f"{type(e).__name__}: {e}"; rec["traceback"] = traceback.format_exc()[-3000:]
    finally:
        L.llm.chat = orig_chat
        if registry is not None:
            with contextlib.suppress(Exception): registry.close()
    rec["seconds"] = round(time.time() - t0, 1); rec["transcript"] = buf.getvalue()
    dst.write_text(json.dumps(rec, ensure_ascii=False, indent=1))
    print(q["id"], rec["status"], f"{rec['seconds']}s", "tools", len(rec["tool_calls"]), "model calls", len(rec["model_calls"]), flush=True)
