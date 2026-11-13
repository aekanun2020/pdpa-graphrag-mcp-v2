import json,sys
E=sys.argv[1]
s=open(E+'/run_eval15.py').read()
head,body=s.split("\nimport json, re, sys, types\n",1)
ns={}; exec(head,ns)
d=json.load(open(E+'/results_v15.json'))
ITEMS=[{"id":r["id"],"q":r["q"],"gold":r["gold"],"kw":r["kw"]} for r in d]
ls=body.split("\n"); i=[k for k,l in enumerate(ls) if l.strip().startswith('lines=[l for l in r["context"]')]
assert len(i)==1
ls[i[0]]='''    pi=m._asks_about_penalty(q,kw) if hasattr(m,"_asks_about_penalty") else None
    lines=m._expand_from_graph(r["profile_results"],G,max_expand=3,max_hops=2,**({"penalty_intent":pi} if pi is not None else {}))
    assert all(l in r["context"] for l in lines)'''
body="\n".join(ls)
b='kws={n:KW[n](it["q"]) for n in M}'; assert b in body
body=body.replace(b,'kws=it["kw"]')
open(E+'/run_eval16.py','w').write("ITEMS=%r\nMAIN_SRC=%r\nBRANCH_SRC=%r\n"%(ITEMS,ns['MAIN_SRC'],ns['BRANCH_SRC'])+"import json, re, sys, types\n"+body)
