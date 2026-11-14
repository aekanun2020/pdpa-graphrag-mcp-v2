"""Pull every recorded search_pdpa call (query, top_k, keywords, context) and every other tool result
out of the round-11 branch runs. Usage: python3 extract_kw.py <dir with r1/> <output dir>"""
import json, glob, sys, os
T, O = sys.argv[1], sys.argv[2]; out = []; other = []
for f in sorted(glob.glob(T + "/r1/branch/*/evidence/*.json")):
    e = json.load(open(f)); qid = f.split("/")[-3]
    try: res = json.loads(e["result"]["content"][0]["text"])
    except Exception: res = None
    if e["tool"] == "search_pdpa":
        if not res or "keywords" not in res: print("skip", f); continue
        a = e["arguments"]
        out.append({"qid": qid, "ev": os.path.basename(f), "query": a["query"], "top_k": a.get("top_k", 5),
                    "keywords": res["keywords"], "context": res["context"]})
    else:
        other.append({"qid": qid, "tool": e["tool"], "arguments": e["arguments"],
                      "text": e["result"]["content"][0]["text"] if e.get("result") else None})
json.dump(out, open(O + "/kw.json", "w"), ensure_ascii=False)
json.dump(other, open(O + "/recorded_tools.json", "w"), ensure_ascii=False)
print("searches", len(out), "top_k", sorted(set(x["top_k"] for x in out)), "other tool calls", len(other))
