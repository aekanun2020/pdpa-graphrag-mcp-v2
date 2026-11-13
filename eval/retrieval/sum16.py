import json,collections,sys
E=sys.argv[1]
l=[x for x in open(E+'/raw16.out') if x.startswith('RESULT ')][0]
d=json.loads(l[7:]); json.dump(d,open(E+'/results_v16.json','w'),ensure_ascii=False,indent=1)
g=json.load(open('data/pdpa_knowledge_graph.json')); L={n['id']:n['label'] for n in g['nodes']}
for r in d:
    m,b,x=(r['arms'][k] for k in('main','branch','branch_code_main_kw'))
    print(r['id'],r['gold'],'| main',m['gold_ctx'],'| branch',b['gold_ctx'],'| mix',x['gold_ctx'],'| nexp',len(m['exp_nodes']),len(b['exp_nodes']),None in m['exp_nodes'],None in b['exp_nodes'])
for v in('main','branch','branch_code_main_kw'):
    lab=collections.Counter(L.get(n,'?') for r in d for n in r['arms'][v]['exp_nodes'])
    print(v,sum(len(r['arms'][v]['gold_ctx']) for r in d),'/',sum(len(r['gold']) for r in d),'in chunks',sum(len(r['arms'][v]['gold_chunks']) for r in d),'chars',sum(r['arms'][v]['ctx_chars'] for r in d),dict(lab))
