"""Frozen dense coding-model adapters using the original shared online learner.

Native Mistral token IDs come directly from mistral-common. Its rendered text is
an audit representation, never a round trip through a different tokenizer.
"""

import copy
import json
from pathlib import Path
import re

from .candidate_runtime_v015 import freeze_candidate_generation
from .candidate_runtime_v020 import Float32SamplingProcessor, bf16_attention_forward
from .candidate_runtime_v0201 import HeadExecution, inspect_parameter_storage
from .local_model_service import parse_generated, prepare_prompt
from .online_training import SharedActor, recipe_config, reference
from .storage import atomic_write, digest, json_bytes, read_json
from .training import normalize_messages

VERSION = 'code-agent-runtime-v0.30'
ATTENTION = 'dense_bf16_explicit_kv_v030'
MODELS = {
    'swe-next-14b': {'repo_id': 'TIGER-Lab/SWE-Next-14B',
        'revision': '5d9484d6b0e20786629fccf6de9f190f5fb5ebc7',
        'model_type': 'qwen2', 'layers': 48, 'hidden_size': 5120,
        'native_format': 'qwen2_json_tool_call', 'eos_token_ids': [151645, 151643]},
    'devstral-small-2507': {'repo_id': 'mistralai/Devstral-Small-2507',
        'revision': 'bd165ab26cebbcc2eea2c4ecbfc07f3ac42b3c39',
        'model_type': 'mistral', 'layers': 40, 'hidden_size': 5120,
        'native_format': 'mistral_common_v13_tool_name_args', 'eos_token_ids': [2]},
}
MISTRAL_HINT = (
    'For this declared work interface, emit exactly one native [TOOL_CALLS]function_name[ARGS]{argument_object} per decision. '
    'Use one supplied function name and its argument object. Multiple calls are rejected together. '
    'Use staff_wait or staff_done when appropriate. Only the actual tool response establishes execution; '
    'never invent tool results. In a native_transport_envelope, original_tool_message is the real '
    'tool response; subsequent_user_messages are later user inputs with their original roles and '
    'unchanged text. Use those later inputs as the current instructions or observations, without '
    'attributing them to a prior model action.'
)


def mistral_message_projection(messages):
    """Preserve tool→user inputs in a documented native-compatible envelope.

    Mistral v13 rejects a user message immediately after a tool result. We do
    not manufacture an assistant turn or discard the subsequent observation.
    The native tool content carries the complete original tool message and each
    later user message, with source indices/roles; the SDK request stays intact.
    """
    selected, indices, envelopes = [], [], {}
    for index, message in enumerate(messages):
        if message['role'] == 'user' and selected and selected[-1]['role'] == 'tool':
            position = len(selected) - 1
            if position not in envelopes:
                envelopes[position] = {
                    'native_transport_envelope': 'mistral_v13_tool_then_user_v0.30',
                    'original_tool_message': copy.deepcopy(selected[-1]),
                    'original_tool_message_index': indices[-1][0],
                    'subsequent_user_messages': [],
                }
            envelopes[position]['subsequent_user_messages'].append({
                'original_message_index': index, 'message': copy.deepcopy(message)})
            indices[-1].append(index)
            selected[-1]['content'] = json.dumps(envelopes[position], ensure_ascii=False,
                                                sort_keys=True, allow_nan=False)
        else:
            selected.append(copy.deepcopy(message))
            indices.append([index])
    proof = {'version': 'mistral-native-role-projection-v0.30',
             'original_messages_sha256': digest(json_bytes(messages)),
             'native_messages_sha256': digest(json_bytes(selected)),
             'source_message_indices_per_native_message': indices,
             'enveloped_native_indices': sorted(envelopes),
             'source_message_count': len(messages), 'native_message_count': len(selected),
             'source_message_sha256': [digest(json_bytes(row)) for row in messages],
             'scope': 'Each original role and text is retained either directly or verbatim inside a labeled envelope. No assistant/tool result is invented and no original sampled output token is changed.'}
    return selected, proof


class NativePrompt(str):
    """Audit rendering carrying the exact native encoder output in memory."""
    def __new__(cls, text, input_ids):
        value = super().__new__(cls, text)
        value.input_ids = tuple(input_ids)
        return value

    def __getnewargs__(self):
        return str(self), self.input_ids


class MistralNativeTokenizer:
    def __init__(self, model_path):
        from mistral_common.tokens.tokenizers.mistral import MistralTokenizer
        from mistral_common.tokens.tokenizers.base import SpecialTokenPolicy
        self.native = MistralTokenizer.from_file(str(Path(model_path) / 'tekken.json'))
        self.special_policy = SpecialTokenPolicy.KEEP
        self.plain = self.native.instruct_tokenizer.tokenizer
        if self.plain.version.value != 'v13':
            raise ValueError('The frozen official Devstral tokenizer must declare instruction version v13')
        self.eos_token_id, self.bos_token_id = self.plain.eos_id, self.plain.bos_id
        self.pad_token_id = read_json(Path(model_path) / 'config.json')['pad_token_id']
        self.padding_side = 'left'

    def __call__(self, text, *, add_special_tokens=False, **kwargs):
        if add_special_tokens or kwargs or not isinstance(text, NativePrompt):
            raise ValueError('Mistral model input must be the original native chat encoder output')
        return {'input_ids': list(text.input_ids)}

    def decode(self, ids, skip_special_tokens=False):
        if skip_special_tokens:
            raise ValueError('Preserve native sampled special tokens in the raw response')
        return self.native.decode(list(ids), special_token_policy=self.special_policy)

    def encode_text(self, text):
        return self.plain.encode(text, bos=False, eos=False)

    def prepare(self, request):
        from mistral_common.protocol.instruct.request import ChatCompletionRequest
        original = normalize_messages(request['messages'])
        messages, role_projection = mistral_message_projection(original)
        if request.get('tools'):
            if messages and messages[0]['role'] == 'system':
                messages[0]['content'] += '\n' + MISTRAL_HINT
            else:
                messages.insert(0, {'role': 'system', 'content': MISTRAL_HINT})
        native_request = ChatCompletionRequest.from_openai(
            messages=messages, tools=request.get('tools') or None,
            model=request.get('model'), tool_choice='auto')
        if native_request.truncate_for_context_length:
            raise ValueError('Native Mistral hidden truncation is forbidden')
        encoded = self.native.encode_chat_completion(native_request)
        text = self.decode(encoded.tokens)
        prompt = NativePrompt(text, encoded.tokens)
        return prompt, messages, {
            'version': VERSION, 'native_tool_prompt': 'mistral_common_single_call',
            'native_input_ids_sha256': digest(json_bytes(encoded.tokens)),
            'request_sha256': digest(json_bytes(request)),
            'normalized_messages_sha256': digest(json_bytes(original)),
            'actual_prompt_messages_sha256': digest(json_bytes(messages)),
            'native_role_projection': role_projection,
            'rendered_prompt_sha256': digest(text.encode()),
            'scope': 'Official native encoder tokens, not retokenized rendering; public syntax hint only, no task solution.',
        }


def _native_ids(message, request, raw, *, length=32):
    for index, call in enumerate(message.get('tool_calls', [])):
        value = digest(json_bytes([request, raw, index]))[:length]
        call['id'] = value if length == 9 else 'call_' + value
    return message


def parse_mistral_generated(raw, request):
    """Exact official v13 name/[ARGS]/object grammar; never rewrite a v7 array."""
    content = raw.removesuffix('</s>').strip()
    marker = '[TOOL_CALLS]'
    if marker not in content:
        return {'role': 'assistant', 'content': content}, None
    if content.count(marker) != 1:
        return {'role': 'assistant', 'content': content}, 'multiple_native_tool_markers'
    prefix, block = content.split(marker)
    try:
        match = re.fullmatch(r'([A-Za-z_][A-Za-z0-9_.-]*)\s*\[ARGS\](.*)', block.strip(), re.DOTALL)
        if match is None:
            raise ValueError('Expected native function_name[ARGS]{argument_object}')
        name, value = match.groups()
        arguments = json.loads(value)
        if not isinstance(arguments, dict):
            raise ValueError('Native arguments must be a JSON object')
        message = {'role': 'assistant', 'content': prefix.strip(), 'tool_calls': [{
            'type': 'function', 'id': '', 'function': {'name': name,
                'arguments': json.dumps(arguments, ensure_ascii=False, allow_nan=False)}}]}
        return _native_ids(message, request, raw, length=9), None
    except (ValueError, TypeError) as error:
        return {'role': 'assistant', 'content': content}, 'invalid_native_tool_v13: ' + str(error)


def candidate_profile(candidate_id):
    if candidate_id not in MODELS:
        raise ValueError('Only the two predeclared new coding candidates are allowed')
    return {'version': VERSION, 'candidate_id': candidate_id, **copy.deepcopy(MODELS[candidate_id]),
            'devices': 1, 'dtype': 'bfloat16', 'base_storage_dtype': 'bfloat16_backbone_float32_lm_head',
            'adapter_storage_dtype': 'float32', 'adapter_compute_dtype': 'float32',
            'max_context_tokens': 16384, 'max_output_tokens': 2048,
            'temperature': 0.7, 'top_p': 1.0, 'top_k': 0, 'repetition_penalty': 1.0,
            'lora_target_modules': ['q_proj', 'v_proj'], 'lora_rank': 8, 'lora_alpha': 16,
            'dropout': 0.0, 'attention': ATTENTION, 'autocast': False,
            'prefix_cache': False, 'sampling_replicas': 0,
            'logprob_max_atol': 0.02, 'logprob_mean_atol': 0.002,
            'scope': 'One explicit runtime combination per model; no parameter-count-only causal comparison.'}


def verify_manifest(model_path, manifest, candidate_id):
    """Check unchanged files against the completed download's content verification."""
    root, record = Path(model_path).resolve(), read_json(Path(manifest))
    declared = MODELS[candidate_id]
    if (record.get('status') != 'complete' or record.get('repo_id') != declared['repo_id']
            or record.get('declared_hf_revision') != declared['revision']
            or Path(record['model_path']).resolve() != root):
        raise ValueError('Require the complete frozen official candidate download')
    files = record['files']
    weights = set(read_json(root / 'model.safetensors.index.json')['weight_map'].values())
    if not weights or not weights <= files.keys():
        raise ValueError('The manifest omits original model shards')
    for name, expected in files.items():
        path = (root / name).resolve()
        stat = path.stat()
        if (not path.is_relative_to(root) or stat.st_size != expected['bytes']
                or stat.st_mtime_ns != expected['mtime_ns']):
            raise ValueError('Verified official file changed after download: ' + name)
        lfs = record['remote_files'][name].get('lfs')
        if lfs and lfs['sha256'] != expected['sha256']:
            raise ValueError('Verified content digest differs from the frozen official LFS identity')
    return record


def loading_info_record(loading):
    """Represent Transformers 5 loading-key sets without altering load admission.

    LoadStateDictInfo.to_dict() returns sets for missing/unexpected/mismatched
    keys, even when all are empty. JSON stores those exact sets as sorted arrays;
    source container types are recorded separately and original objects remain.
    """
    return {
        'loading_info': {key: sorted(value) if isinstance(value, set) else copy.deepcopy(value)
                         for key, value in loading.items()},
        'loading_info_source_types': {key: type(value).__name__ for key, value in loading.items()},
        'loading_info_serialization': 'Top-level loading-key sets represented by sorted JSON arrays; no key or error is omitted.',
    }


class DenseCandidateActor(SharedActor):
    def prepare_request(self, request):
        if isinstance(self.tokenizer, MistralNativeTokenizer):
            return self.tokenizer.prepare(request)
        return prepare_prompt(request, self.tokenizer, 'single_call')

    def parse_response(self, raw, request):
        if isinstance(self.tokenizer, MistralNativeTokenizer):
            return parse_mistral_generated(raw, request)
        message, error = parse_generated(raw)
        return _native_ids(message, request, raw), error

    def _generate_tokens(self, inputs, trace, options):
        self.head_execution.verify_installed()
        processor = Float32SamplingProcessor(trace)
        generated = self.model.generate(input_ids=inputs, attention_mask=self.torch.ones_like(inputs),
            logits_processor=[processor], **options)
        return generated, {'runtime_version': VERSION, 'sampling_processor_calls': processor.calls,
                           'observed_sampling_score_dtypes': sorted(processor.observed_input_dtypes),
                           'head_execution': self.head_execution.snapshot()}

    def learning_logprobs(self, trace):
        self.head_execution.verify_installed()
        return super().learning_logprobs(trace)

    @classmethod
    def from_candidate(cls, model_path, *, manifest, profile, output, recipe=None):
        import torch
        import transformers
        import peft
        from peft import LoraConfig, get_peft_model
        from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer
        from transformers.masking_utils import ALL_MASK_ATTENTION_FUNCTIONS, AttentionMaskInterface
        from transformers.modeling_utils import AttentionInterface

        if profile != candidate_profile(profile['candidate_id']):
            raise ValueError('Dense candidate profile changed after declaration')
        recipe = recipe_config(recipe)
        for key, field in [('temperature', 'temperature'), ('max_length', 'max_context_tokens'),
                           ('max_output_tokens', 'max_output_tokens'), ('logprob_max_atol', 'logprob_max_atol'),
                           ('logprob_mean_atol', 'logprob_mean_atol')]:
            if recipe[key] != profile[field]:
                raise ValueError('Dense candidate recipe differs: ' + key)
        if torch.cuda.device_count() != 1 or not torch.cuda.is_bf16_supported(including_emulation=False):
            raise ValueError('Dense selection requires exactly one native BF16 GPU, no offload')
        if torch.is_autocast_enabled('cuda') or torch.is_autocast_enabled('cpu'):
            raise ValueError('Ambient autocast is not part of the declared numerical profile')
        identity = verify_manifest(model_path, manifest, profile['candidate_id'])
        torch.manual_seed(recipe['seed'])
        torch.set_num_threads(8)
        torch.set_float32_matmul_precision('highest')
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        root = Path(model_path).resolve()
        config = AutoConfig.from_pretrained(root, local_files_only=True, trust_remote_code=False)
        if (config.model_type != profile['model_type'] or config.num_hidden_layers != profile['layers']
                or config.hidden_size != profile['hidden_size'] or config.tie_word_embeddings
                or config.attention_dropout != 0):
            raise ValueError('Official architecture differs from the frozen dense candidate')
        tokenizer = (MistralNativeTokenizer(root) if config.model_type == 'mistral' else
                     AutoTokenizer.from_pretrained(root, local_files_only=True, trust_remote_code=False))
        tokenizer.padding_side = 'left'
        if tokenizer.pad_token_id is None:
            tokenizer.pad_token_id = tokenizer.eos_token_id
        network, loading = AutoModelForCausalLM.from_pretrained(root, config=config,
            local_files_only=True, trust_remote_code=False, dtype=torch.bfloat16,
            attn_implementation='sdpa', device_map={'': 0}, output_loading_info=True)
        if any(loading.get(key) for key in ('missing_keys', 'unexpected_keys', 'mismatched_keys', 'error_msgs')):
            raise ValueError('Official dense model did not load every original tensor exactly')
        eos = network.generation_config.eos_token_id
        eos = [eos] if isinstance(eos, int) else eos
        if sorted(eos) != sorted(profile['eos_token_ids']):
            raise ValueError('Official generation EOS differs from the registered native contract')
        generation = freeze_candidate_generation(network, tokenizer, recipe['max_output_tokens'])
        network = get_peft_model(network, LoraConfig(r=8, lora_alpha=16, lora_dropout=0,
            target_modules=profile['lora_target_modules'], bias='none', task_type='CAUSAL_LM'))
        matched = [name for name, module in network.named_modules() if hasattr(module, 'lora_A')]
        if len(matched) != 2 * config.num_hidden_layers:
            raise ValueError('Every dense layer needs the declared q/v LoRA pair')
        head = network.get_output_embeddings()
        if type(head) is not torch.nn.Linear or head.bias is not None or head.weight.requires_grad:
            raise ValueError('Require the official untied frozen linear output head')
        head.to(dtype=torch.float32)
        head_execution = HeadExecution(head, torch)
        actual_storage = inspect_parameter_storage(network, torch)
        AttentionInterface.register(ATTENTION, bf16_attention_forward)
        AttentionMaskInterface.register(ATTENTION, ALL_MASK_ATTENTION_FUNCTIONS['sdpa'])
        network.set_attn_implementation(ATTENTION)
        if any(parameter.device != torch.device('cuda:0') for parameter in network.parameters()):
            raise ValueError('Dense candidate escaped the assigned single GPU')
        actual_profile = {**copy.deepcopy(profile), 'torch': str(torch.__version__),
                          'transformers': str(transformers.__version__), 'peft': str(peft.__version__),
                          'actual_lora_modules': matched, 'actual_parameter_storage': actual_storage,
                          'generation_contract_sha256': digest(json_bytes(generation)),
                          'official_native_tokenizer': 'mistral-common==1.7.0' if config.model_type == 'mistral' else 'official Qwen2 HF template',
                          'weight_verification': 'Official whole-file SHA256 at completed download; unchanged size/mtime and manifest at load; no redundant full weight rescan.'}
        owner = cls(network, tokenizer, output=output, recipe=recipe, device='cuda:0',
            inference_profile=actual_profile, base_identity={'path': str(root),
                'manifest': reference(manifest), 'revision': identity['declared_hf_revision']})
        owner.head_execution = head_execution
        atomic_write(Path(output) / 'dense-generation-contract.json', json_bytes(generation))
        atomic_write(Path(output) / 'dense-loading.json', json_bytes({**loading_info_record(loading),
            'actual_storage': actual_storage, 'actual_lora_modules': matched}))
        return owner
