"""Independent-process actual world and official-tokenizer identifier control."""
import argparse
import json
from pathlib import Path

from proworksim.candidate_runtime_v015 import prepare_candidate_prompt
from proworksim.candidate_runtime_v017 import parse_candidate_generated
from proworksim.deterministic_work_v024 import deterministic_tool_ids
from proworksim.episode import begin_episode, finish_episode
from proworksim.online_collection import run_fragment
from proworksim.storage import atomic_write, digest, json_bytes, read_json
from proworksim.templates import retail_collaboration_v024 as world
from scripts.retail_work_controls_v024 import ProgramOwner


class NativeProgram(ProgramOwner):
    def complete(self, request, *, timeout_seconds):
        envelope = super().complete(request, timeout_seconds=timeout_seconds)
        if envelope['http_status'] != 200:
            return envelope
        message = envelope['body']['choices'][0]['message']
        function = message['tool_calls'][0]['function']
        args = json.loads(function['arguments'])
        raw = '<tool_call>\n<function=' + function['name'] + '>\n' + '\n'.join(
            '<parameter=' + k + '>' + (v if isinstance(v, str) else json.dumps(v)) + '</parameter>'
            for k, v in args.items()) + '\n</function>\n</tool_call>'
        parsed, diagnostics = parse_candidate_generated(raw, request)
        if diagnostics is not None:
            raise ValueError(diagnostics)
        parsed = deterministic_tool_ids(parsed, request, raw)
        if parsed['tool_calls'][0]['function'] != function:
            raise ValueError('Actual native parser changed program action')
        envelope['body']['choices'][0]['message'] = parsed
        envelope['raw_body'] = json.dumps(envelope['body'])
        return envelope


def run(output, tokenizer_path, indices):
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_path, local_files_only=True)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    entries = []
    for index in indices:
        case = world.registry()['all_cases'][index]
        folder = output / f'case-{index:02d}'
        prepared = world.build_case(case, folder)
        owner = NativeProgram(case['task'], tokenizer)
        runner, capture, _ = world.runtime(owner, prepared, folder, episode_key='independent-process-control')
        episode = folder/'episode'
        manifest = begin_episode(prepared.world, episode, experience=runner.recorder.snapshot(), work_ids=[world.WORK], scenario=prepared.scenario, policies=runner.policy_identities)
        stop = run_fragment(prepared, runner)
        finish_episode(prepared.world, episode, experience=runner.recorder.snapshot(), termination=stop)
        tokens = []
        for request in owner.requests:
            rendered, _, _ = prepare_candidate_prompt(request, tokenizer, {'chat_template_kwargs': {'enable_thinking': False, 'preserve_thinking': False}})
            tokens.append(tokenizer(rendered, add_special_tokens=False)['input_ids'])
        score = world.assess_episode(episode)
        identity = read_json(folder/'visible-identity.json')
        row = {'case_id': case['case_id'], 'case_index': index, 'score': score,
               'messages_sha256': digest(json_bytes([r['messages'] for r in owner.requests])),
               'tools_sha256': digest(json_bytes([r['tools'] for r in owner.requests])),
               'official_input_tokens_sha256': digest(json_bytes(tokens)),
               'world_tool_calls_sha256': digest(json_bytes({r: [x for x in rows if x['kind'] == 'tool_call'] for r, rows in capture.items()})),
               'visible_runtime_id': runner.run_id, 'actual_identity': identity,
               'actual_episode_id': manifest['episode_id'], 'requests': len(owner.requests)}
        atomic_write(folder/'requests.json', json_bytes(owner.requests))
        atomic_write(folder/'capture.json', json_bytes(capture))
        entries.append(row)
        atomic_write(output/'report.json', json_bytes({'cases': entries}))
        print(index, score['eligible'], score['completed'], row['messages_sha256'], flush=True)
    return entries


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True)
    p.add_argument('--tokenizer', required=True)
    p.add_argument('--case-indices', nargs='+', type=int, default=[0, 4])
    a = p.parse_args()
    run(a.output, a.tokenizer, a.case_indices)
