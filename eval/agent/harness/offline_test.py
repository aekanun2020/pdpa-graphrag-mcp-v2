"""Offline checks of the PDPA hooks and verifier: real deterministic MCP calls, zero model calls."""
import json, subprocess, sys
from pathlib import Path
from types import SimpleNamespace
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src')); sys.path.insert(0, str(ROOT / 'harnesses/pdpa/hooks'))
from dfai_harness.runtime import MCPClient, canonical, digest, load_json, write_json
import pdpa
base = ROOT / 'harnesses/pdpa'
mcp = load_json(base / 'policies/mcp-main.json'); settings = load_json(base / 'policies/hook-settings.json')
run = ROOT / 'runs/offline'; (run / 'evidence').mkdir(parents=True)
c = MCPClient(mcp, 60); c.initialize()
engine = SimpleNamespace(events=[], config={'hook_settings': settings}, compiled_contract={'requirements': [
    {'id': 'R1', 'issue_type': 'lawful_basis', 'description': 'x', 'question_span_id': 'S001'},
    {'id': 'R2', 'issue_type': 'penalty', 'description': 'y', 'question_span_id': 'S001'}]})
def call(name, args, origin='agent'):
    pre = pdpa.pre_tool_use(engine, name, args)
    if pre: return None, pre
    r = c.call(name, args); ok, post = pdpa.post_tool_use(engine, name, args, r)
    eid = f'E{len(engine.events)+1:04d}'
    e = {'evidence_id': eid, 'origin': origin, 'tool': name, 'arguments': args, 'result': r, 'admitted': ok, 'result_sha256': digest(canonical(r).encode())}
    engine.events.append(e); write_json(run / 'evidence' / f'{eid}-{name}.json', e); return eid, post
checks = []
def check(label, cond): checks.append((label, bool(cond))); print(('PASS ' if cond else 'FAIL ') + label)
check('no evidence yet', pdpa.evidence_errors(engine))
e1, _ = call('get_section_text', {'section_id': 'sec_26'})
e2, _ = call('get_penalty', {'section_id': 'sec_26'})
e3, post = call('get_section_text', {'section_id': 'sec_999'})
check('not-found section is not admitted', post and not engine.events[-1]['admitted'])
check('structuredContent dropped', all('structuredContent' not in e['result'] for e in engine.events))
check('identical call rejected', call('get_section_text', {'section_id': 'sec_26'})[0] is None)
check('bad section id rejected', call('get_penalty', {'section_id': 'มาตรา 26'})[0] is None)
check('top_k bound', call('search_pdpa', {'query': 'x', 'top_k': 50})[0] is None)
check('evidence present', not pdpa.evidence_errors(engine))
good = json.dumps({'answer': f'ทำได้เมื่อได้รับความยินยอมโดยชัดแจ้งตามมาตรา ๒๖ ({e1}) โทษตามมาตรา 79 ({e2})',
                   'bindings': [{'requirement_id': 'R1', 'evidence_ids': [e1]}, {'requirement_id': 'R2', 'evidence_ids': [e2]}]}, ensure_ascii=False)
check('good draft accepted', not pdpa.completion_errors(engine, good))
def errs(answer, bindings): return pdpa.completion_errors(engine, json.dumps({'answer': answer, 'bindings': bindings}, ensure_ascii=False))
both = [{'requirement_id': 'R1', 'evidence_ids': [e1]}, {'requirement_id': 'R2', 'evidence_ids': [e2]}]
x = errs('ตามมาตรา 26 และมาตรา 41', both); check('ungrounded section rejected and opens tools', x and pdpa.repair_needs_tools(engine, x))
check('unadmitted evidence cannot be bound', errs('มาตรา 26', [{'requirement_id': 'R1', 'evidence_ids': [e3]}, {'requirement_id': 'R2', 'evidence_ids': [e2]}]))
check('missing requirement rejected', errs('มาตรา 26', both[:1]))
check('penalty needs penalty evidence', errs('มาตรา 26', [{'requirement_id': 'R1', 'evidence_ids': [e1]}, {'requirement_id': 'R2', 'evidence_ids': [e1]}]) and True)
check('citation outside bindings rejected', errs(f'มาตรา 26 ({e1}) E0009', both))
check('no section cited rejected', errs('ทำได้', both))
check('fenced draft parses', not pdpa.completion_errors(engine, '```json\n' + good + '\n```'))
check('section parsing', pdpa.cited_sections('มาตรา ๒๔ (๕) และ ม. 37 จำคุก 6 เดือน') == {24, 37} and {26, 27, 28} <= pdpa.shown_sections('มาตรา 26, 27 และ 28 sec_79'))
(run / 'investigation.md').write_text(good + '\n'); write_json(run / 'mcp-policy.json', mcp)
out = subprocess.run([sys.executable, '-B', str(base / 'hooks/verify.py'), '--harness', str(base / 'harness.json'), '--run-dir', str(run)], capture_output=True, text=True)
print(out.stdout[-300:], out.stderr[-800:])
receipt = load_json(run / 'verifier/receipt.json'); report = (run / 'verifier/report.md').read_text()
check('verifier reread matched', out.returncode == 0 and receipt['status'] == 'reread_matched' and len(receipt['replayed']) == 2 and [s['section'] for s in receipt['sections']] == [26, 79])
final = f'ทำได้ตามมาตรา 26 โทษตามมาตรา 79\n\nหลักฐานที่ใช้: {e1}, {e2}'
check('synthesis accepted', not pdpa.synthesis_errors(engine, final, good, report))
check('synthesis with unverified section rejected', pdpa.synthesis_errors(engine, final.replace('มาตรา 79', 'มาตรา 95'), good, report))
check('synthesis dropping an id rejected', pdpa.synthesis_errors(engine, final.replace(', ' + e2, ''), good, report))
c.close(); print(sum(ok for _, ok in checks), 'of', len(checks), 'passed'); sys.exit(0 if all(ok for _, ok in checks) else 1)
