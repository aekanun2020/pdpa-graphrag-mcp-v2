import json, re, sys
from pathlib import Path
root = Path(sys.argv[1]); TH = str.maketrans('๐๑๒๓๔๕๖๗๘๙', '0123456789')
def secs(t): return sorted({int(n) for n in re.findall(r'(?:มาตรา|ม\.)\s*(\d{1,3})(?!\d)', t.translate(TH))})
rows = []
for run in sorted(root.glob('*/*')):
    server, qid = run.parent.name, run.name
    row = {'id': qid, 'server': server, 'status': 'ok' if (run/'receipt.json').exists() else 'failed'}
    if (run/'failure.json').exists(): row['error'] = json.loads((run/'failure.json').read_text())
    if (run/'usage.json').exists():
        u = json.loads((run/'usage.json').read_text()); row['model_calls'] = u['attempted_model_calls']
        row['prompt_tokens'] = sum(x.get('prompt_tokens', 0) for x in u['usage']); row['completion_tokens'] = sum(x.get('completion_tokens', 0) for x in u['usage'])
        row['cost'] = round(sum(x.get('cost', 0) or 0 for x in u['usage']), 5)
    ev = [json.loads(f.read_text()) for f in sorted((run/'evidence').glob('*.json'))] if (run/'evidence').exists() else []
    row['tools'] = [f"{e['tool']}({(e['arguments'].get('section_id') or e['arguments'].get('query') or '')[:40]}){'' if e['admitted'] else '✗'}" for e in ev if e['origin'] == 'agent']
    row['rejections'] = len(list((run/'hook-rejections').glob('*.json'))) if (run/'hook-rejections').exists() else 0
    row['synth_rejections'] = len(list((run/'synthesis-rejections').glob('*.json'))) if (run/'synthesis-rejections').exists() else 0
    if (run/'compiled-task-contract.json').exists():
        row['requirements'] = [(r['issue_type'], r['description'][:80]) for r in json.loads((run/'compiled-task-contract.json').read_text())['requirements']]
    if (run/'answer.md').exists():
        synth = (run/'answer.md').read_text().split('## ตัวบทที่อ่านซ้ำจาก MCP')[0]; row['answer'] = synth.strip(); row['sections'] = secs(synth)
    rows.append(row)
json.dump(rows, open(root/'summary.json', 'w'), ensure_ascii=False, indent=1)
for r in rows:
    print(f"{r['id']} {r['server']} {r['status']} calls={r.get('model_calls')} in={r.get('prompt_tokens')} out={r.get('completion_tokens')} cost={r.get('cost')} rej={r['rejections']}/{r['synth_rejections']} sections={r.get('sections')}")
    print('   tools:', ' | '.join(r['tools']))
