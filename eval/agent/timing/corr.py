"""Match each finished search_pdpa evidence file to its server-side delay; compare delay with keyword count."""
import json, re, sys, glob, os, statistics as st
from datetime import datetime, timedelta
S = sys.argv[1]
calls = []
for line in open(f"{S}/timing/main-server-r1.log", errors="replace"):
    m = re.match(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6})\d*Z (.*)", line)
    if not m: continue
    t = datetime.fromisoformat(m.group(1)) + timedelta(hours=7); x = m.group(2)
    if "CallToolRequest" in x: pend = t
    elif "_profiles/points/query" in x and pend: calls.append([pend, (t - pend).total_seconds(), None]); pend = None
    elif "_chunks/points/query" in x and calls and calls[-1][2] is None: calls[-1][2] = t
rows = []
for f in glob.glob(f"{S}/results/r1/main/*/evidence/*search_pdpa*.json"):
    d = json.load(open(f)); s = json.dumps(d, ensure_ascii=False)
    m = re.search(r'\\"keywords\\": (\{.*?\})\s*,\s*\\"', s) or re.search(r'"keywords": (\{.*?\})', s)
    n = None
    def find(o):
        if isinstance(o, dict):
            if "low_level" in o and "high_level" in o: return len(o["low_level"]) + len(o["high_level"])
            for v in o.values():
                r = find(v)
                if r is not None: return r
        elif isinstance(o, list):
            for v in o:
                r = find(v)
                if r is not None: return r
        elif isinstance(o, str) and "low_level" in o:
            try: return find(json.loads(o))
            except Exception: return None
    n = find(d); mt = datetime.fromtimestamp(os.path.getmtime(f))
    best = min(calls, key=lambda c: abs(((c[2] or c[0]) - mt).total_seconds()))
    if abs(((best[2] or best[0]) - mt).total_seconds()) < 5: rows.append((best[1], n, f.split("/main/")[1]))
rows.sort()
print("matched", len(rows), "of", len(glob.glob(f"{S}/results/r1/main/*/evidence/*search_pdpa*.json")))
for g, n, f in rows: print(f"{g:6.1f}s  keywords={n}  {f}")
xs = [(g, n) for g, n, _ in rows if n is not None]
if len(xs) > 2:
    print("pearson r =", round(st.correlation([a for a, _ in xs], [b for _, b in xs]), 2))
