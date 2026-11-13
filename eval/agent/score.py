import json, sys
from pathlib import Path
S = Path(sys.argv[1]); E = Path(sys.argv[2])
gold = json.loads(E.read_text())  # gold.json
group = {**{q: "ม.4" for q in "R1 R2 R3 R4 H1 H2 H3 Q6".split()}, **{q: "โทษ" for q in "P1 P3 P5 P7 P9 P12 N6 Q8".split()}, **{q: "อื่น" for q in "O1 O2 O7 O10 O12 O15 N3 N4".split()}}
rows = {(r["id"], r["server"]): r for r in json.loads((S/"summary.json").read_text())}
order = list(group); tot = {}
print("id grp gold | main: hit calls tools searches cost | branch: hit calls tools searches cost")
for q in order:
    line = [q, group[q], ",".join(map(str, gold[q]))]
    for s in ("main", "branch"):
        r = rows[(q, s)]; t = tot.setdefault((s, group[q]), dict(hit=0, gold=0, ok=0, n=0, calls=0, tools=0, search=0, cost=0, full=0)); a = tot.setdefault((s, "รวม"), dict(hit=0, gold=0, ok=0, n=0, calls=0, tools=0, search=0, cost=0, full=0))
        hit = [g for g in gold[q] if g in (r.get("sections") or [])]; searches = sum(x.startswith("search_pdpa") for x in r["tools"])
        for d in (t, a):
            d["n"] += 1; d["gold"] += len(gold[q]); d["hit"] += len(hit); d["ok"] += r["status"] == "ok"; d["full"] += len(hit) == len(gold[q])
            d["calls"] += r.get("model_calls", 0); d["tools"] += len(r["tools"]); d["search"] += searches; d["cost"] += r.get("cost", 0)
        line.append(f"| {'FAIL' if r['status']!='ok' else str(len(hit))+'/'+str(len(gold[q]))} {r.get('model_calls')} {len(r['tools'])} {searches} {r.get('cost')} rej{r['rejections']}/{r['synth_rejections']}" + ("" if len(hit) == len(gold[q]) or r['status']!='ok' else f" miss{sorted(set(gold[q])-set(hit))}"))
    print(" ".join(line))
for k in sorted(tot, key=lambda k: (k[1], k[0])):
    d = tot[k]; print(k[1], k[0], f"ok {d['ok']}/{d['n']} gold {d['hit']}/{d['gold']} full {d['full']}/{d['n']} calls {d['calls']} tools {d['tools']} search {d['search']} cost {d['cost']:.4f}")
