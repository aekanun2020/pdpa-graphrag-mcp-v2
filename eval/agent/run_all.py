"""Run questions through the PDPA harness against both server builds. Resumable; one line per run."""
import argparse, json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
HERE = Path(__file__).resolve().parent; H = HERE / "harness"
p = argparse.ArgumentParser(); p.add_argument("--ids", required=True); p.add_argument("--tag", default="r1")
p.add_argument("--servers", default="main,branch"); a = p.parse_args()
questions = {q["id"]: q for q in json.loads((HERE / "questions.json").read_text())}
env = {k: v for k, v in os.environ.items() if k not in ("OPENROUTER_MODEL", "OBSERVER_MODEL", "ROUTER_MODEL", "CONTRACT_AUTHOR_MODEL", "SEMANTIC_REVIEWER_MODEL")}
env["PYTHONDONTWRITEBYTECODE"] = "1"; env["PYTHONUNBUFFERED"] = "1"
(H / "questions").mkdir(exist_ok=True)
def one(qid, server):
    out = H / "runs" / a.tag / server / qid
    if (out / "receipt.json").exists() or (out / "failure.json").exists():
        return f"{qid} {server} skipped (already run)"
    qf = H / "questions" / f"{qid}.txt"; qf.write_text(questions[qid]["q"] + "\n", encoding="utf-8")
    out.parent.mkdir(parents=True, exist_ok=True); t = time.time()
    try:
        r = subprocess.run([sys.executable, "-B", str(H / "run_pdpa.py"), "--server", server, "--question-file", str(qf), "--output-dir", str(out)],
                           env=env, cwd=str(H), capture_output=True, text=True, timeout=1200)
        (out / "launcher-output.txt").write_text(r.stdout[-20000:] + "\n--- stderr\n" + r.stderr[-20000:])
        tail = r.stderr.strip().splitlines()[-1][:200] if r.returncode and r.stderr.strip() else ""
        status = "ok" if r.returncode == 0 else "FAILED " + tail
    except subprocess.TimeoutExpired:
        status = "TIMEOUT"
    calls = "?"
    try: calls = json.loads((out / "usage.json").read_text())["attempted_model_calls"]
    except Exception: pass
    return f"{qid} {server} {status} model_calls={calls} {time.time()-t:.0f}s"
servers = a.servers.split(",")
with ThreadPoolExecutor(max_workers=len(servers)) as pool:
    for qid in a.ids.split(","):
        for line in pool.map(lambda s: one(qid, s), servers):
            print(line, flush=True)
