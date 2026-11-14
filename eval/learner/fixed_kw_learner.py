"""Learner side: build the index exactly as the server does at startup, then rerun searches with fixed keywords."""
import json, sys
src, dst = sys.argv[1], sys.argv[2]
import lightrag.retrieval as R
from lightrag.main import PDPALightRAG
rag = PDPALightRAG(); rag.build(use_llm_extract=False, use_llm_profile=False)
items = json.load(open(src)); out = []
for it in items:
    R.extract_query_keywords = lambda q, kw=it["keywords"]: kw
    r = R.retrieve(it["query"], rag.index, rag.knowledge_graph, top_k=it["top_k"])
    out.append({"qid": it["qid"], "ev": it["ev"], "context": r["context"],
                "profiles": [(p["profile"]["id"], round(float(p["score"]), 6)) for p in r["profile_results"]],
                "chunks": [(c["chunk_id"], round(float(c["score"]), 6)) for c in r["chunk_results"]]})
json.dump(out, open(dst, "w"), ensure_ascii=False)
print("done", len(out))
