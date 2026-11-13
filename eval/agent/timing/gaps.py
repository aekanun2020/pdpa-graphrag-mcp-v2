"""Gap between a CallToolRequest and the first Qdrant profile query that follows it = time before vector search (keyword LLM call + first embedding)."""
import re, sys, statistics as st
from datetime import datetime
def main_events(path):
    for line in open(path, errors="replace"):
        m = re.match(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6})\d*Z (.*)", line)
        if m: yield datetime.fromisoformat(m.group(1)), m.group(2)
def branch_events(path):
    cur = None
    for line in open(path, errors="replace"):
        m = re.match(r"\[(\d\d/\d\d/\d\d \d\d:\d\d:\d\d)\]", line)
        if m: cur = datetime.strptime(m.group(1), "%m/%d/%y %H:%M:%S")
        if cur: yield cur, line
def gaps(events):
    out, pending, prev = [], None, ""
    for t, text in events:
        if "CallToolRequest" in text and "Processing request" in prev: pending = t   # type is on the continuation line
        elif "CallToolRequest" in text: pending = t
        elif "_profiles/points/query" in text or ("collections/pdpa" in text and pending and "POST" in prev and False):
            if pending: out.append((pending, (t - pending).total_seconds())); pending = None
        prev = text
    return out
for name, ev in (("main", main_events(sys.argv[1])), ("branch", branch_events(sys.argv[2]))):
    g = gaps(ev); v = sorted(x for _, x in g)
    if not v: print(name, "no data"); continue
    q = lambda p: v[min(len(v)-1, int(p*len(v)))]
    print(f"{name}: n={len(v)} median={st.median(v):.1f}s mean={st.mean(v):.1f}s p90={q(.9):.1f}s max={v[-1]:.1f}s over60={sum(x>60 for x in v)} over110={sum(x>110 for x in v)}")
    for t, x in g:
        if x > 60: print("   ", t.strftime("%H:%M:%S"), f"{x:.1f}s")
