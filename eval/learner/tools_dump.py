"""Call the 4 tools that do not use an LLM, for sec_1..sec_96, and save raw text."""
import json, sys, urllib.request
U, dst = sys.argv[1], sys.argv[2]
H = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
def post(body):
    r = urllib.request.urlopen(urllib.request.Request(U, json.dumps(body).encode(), H), timeout=60)
    out = r.read().decode(); d = None
    for l in out.splitlines():
        l = l.strip()
        if l.startswith("data:"): l = l[5:].strip()
        if l.startswith("{"):
            try: d = json.loads(l)
            except Exception: pass
    return d
def call(name, args):
    d = post({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}})
    return d["result"]["content"][0]["text"]
res = {"get_pdpa_summary": call("get_pdpa_summary", {})}
for n in range(1, 97):
    for t in ("get_section_text", "get_related_sections", "get_penalty"):
        res[f"{t}:sec_{n}"] = call(t, {"section_id": f"sec_{n}"})
json.dump(res, open(dst, "w"), ensure_ascii=False)
print("calls", len(res))
