"""Second PDPA-RAG server process for evaluation: the image's own code with lightrag/retrieval.py
taken from the branch, on 127.0.0.1:8101. It reads the Qdrant collections the running server
built and never writes to Qdrant: the two build_* methods are replaced by in-memory assignments."""
import importlib.util, os, runpy, sys
os.environ["PORT"] = "8101"; os.environ["HOST"] = "127.0.0.1"
os.chdir("/app"); sys.path.insert(0, "/app")
HERE = os.path.dirname(os.path.abspath(__file__))
import lightrag.vector_index as vi
client_probe = vi.QdrantClient(host=vi.QDRANT_HOST, port=vi.QDRANT_PORT)
for name in (vi.PROFILE_COLLECTION, vi.CHUNK_COLLECTION):
    count = client_probe.count(name).count if client_probe.collection_exists(name) else 0
    print(f"collection {name}: {count} points", flush=True)
    if count == 0:
        raise SystemExit(f"{name} is missing or empty; refusing to start")
vi.VectorIndex.build_profiles = lambda self, profiles: setattr(self, "profiles", profiles)
vi.VectorIndex.build_chunks = lambda self, chunk_store: setattr(self, "chunk_store", chunk_store)
spec = importlib.util.spec_from_file_location("lightrag.retrieval", os.path.join(HERE, "branch", "retrieval.py"))
module = importlib.util.module_from_spec(spec); sys.modules["lightrag.retrieval"] = module; spec.loader.exec_module(module)
assert hasattr(module, "_asks_about_penalty"), "branch retrieval not loaded"
open(os.path.join(HERE, "serve_branch.pid"), "w").write(str(os.getpid()))
print("branch retrieval loaded; starting server on 127.0.0.1:8101", flush=True)
runpy.run_path("/app/mcp_server_rag.py", run_name="__main__")
