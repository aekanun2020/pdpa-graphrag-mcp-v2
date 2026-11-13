"""Load a small source-verified corpus verbatim. No search or external model."""
import hashlib
import json
from pathlib import Path


def load_knowledge(root: Path, mode: str) -> tuple[str, dict]:
    if mode == 'off':
        return '', {'mode': 'off', 'entries': []}
    if mode != 'verified':
        raise ValueError('Unknown knowledge mode')
    base = (root / 'knowledge').resolve()
    manifest = json.loads((base / 'manifest.json').read_text())
    blocks = []
    receipts = []
    for entry in manifest['entries']:
        if entry['status'] != 'verified_source' or entry['kind'] not in {'database_observation', 'technical_reference'}:
            raise ValueError('Unverified or unsupported knowledge entry')
        path = (base / entry['path']).resolve()
        if not path.is_relative_to(base) or path.suffix != '.md':
            raise ValueError('Knowledge path escapes corpus')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry['sha256']:
            raise ValueError('Knowledge hash mismatch: ' + entry['id'])
        if not entry['sources']:
            raise ValueError('Knowledge has no source')
        blocks.append(f"[{entry['id']}; {entry['kind']}]\n" + raw.decode('utf-8'))
        receipts.append({k: entry[k] for k in ['id', 'kind', 'sha256', 'sources']})
    context = '\n\n'.join(blocks)
    if len(context.encode()) > manifest['max_context_bytes']:
        raise ValueError('Knowledge context exceeds explicit budget')
    return context, {'mode': mode, 'entries': receipts, 'context_sha256': hashlib.sha256(context.encode()).hexdigest()}
