#!/usr/bin/env python3
"""Launcher for the PDPA harness: same runtime as bps39 (dfai_harness.runtime, unmodified),
with the harnesses/pdpa assets. --server picks which PDPA-RAG build the run talks to."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))
MODEL = 'deepseek/deepseek-v4.1-flash'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--server', choices=['main', 'branch'], required=True)
    parser.add_argument('--question-file', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--preflight', action='store_true', help='Real MCP check and summary read, zero model calls')
    args = parser.parse_args()
    from dfai_harness.runtime import Harness, load_json, write_json, require
    base = ROOT / 'harnesses/pdpa'
    engine = Harness(base / 'harness.json', ROOT / 'cases/PDPA/case.json', args.output_dir, None,
                     policy_overrides={'mcp': base / 'policies' / f'mcp-{args.server}.json'})
    engine.config.update({'model_profile': 'deepseek-v4.1-flash', 'knowledge_mode': 'off', 'finalization_mode': 'legacy',
                          'semantic_mode': 'off', 'tool_routing': 'native', 'server_build': args.server})
    engine.question_path = args.question_file.resolve()
    engine.question = engine.question_path.read_text(encoding='utf-8').strip()
    write_json(engine.run_dir / 'mcp-policy.json', engine.config['mcp'])
    try:
        allow = load_json(engine.resolve(engine.config['models']['allowlist_file']))['allowed']
        roles = engine.config['models']['roles']
        print('Resolved models:', json.dumps(roles), flush=True)
        require(allow == [MODEL] and set(roles) == {'contract_compiler', 'agent', 'synthesizer'} and all(x == MODEL for x in roles.values()), 'Model policy mismatch')
        for variable in engine.config['models']['guard_environment_variables']:
            require(os.environ.get(variable, MODEL) == MODEL, f'Unauthorized {variable}')
            os.environ[variable] = MODEL
        if args.preflight:
            tools = engine.initialize_mcp()
            context = engine.hooks.prepare_contract_context(engine)
            write_json(engine.run_dir / 'preflight.json', {'status': 'passed', 'model_calls': 0, 'endpoint': engine.mcp.endpoint,
                       'tools': [t['name'] for t in tools], 'graph': {k: context['pdpa_summary']['knowledge_graph'][k] for k in ('nodes', 'edges')},
                       'question_spans': len(context['question_spans']), 'resolved_models': roles})
            print('Preflight:', engine.run_dir / 'preflight.json')
        else:
            answer, receipt = engine.run()
            print('Answer:', answer); print('Receipt:', receipt)
        return 0
    except Exception as exc:
        write_json(engine.run_dir / 'failure.json', {'status': 'failed', 'phase': engine.phase, 'error_type': type(exc).__name__, 'error': str(exc)})
        print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        return 2
    finally:
        write_json(engine.run_dir / 'agent-transcript.json', engine.transcript)
        if engine.model is not None:
            write_json(engine.run_dir / 'usage.json', {'attempted_model_calls': engine.model.calls, 'usage': engine.model.usage})
        engine.close()


if __name__ == '__main__':
    raise SystemExit(main())
