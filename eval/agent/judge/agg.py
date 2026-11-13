import json, glob, re, sys
from pathlib import Path
S = Path(sys.argv[1]); J = S / "judge"; key = json.loads((J / "key.json").read_text())
TH = str.maketrans("0123456789", "๐๑๒๓๔๕๖๗๘๙")
def raw_evidence(run, server, qid):
    out = ""
    for f in sorted(glob.glob(str(S / f"results/{run}/{server}/{qid}/evidence/*.json"))):
        e = json.loads(Path(f).read_text())
        if e.get("admitted", True):
            try: out += "\n" + e["result"]["content"][0]["text"].encode().decode("unicode_escape", "ignore") if False else "\n" + json.dumps(json.loads(e["result"]["content"][0]["text"]), ensure_ascii=False)
            except Exception: out += "\n" + str(e.get("result"))
    return out
tot = {}; rows = []
for code, (run, server, qid) in sorted(key.items(), key=lambda kv: (kv[1][2], kv[1][1])):
    p = J / "out" / f"{code}.json"
    if not p.exists(): print("MISSING", code, run, server, qid); continue
    d = json.loads(p.read_text()); ev = raw_evidence(run, server, qid)
    nie = [x for x in d["problems"] if x["type"] == "not_in_evidence"]
    confirmed = []
    for x in nie:
        n = x.get("law_section"); 
        try: n = int(n)
        except Exception: n = None
        present = bool(n) and (f"มาตรา {str(n).translate(TH)} " in ev)
        x["_text_in_raw_evidence"] = present
        if not present: confirmed.append(x)
    k = f"{run}:{server}"; t = tot.setdefault(k, dict(n=0, claims=0, correct=0, partly=0, wrong=0, cit=0, nie=0, nie_confirmed=0, c_correct=0, c_partly=0, c_wrong=0, keyuse=0))
    t["n"] += 1; t["claims"] += d["n_claims"]; t["correct"] += d["n_correct"]; t["partly"] += d["n_partly"]; t["wrong"] += d["n_wrong"]; t["cit"] += d["n_citation_wrong"]
    t["nie"] += d["n_not_in_evidence"]; t["nie_confirmed"] += len(confirmed) + max(0, d["n_not_in_evidence"] - len(nie)); t["c_" + d["conclusion"]] += 1; t["keyuse"] += bool(d["uses_key_sections"])
    rows.append((qid, server, run, code, d, confirmed))
for k, t in tot.items(): print(k, t)
print()
for qid, server, run, code, d, conf in rows:
    flag = d["n_partly"] or d["n_wrong"] or d["n_citation_wrong"] or d["n_not_in_evidence"] or d["conclusion"] != "correct"
    print(f"{qid:4} {server:6} {code} claims={d['n_claims']} partly={d['n_partly']} wrong={d['n_wrong']} cit={d['n_citation_wrong']} nie={d['n_not_in_evidence']}(confirmed {len(conf)}) concl={d['conclusion']} key={d['uses_key_sections']}")
    if "-v" in sys.argv and flag:
        if d["conclusion"] != "correct": print("      CONCL:", d["conclusion_reason"])
        for x in d["problems"]:
            print(f"      [{x['type']}{'' if x['type']!='not_in_evidence' else (' raw-present' if x['_text_in_raw_evidence'] else ' CONFIRMED')}] ม.{x.get('law_section')} «{x['quote'][:110]}» — {x['why'][:260]}")
json.dump([{"id": q, "server": s, "run": r, "code": c, **d} for q, s, r, c, d, _ in rows], open(J / "judged.json", "w"), ensure_ascii=False, indent=1)
