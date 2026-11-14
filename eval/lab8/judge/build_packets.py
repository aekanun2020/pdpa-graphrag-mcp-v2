"""Build review packets for lab8 runs, in the format eval/agent/judge/RUBRIC.md expects.
Usage: python3 build_packets.py <runs dir> <questions.json> <gold.json> <out dir>"""
import json, glob, random, re, sys
from pathlib import Path
runs, qfile, gfile, out = map(Path, sys.argv[1:5]); (out / "packets").mkdir(parents=True, exist_ok=True); (out / "out").mkdir(exist_ok=True)
gold = json.loads(gfile.read_text()); TH = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
rng = random.Random(20261114); key = {}; used = set()
for f in sorted(glob.glob(str(runs / "*.json"))):
    r = json.loads(Path(f).read_text())
    if not r.get("answer"): continue
    seen, small = set(), []
    for c in r["tool_calls"]:
        name, res = c["name"], c["result"]
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
            small.append(f"[search_pdpa {json.dumps(c['arguments'], ensure_ascii=False)} — graph part of the context]\n{head[:7000]}")
        elif name != "get_pdpa_summary":
            small.append(f"[{name} {json.dumps(c['arguments'], ensure_ascii=False)}]\n{res[:6000]}")
    while True:
        code = "L%03d" % rng.randrange(100, 999)
        if code not in used: used.add(code); break
    key[code] = r["id"]
    (out / "packets" / f"{code}.md").write_text(
        f"# Packet {code}\n\n## Question\n{r['question']}\n\n## Reference sections expected by the answer key\n{', '.join('มาตรา %d' % g for g in gold[r['id']])}\n\n"
        f"## Sections whose full text the agent retrieved (the evidence set)\n{', '.join(map(str, sorted(seen))) or '(none)'}\n\n"
        f"## Other tool results the agent saw (graph lookups)\n" + ("\n\n".join(small) or "(none)") + f"\n\n## Answer to review\n\n{r['answer']}\n")
(out / "key.json").write_text(json.dumps(key, indent=1))
print(len(key), "packets; bytes", sum(p.stat().st_size for p in (out / "packets").glob("*.md")))
