"""Build blind review packets for two systems answering the same questions.

Both systems' packets are built with the same evidence rules, then shuffled under random codes so a
reviewer cannot tell which system wrote an answer. Format follows eval/agent/judge/RUBRIC.md.

Usage: python3 build_blind.py <lab8 runs dir> <harness runs dir (…/r3/main)> <questions.json> <gold.json> <out dir>
"""
import json, glob, random, re, sys
from pathlib import Path
lab8, harness, qfile, gfile, out = map(Path, sys.argv[1:6])
(out / "packets").mkdir(parents=True, exist_ok=True); (out / "out").mkdir(exist_ok=True)
gold = json.loads(gfile.read_text()); questions = {q["id"]: q["q"] for q in json.loads(qfile.read_text())}
TH = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")

def evidence(calls):
    """calls: list of (tool name, arguments, result text). Returns (sections with full text, other results)."""
    seen, small = set(), []
    for name, args, res in calls:
        if name == "get_section_text":
            try:
                d = json.loads(res)
                if d.get("text"): seen.add(int(d["number"]))
            except Exception: pass
        elif name == "search_pdpa":
            try: ctx = json.loads(res)["context"]
            except Exception: ctx = res
            head, _, tail = ctx.partition("## เนื้อหาต้นฉบับ PDPA")
            seen.update(int(n.translate(TH)) for n in re.findall(r"^### .*?มาตรา ([๐-๙]+):", tail, flags=re.M))
            small.append(f"[search_pdpa {json.dumps(args, ensure_ascii=False)} — graph part of the context]\n{head[:7000]}")
        elif name != "get_pdpa_summary":
            small.append(f"[{name} {json.dumps(args, ensure_ascii=False)}]\n{res[:6000]}")
    return seen, small

items = []
for f in sorted(glob.glob(str(lab8 / "*.json"))):
    r = json.loads(Path(f).read_text())
    if r.get("answer"):
        items.append(("lab8", r["id"], r["answer"], [(c["name"], c["arguments"], c["result"]) for c in r["tool_calls"]], set()))
for d in sorted(glob.glob(str(harness / "*"))):
    d = Path(d); a = d / "answer.md"
    if not a.exists() or not (d / "receipt.json").exists(): continue
    calls = []
    for f in sorted(glob.glob(str(d / "evidence" / "E*.json"))):
        e = json.loads(Path(f).read_text())
        if not e.get("admitted", True): continue
        try: txt = e["result"]["content"][0]["text"]
        except Exception: continue
        calls.append((e.get("tool") or Path(f).stem.split("-", 1)[-1], e.get("arguments") or {}, txt))
    # Sections the verifier re-read with get_section_text before the final answer was written:
    # their full text was given to the synthesizer, so they count as retrieved full text.
    reread = set()
    vr = d / "verifier" / "receipt.json"
    if vr.exists():
        reread = {int(x["section"]) for x in json.loads(vr.read_text()).get("sections", [])}
    items.append(("harness", d.name, a.read_text().split("## ตัวบทที่อ่านซ้ำจาก MCP")[0].strip(), calls, reread))

rng = random.Random(20261114 + 28); rng.shuffle(items); key = {}; used = set()
for system, qid, answer, calls, reread in items:
    seen, small = evidence(calls); seen |= reread
    while True:
        code = "U%03d" % rng.randrange(100, 999)
        if code not in used: used.add(code); break
    key[code] = [system, qid]
    (out / "packets" / f"{code}.md").write_text(
        f"# Packet {code}\n\n## Question\n{questions[qid]}\n\n## Reference sections expected by the answer key\n{', '.join('มาตรา %d' % g for g in gold[qid])}\n\n"
        f"## Sections whose full text the agent retrieved (the evidence set)\n{', '.join(map(str, sorted(seen))) or '(none)'}\n\n"
        f"## Other tool results the agent saw (graph lookups)\n" + ("\n\n".join(small) or "(none)") + f"\n\n## Answer to review\n\n{answer}\n")
(out / "key.json").write_text(json.dumps(key, indent=1))
import collections
print(len(key), "packets", dict(collections.Counter(v[0] for v in key.values())), "bytes", sum(p.stat().st_size for p in (out / "packets").glob("*.md")))
