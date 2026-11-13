"""Build blind review packets: one file per finished run, coded so the reviewer cannot tell which build produced it."""
import json, glob, os, re, random, sys
from pathlib import Path
S = Path(sys.argv[1]); J = S / "judge"; P = J / "packets"; P.mkdir(exist_ok=True)
tags = sys.argv[2:]  # e.g. r1:main r1:branch r2:main
qs = {q["id"]: q["q"] for q in json.loads((S / "questions.json").read_text())}
gold = json.loads((S / "gold.json").read_text())
keyp = J / "key.json"; key = json.loads(keyp.read_text()) if keyp.exists() else {}
rng = random.Random(20261114); used = set(key)
for tag in tags:
    run, server = tag.split(":")
    for d in sorted(glob.glob(str(S / f"results/{run}/{server}/*"))):
        a = Path(d) / "answer.md"
        if not a.exists() or any(v == [run, server, Path(d).name] for v in key.values()): continue
        qid = Path(d).name; syn = a.read_text().split("## ตัวบทที่อ่านซ้ำจาก MCP")[0].strip()
        seen, small = set(), []
        for f in sorted(glob.glob(d + "/evidence/*.json")):
            e = json.loads(Path(f).read_text())
            if not e.get("admitted", True): continue
            try: txt = e["result"]["content"][0]["text"]
            except Exception: continue
            tool = e.get("tool") or Path(f).stem.split("-", 1)[1]
            if "get_section_text" in tool:
                try:
                    r = json.loads(txt)
                    if r.get("text"): seen.add(int(r["number"]))
                except Exception: pass
            elif "search_pdpa" in tool:
                try: ctx = json.loads(txt)["context"]
                except Exception: ctx = txt
                seen.update(int(n) for n in re.findall(r"— sec_(\d+):", ctx))
            elif "summary" not in tool:
                small.append(f"[{tool} {json.dumps(e.get('arguments'), ensure_ascii=False)}]\n{txt[:6000]}")
        while True:
            code = "X%03d" % rng.randrange(100, 999)
            if code not in used: used.add(code); break
        key[code] = [run, server, qid]
        (P / f"{code}.md").write_text(
            f"# Packet {code}\n\n## Question\n{qs[qid]}\n\n## Reference sections expected by the answer key\n{', '.join('มาตรา %d' % g for g in gold[qid])}\n\n"
            f"## Sections whose full text the agent retrieved (the evidence set)\n{', '.join(map(str, sorted(seen)))}\n\n"
            f"## Other tool results the agent saw (graph lookups)\n" + ("\n\n".join(small) or "(none)") + f"\n\n## Answer to review\n\n{syn}\n")
keyp.write_text(json.dumps(key, indent=1))
codes = sorted(key); print(len(codes), "packets; total bytes", sum((P / f"{c}.md").stat().st_size for c in codes))
