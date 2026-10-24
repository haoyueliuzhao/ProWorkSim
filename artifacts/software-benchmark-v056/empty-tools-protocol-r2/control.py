"""Bounded no-tool wire check: failed task is tokenized only; one neutral generation."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import http.client
import json
from pathlib import Path
import time
import traceback
from urllib.parse import urlsplit

from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.storage import json_bytes

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
OUT = Path(__file__).resolve().parent
SOURCE = ROOT / 'runs/software-benchmark-v056/episodes/ef4a68244887bb4d18967daea855596101e00f85ef207aa8209d8f5c64f97e2a/ref-ledger/request-0041.json'
READY = ROOT / 'runs/software-benchmark-v056/residents/gpu1-r1/ready.json'
TEMPLATE_KEYS = ('model', 'messages', 'tools', 'chat_template_kwargs',
                 'add_generation_prompt', 'continue_final_message', 'add_special_tokens')
SEED = 20261024056991


def sha(value):
    return hashlib.sha256(json_bytes(value)).hexdigest()


def main():
    source = json.loads(SOURCE.read_bytes())
    ready = json.loads(READY.read_bytes())
    original = source['request']
    assert source['usage_id'] == 'condenser' and original['tools'] == []
    assert original['tool_choice'] == 'none'
    assert source['service_identity']['endpoint'] == ready['endpoint']
    endpoint = urlsplit(ready['endpoint'])
    assert endpoint.scheme == 'http' and endpoint.hostname == '127.0.0.1' and endpoint.port == 18057
    key = Path(ready['api_key_file']).read_text().strip()
    result = {'version': 'v056-empty-tools-real-HTTP-control-r2',
              'created_utc': datetime.now(timezone.utc).isoformat(), 'passed': False,
              'source_failed_request': reference(SOURCE), 'resident_ready': reference(READY),
              'source': reference(__file__), 'benchmark_generation_replayed': False,
              'maximum_neutral_generation_requests': 1, 'neutral_generation_requests_started': 0,
              'known_neutral_actual_tokens': 0, 'formal_slot_claims': 0, 'HTTP_calls': []}

    def post(label, route, payload):
        before = time.monotonic()
        connection = http.client.HTTPConnection('127.0.0.1', endpoint.port, timeout=1800)
        record = {'label': label, 'route': route, 'request_sha256': sha(payload)}
        result['HTTP_calls'].append(record)
        try:
            connection.request('POST', route, body=json_bytes(payload), headers={
                'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
            response = connection.getresponse()
            raw = response.read(16 * 1024 * 1024 + 1)
            record.update(status=response.status, elapsed_seconds=time.monotonic()-before,
                          response_sha256=hashlib.sha256(raw).hexdigest(), response_bytes=len(raw))
            assert len(raw) <= 16 * 1024 * 1024
            body = json.loads(raw)
            if response.status != 200:
                write_new(OUT / (label + '-error.json'), body)
                raise RuntimeError(f'{label} returned HTTP {response.status}; no retry')
            return body
        finally:
            connection.close()

    def ids(body):
        values = body['tokens']
        assert isinstance(values, list) and values and all(type(x) is int and x >= 0 for x in values)
        assert body['count'] == len(values) and body['max_model_len'] == 131072
        return values

    try:
        original_count = {k: copy.deepcopy(original[k]) for k in TEMPLATE_KEYS}
        normalized = {k: copy.deepcopy(v) for k, v in original.items() if k not in {'tools', 'tool_choice'}}
        normalized_count = {k: copy.deepcopy(normalized[k]) for k in TEMPLATE_KEYS if k in normalized}
        first = post('original-empty-tools-tokenize', '/tokenize', original_count)
        second = post('omitted-tools-tokenize', '/tokenize', normalized_count)
        before_ids, after_ids = ids(first), ids(second)
        equal = before_ids == after_ids
        recorded = source['exact_input']['input_ids']
        equality = {'all_input_ids_equal': equal, 'original_count': len(before_ids),
                    'omitted_count': len(after_ids), 'original_ids_sha256': sha(before_ids),
                    'omitted_ids_sha256': sha(after_ids),
                    'matches_original_failed_request_exact_input': before_ids == recorded,
                    'original_generation_tool_choice': original['tool_choice'],
                    'tool_choice_not_part_of_old_tokenizer_payload': True,
                    'original_tokenizer_payload_sha256': sha(original_count),
                    'new_tokenizer_payload_sha256': sha(normalized_count)}
        write_new(OUT / 'tokenizer-equivalence.json', equality)
        write_new(OUT / 'complete-equivalent-input-ids.json', before_ids)
        result['tokenizer_equivalence'] = reference(OUT / 'tokenizer-equivalence.json')
        assert equal and before_ids == recorded
        neutral = {k: copy.deepcopy(v) for k, v in normalized.items() if k != 'messages'}
        neutral.update(seed=SEED, messages=[{'role': 'user', 'content': 'What is 2 + 2? Reply with just the answer.'}])
        assert neutral['max_tokens'] == 32768 and neutral['temperature'] == .6
        assert neutral['top_p'] == .95 and neutral['top_k'] == 20
        assert neutral['chat_template_kwargs'] == {'enable_thinking': True}
        assert 'tools' not in neutral and 'tool_choice' not in neutral
        neutral_count = {k: copy.deepcopy(neutral[k]) for k in TEMPLATE_KEYS if k in neutral}
        neutral_tokens = ids(post('neutral-tokenize', '/tokenize', neutral_count))
        write_new(OUT / 'neutral-request.json', neutral)
        result['neutral_generation_requests_started'] = 1
        result['known_neutral_actual_tokens'] = None
        body = post('neutral-generation', '/v1/chat/completions', neutral)
        response_ref = write_new(OUT / 'neutral-response.json', body)
        usage = body['usage']
        assert body['model'] == 'raw-qwen3.5-9b-v054-ref' and body['id']
        assert len(body['choices']) == 1 and body['choices'][0]['finish_reason'] in {'stop', 'length'}
        assert body['choices'][0]['message']['role'] == 'assistant'
        assert all(type(usage[k]) is int for k in ('prompt_tokens', 'completion_tokens', 'total_tokens'))
        assert usage['prompt_tokens'] == len(neutral_tokens)
        assert 0 < usage['completion_tokens'] <= 32768
        assert usage['total_tokens'] == usage['prompt_tokens'] + usage['completion_tokens']
        reason = (usage.get('completion_tokens_details') or {}).get('reasoning_tokens')
        assert reason is None or 0 <= reason <= usage['completion_tokens']
        result.update(passed=True, neutral_response=response_ref, neutral_usage=usage,
            known_neutral_actual_tokens=usage['total_tokens'], neutral_seed=SEED,
            neutral_input_ids_sha256=sha(neutral_tokens), model_requests_automatically_retried=0,
            failed_task_content_used_only_for_tokenization=True)
    except BaseException as error:
        result.update(error={'type': type(error).__name__, 'message': str(error)}, traceback=traceback.format_exc())
    write_new(OUT / 'result.json', result)
    print(json.dumps({'passed': result['passed'], 'neutral_generation_requests_started': result['neutral_generation_requests_started'], 'known_neutral_actual_tokens': result['known_neutral_actual_tokens'], 'output': str(OUT), **({'error': result['error']} if 'error' in result else {})}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
