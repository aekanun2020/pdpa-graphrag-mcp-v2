"""Fresh re-read of what the draft relies on; no model, oracle or semantic grading.

Deterministic tools (get_section_text, get_related_sections, get_penalty) are called again with the
same arguments and must return the same text. search_pdpa is not replayed: the server extracts
keywords with a language model, so a second call is neither free nor guaranteed identical; its
recorded result is checked against its stored hash only. Every section the draft cites is then read
from the server with get_section_text, and that text is the verified report the synthesizer uses.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'src'))
from dfai_harness.runtime import MCPClient, canonical, digest, load_json, write_json, require
from pdpa import text_result, parse_draft, cited_sections, SECTION_TOOLS


def main():
    p = argparse.ArgumentParser(); p.add_argument('--harness', type=Path, required=True); p.add_argument('--run-dir', type=Path, required=True)
    args = p.parse_args(); base = args.harness.resolve().parent
    config = load_json(args.harness); policies = {k: load_json(base / v) for k, v in config['policy_files'].items()}
    run = args.run_dir.resolve()
    # The launcher swaps the MCP policy per run (which server build is under test); replay must hit the same one.
    mcp = load_json(run / 'mcp-policy.json'); settings = policies['hook_settings']
    output = run / 'verifier'; output.mkdir(exist_ok=False)
    c = MCPClient(mcp, mcp['timeout_seconds'])
    receipt = {'status': 'failed', 'semantic_assessment': 'not_assessed', 'model_calls': 0, 'oracle_answer_used': False,
               'endpoint': mcp['endpoint'], 'replayed': [], 'not_replayed': [], 'sections': []}
    try:
        init = c.initialize()
        require(init['serverInfo'] == {'name': mcp['server_name'], 'version': mcp['server_version']}, 'Server identity changed')
        draft = parse_draft((run / policies['run']['draft_artifact']).read_text())
        ids = sorted({eid for b in draft['bindings'] for eid in b['evidence_ids']})
        require(bool(ids), 'No bound evidence')
        events = {e['evidence_id']: e for f in (run / 'evidence').glob('*.json') for e in [load_json(f)]}
        report = ['การอ่านซ้ำยืนยันว่าตัวบทที่อ้างมีอยู่จริงใน MCP server และผลของเครื่องมือที่ให้ผลคงที่ตรงกับหลักฐานก่อนตอบ ไม่ใช่การตรวจความถูกต้องทางกฎหมาย']
        penalties = []
        for eid in ids:
            e = events[eid]
            require(e['admitted'], 'Unadmitted bound evidence')
            require(digest(canonical(e['result']).encode()) == e['result_sha256'], 'Evidence hash mismatch')
            if e['tool'] not in SECTION_TOOLS:
                receipt['not_replayed'].append({'evidence_id': eid, 'tool': e['tool'], 'reason': 'retrieval uses a language model for keywords; stored hash checked only'})
                continue
            raw = c.call(e['tool'], e['arguments']); raw.pop('structuredContent', None)
            write_json(output / f'{eid}.json', raw)
            require(text_result(raw) == text_result(e['result']), f'{eid}: replay differs from evidence')
            receipt['replayed'].append({'evidence_id': eid, 'tool': e['tool'], 'arguments': e['arguments'], 'matched': True})
            if e['tool'] == 'get_penalty':
                penalties.append((eid, json.loads(text_result(raw))))
        sections = sorted(cited_sections(draft['answer']))
        require(0 < len(sections) <= settings['max_verifier_sections'], 'Cited-section count outside verifier budget')
        report.append('### ตัวบทของมาตราที่ร่างคำตอบอ้าง (อ่านใหม่ด้วย get_section_text)')
        for number in sections:
            raw = c.call('get_section_text', {'section_id': f'sec_{number}'}); raw.pop('structuredContent', None)
            write_json(output / f'section-{number}.json', raw)
            value = json.loads(text_result(raw))
            require(value.get('found') is not False and not value.get('error') and isinstance(value.get('text'), str), f'มาตรา {number} is not in the server')
            receipt['sections'].append({'section': number, 'text_sha256': digest(value['text'].encode())})
            report.append(f"**มาตรา {number}** (sec_{number})\n\n{value['text']}")
        if penalties:
            report.append('### ผลของ get_penalty ที่ผูกไว้ (อ่านซ้ำแล้วตรงกัน)')
            for eid, value in penalties:
                lines = [f"- {x.get('description')} — เส้นทาง {x.get('path')}" for x in value.get('penalties', [])] or ['- กราฟไม่มีเส้นเชื่อมไปยังโทษจากมาตรานี้ (ไม่ได้แปลว่ากฎหมายไม่มีโทษ)']
                report.append(f"{eid}: get_penalty({value.get('section_id')})\n" + '\n'.join(lines))
        if receipt['not_replayed']:
            report.append('ผลของ search_pdpa (' + ', '.join(x['evidence_id'] for x in receipt['not_replayed']) + ') ไม่ได้เรียกซ้ำ ตรวจเฉพาะ hash ของผลที่บันทึกไว้')
        receipt['status'] = 'reread_matched'
        answer = output / 'report.md'; answer.write_text('\n\n'.join(report) + '\n')
        print('Answer:', answer)
        print('Receipt:', output / 'receipt.json')
    finally:
        write_json(output / 'receipt.json', receipt); c.close()


if __name__ == '__main__':
    main()
