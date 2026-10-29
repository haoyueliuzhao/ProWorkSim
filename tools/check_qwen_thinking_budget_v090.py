"""CPU-only check of the installed vLLM thinking-to-answer budget mechanism."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def check(output):
    output = Path(output).resolve()
    if (os.getuid() == 0 or output.exists() or not
            (output.is_relative_to(ROOT/'runs/software-benchmark-v090') or output.is_relative_to('/tmp'))):
        raise PermissionError('Use a fresh ordinary-user CPU-only evidence directory')
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    sys.path.insert(0, str(ROOT/'runs/software-benchmark-v054/ref-venv/lib/python3.12/site-packages'))
    import torch
    from tokenizers import Tokenizer
    from vllm.entrypoints.openai.chat_completion.protocol import ChatCompletionRequest
    from vllm.sampling_params import SamplingParams
    from vllm.v1.sample.logits_processor.interface import BatchUpdate
    from vllm.v1.sample.thinking_budget_state import ThinkingBudgetStateHolder
    from proworksim.software_benchmark_candidates_v054 import reference, write_new

    tokenizer_file = ROOT/'runs/assets/models/Qwen3.5-9B-c20223623576/tokenizer.json'
    tokenizer = Tokenizer.from_file(str(tokenizer_file))
    start = tokenizer.encode('<think>', add_special_tokens=False).ids
    end = tokenizer.encode('</think>', add_special_tokens=False).ids
    assert len(start) == len(end) == 1 and start != end
    config = SimpleNamespace(reasoning_start_token_ids=start, reasoning_end_token_ids=end)
    # A tiny synthetic token sequence exercises the real installed implementation.
    # It contains no model-generated reasoning and does not measure task quality.
    state = ThinkingBudgetStateHolder(config, 1, 0, torch.device('cpu'), False)
    params = SamplingParams(max_tokens=8, thinking_token_budget=3)
    batch = BatchUpdate(batch_size=1, removed=[], added=[(0, params, start, [])], moved=[])
    state.sync_batch(batch)
    output_ids = [11, 12]
    state.update_state([output_ids], None)
    assert state._state[0]['in_end'] is False
    output_ids.append(13)
    state.update_state([output_ids], None)
    assert state._state[0]['in_end'] is True
    assert state._state[0]['force_index'] == [0]
    assert state.think_end_token_ids[state._state[0]['end_count']] == end[0]
    output_ids.extend(end)
    state.update_state([output_ids], None)
    assert state._state[0]['in_end'] is False
    request = ChatCompletionRequest(model='raw-qwen3.5-9b-v054-ref',
        messages=[{'role': 'user', 'content': 'Synthetic CPU shape only'}],
        max_tokens=32768, thinking_token_budget=24576,
        chat_template_kwargs={'enable_thinking': True})
    assert request.thinking_token_budget == 24576 and request.max_tokens == 32768
    output.mkdir(parents=True)
    import inspect
    return write_new(output/'result.json', {'version': 'v090-official-thinking-budget-CPU-r1',
        'passed': True, 'installed_request_field_accepted': True,
        'real_installed_state_requests_reasoning_end_at_budget': True,
        'real_installed_state_clears_forcing_after_end': True,
        'GPU_logit_mask_path_tested': False,
        'synthetic_budget': 3, 'synthetic_max_tokens': 8,
        'proposed_thinking_token_budget': 24576, 'unchanged_total_output_limit': 32768,
        'nominal_remaining_output_capacity': 8192,
        'guarantees_tool_call_or_correct_answer': False,
        'formal_protocol_frozen': False, 'production_deployed': False,
        'model_calls': 0, 'GPU_model_loads': 0, 'network_calls': 0,
        'torch_cuda_initialized': torch.cuda.is_initialized(),
        'tokenizer': reference(tokenizer_file),
        'installed_state_source': reference(inspect.getfile(ThinkingBudgetStateHolder)),
        'installed_request_source': reference(inspect.getfile(ChatCompletionRequest)),
        'source': reference(__file__),
        'official_documentation': 'https://docs.vllm.ai/en/latest/features/reasoning_outputs/#thinking-budget-control',
        'scope': 'CPU mechanism only; not GPU kernel, end-to-end serving, speed or correctness qualification'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.output), ensure_ascii=False))
