"""PDPA policy hooks. Structural admission is not a judgment of legal correctness."""
from __future__ import annotations
import json
import re
from collections import Counter

SECTION_TOOLS = {'get_section_text', 'get_related_sections', 'get_penalty'}
RETRIEVAL_TOOLS = SECTION_TOOLS | {'search_pdpa'}
THAI_DIGITS = str.maketrans('๐๑๒๓๔๕๖๗๘๙', '0123456789')
# Answer side: the number directly after มาตรา / ม. (one citation, one number).
CITED_SECTION = re.compile(r'(?:มาตรา|ม\.)\s*(\d{1,3})(?!\d)')
# Evidence side: also node ids and the numbers a list continues with ("มาตรา 26, 27 และ 28").
SHOWN_LIST = re.compile(r'(?:มาตรา|ม\.)\s*(\d{1,3}(?:\s*(?:,|และ|หรือ|ถึง|-|–)\s*(?:มาตรา|ม\.)?\s*\d{1,3})*)')
SHOWN_NODE = re.compile(r'\bsec_(\d{1,3})\b')
NOT_SHOWN = 'no bound evidence shows'


def text_result(result):
    if result.get('isError'):
        raise ValueError('MCP isError')
    blocks = result.get('content')
    if not isinstance(blocks, list) or not blocks:
        raise ValueError('Missing MCP content')
    if any(x.get('type') != 'text' or not isinstance(x.get('text'), str) for x in blocks):
        raise ValueError('Unsupported MCP result content')
    text = '\n'.join(x['text'] for x in blocks)
    if not text.strip():
        raise ValueError('Empty MCP result')
    return text


def cited_sections(text):
    return {int(n) for n in CITED_SECTION.findall(text.translate(THAI_DIGITS))}


def shown_sections(text):
    text = text.translate(THAI_DIGITS)
    found = {int(n) for n in SHOWN_NODE.findall(text)}
    for group in SHOWN_LIST.findall(text):
        found.update(int(n) for n in re.findall(r'\d{1,3}', group))
    return found


def question_spans(question):
    """Exact source spans without case IDs, domain vocabulary or references."""
    options = [question]
    matches = list(re.finditer(r'[^\s?;\n]+', question))
    for i, first in enumerate(matches):
        for last in matches[i:i+4]:
            options.append(question[first.start():last.end()])
    return {f'S{i:03d}': text for i, text in enumerate(dict.fromkeys(x for x in options if x.strip()), 1)}


def prepare_contract_context(engine):
    result = engine.invoke_hook_tool('get_pdpa_summary', {})
    summary = json.loads(text_result(result))
    if not isinstance(summary.get('knowledge_graph'), dict):
        raise ValueError('Missing live PDPA summary')
    return {'pdpa_summary': summary, 'summary_evidence_id': engine.events[-1]['evidence_id'],
            'question_spans': question_spans(engine.question)}


def prepare_contract_schema(engine, schema):
    import copy
    schema = copy.deepcopy(schema)
    schema['properties']['task_id']['enum'] = [engine.case_metadata['case_id']]
    schema['properties']['question']['enum'] = [engine.question]
    spans = question_spans(engine.question)
    schema['properties']['requirements']['items']['properties']['question_span_id']['enum'] = list(spans)
    (engine.run_dir / 'question-spans.json').write_text(json.dumps(spans, ensure_ascii=False, indent=2) + '\n')
    return schema


def validate_compiled_contract(engine, contract):
    errors = []
    if contract.get('task_id') != engine.case_metadata['case_id']:
        errors.append('task_id differs from selected case')
    if contract.get('question') != engine.question:
        errors.append('question differs from the exact source question')
    requirements = contract.get('requirements', [])
    if not 1 <= len(requirements) <= engine.config['hook_settings']['max_requirements']:
        errors.append('Requirement count outside policy')
    spans = question_spans(engine.question)
    ids = []
    for r in requirements:
        ids.append(r.get('id'))
        if not re.fullmatch(r'R[1-9][0-9]*', str(r.get('id', ''))):
            errors.append('Invalid requirement id')
        if r.get('question_span_id') not in spans:
            errors.append('Requirement must select a question_span_id from the supplied source map')
        if not str(r.get('description', '')).strip():
            errors.append('Requirement description missing')
        if cited_sections(str(r.get('description', ''))):
            errors.append(f"{r.get('id')}: a requirement must not name a section number; describe what must be found")
    if len(set(ids)) != len(ids):
        errors.append('Duplicate requirement id')
    return errors


def pre_tool_use(engine, name, arguments):
    settings = engine.config['hook_settings']
    errors = []
    if name in SECTION_TOOLS:
        if not re.fullmatch(r'(sec_)?\d{1,3}', str(arguments.get('section_id', ''))):
            errors.append('section_id must be sec_<number>, for example sec_26')
    if name == 'search_pdpa':
        query = arguments.get('query')
        if not isinstance(query, str) or not query.strip():
            errors.append('query must be a nonempty string')
        elif len(query) > settings['max_query_chars']:
            errors.append(f"query exceeds {settings['max_query_chars']} characters")
        top_k = arguments.get('top_k', 5)
        if not isinstance(top_k, int) or not 1 <= top_k <= settings['max_top_k']:
            errors.append(f"top_k must be between 1 and {settings['max_top_k']}")
    for event in engine.events:
        if event['origin'] == 'agent' and event['tool'] == name and event['arguments'] == arguments:
            state = 'admitted evidence' if event['admitted'] else 'a call that was not admitted'
            errors.append(f"This call is identical to {event['evidence_id']}, {state}; use that result or change the arguments")
            break
    return errors


def post_tool_use(engine, name, arguments, result):
    # FastMCP returns the same JSON twice (content text and structuredContent); keep the text only.
    result.pop('structuredContent', None)
    try:
        value = json.loads(text_result(result))
        if not isinstance(value, dict):
            raise ValueError('Tool result is not a JSON object')
        if value.get('error'):
            raise ValueError('Tool reported: ' + str(value['error']))
        if value.get('found') is False:
            raise ValueError('Section not found')
        if name == 'search_pdpa' and not str(value.get('context', '')).strip():
            raise ValueError('Search returned no context')
        return True, []
    except (ValueError, TypeError, KeyError) as exc:
        return False, [str(exc)]


def retrieval_events(engine):
    return {e['evidence_id']: e for e in engine.events
            if e['admitted'] and e['origin'] == 'agent' and e['tool'] in RETRIEVAL_TOOLS}


def evidence_errors(engine):
    return [] if retrieval_events(engine) else ['No admitted retrieval evidence']


def parse_draft(draft):
    text = draft.strip()
    fenced = re.fullmatch(r'```[A-Za-z0-9_-]*[ \t]*\n(.*?)\n?```', text, flags=re.S)
    if fenced:
        text = fenced.group(1)
    value = json.loads(text)
    if not isinstance(value, dict) or set(value) != {'answer', 'bindings'}:
        raise ValueError('Draft must have exactly answer and bindings')
    if not isinstance(value['answer'], str) or not value['answer'].strip() or not isinstance(value['bindings'], list):
        raise ValueError('Invalid answer or bindings')
    return value


def ungrounded_sections(text, evidence_texts):
    shown = set().union(*(shown_sections(t) for t in evidence_texts)) if evidence_texts else set()
    return sorted(cited_sections(text) - shown)


def completion_errors(engine, draft):
    errors = []
    try:
        value = parse_draft(draft)
        settings = engine.config['hook_settings']
        if len(value['bindings']) > settings['max_bindings']:
            return ['Too many bindings']
        required = {r['id']: r for r in engine.compiled_contract['requirements']}
        events = retrieval_events(engine)
        low, high = settings['penalty_section_range']
        seen, bound_ids = [], set()
        for binding in value['bindings']:
            if not isinstance(binding, dict) or set(binding) != {'requirement_id', 'evidence_ids'}:
                return ['Binding requires requirement_id and evidence_ids']
            rid, ids = binding['requirement_id'], binding['evidence_ids']
            seen.append(rid)
            if rid not in required:
                errors.append(f'Binding names unknown requirement {rid!r}; compiled requirement ids are {sorted(required)}')
                continue
            if not isinstance(ids, list) or not ids:
                errors.append(f'{rid}: evidence_ids must be a nonempty list of admitted retrieval evidence ids')
                continue
            unknown = [e for e in ids if e not in events]
            if unknown:
                errors.append(f'{rid}: {unknown} are not admitted retrieval evidence ids of this run; admitted ids are {sorted(events)}')
                continue
            bound_ids.update(ids)
            if required[rid]['issue_type'] == 'penalty':
                texts = [text_result(events[e]['result']) for e in ids]
                has_penalty_tool = any(events[e]['tool'] == 'get_penalty' for e in ids)
                has_penalty_section = any(low <= n <= high for t in texts for n in shown_sections(t))
                if not (has_penalty_tool or has_penalty_section):
                    errors.append(f'{rid}: a penalty requirement must be bound to evidence that shows a penalty provision '
                                  f'(a get_penalty result or text of a section in the penalty chapter); {NOT_SHOWN} one for {rid}')
        if Counter(seen) != Counter(required.keys()):
            errors.append('Bind every requirement exactly once')
        cited = set(re.findall(r'\bE\d{4}\b', value['answer']))
        if cited - bound_ids:
            errors.append('Draft cites evidence outside bindings: ' + ', '.join(sorted(cited - bound_ids))
                          + '. Add those ids to the binding of the requirement they support, or remove the citations.')
        if not cited_sections(value['answer']):
            errors.append('The answer cites no section; cite the governing sections as มาตรา N')
        missing = ungrounded_sections(value['answer'], [text_result(events[e]['result']) for e in sorted(bound_ids)])
        if missing:
            errors.append('The answer cites มาตรา ' + ', '.join(map(str, missing)) + f' but {NOT_SHOWN} '
                          + ('it' if len(missing) == 1 else 'them')
                          + '. Read each with get_section_text and bind that evidence, or remove the citation.')
    except (ValueError, TypeError, KeyError) as exc:
        errors.append(f'Draft JSON invalid: {exc}')
    return errors


def repair_needs_tools(engine, errors):
    return ['get_section_text', 'search_pdpa'] if any(NOT_SHOWN in e for e in errors) else []


def repair_tool_instruction(engine, errors):
    return 'Call get_section_text for the section the rejection named (or search_pdpa for a penalty provision), then bind the new evidence id.'


def synthesis_errors(engine, text, draft, verified_report):
    if not text.strip():
        return ['Empty synthesis']
    used = {eid for b in parse_draft(draft)['bindings'] for eid in b['evidence_ids']}
    cited = set(re.findall(r'\bE\d{4}\b', text))
    errors = []
    if not used <= cited:
        errors.append('Synthesis must cite all bound evidence ids: missing ' + ', '.join(sorted(used - cited)))
    if cited - used:
        errors.append('Synthesis cites evidence outside verified bindings: ' + ', '.join(sorted(cited - used)))
    missing = ungrounded_sections(text, [verified_report])
    if missing:
        errors.append('Synthesis cites มาตรา ' + ', '.join(map(str, missing)) + ' which the verified report does not show')
    return errors
