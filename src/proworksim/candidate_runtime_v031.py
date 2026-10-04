"""Declared v031 native interfaces and complete differentiable dense replay.

Weight loading and cached sampling retain the v030 implementation. The owner is
bound to its new interface/replay profile before its initial identity is made.
No old trace, probability threshold, model output, or screening outcome is edited.
"""

import copy

from .candidate_runtime_v030 import DenseCandidateActor, candidate_profile as loading_profile
from .functional_dense_v031 import CONTRACT as LEARNING_CONTRACT, learning_logprobs
from .native_codecs_v031 import MISTRAL_FORMAT, SWE_AUTHOR_COMMIT, SWE_FORMAT, VERSION as NATIVE_VERSION

VERSION = "code-agent-runtime-v0.31"
NATIVE_FORMATS = {
    "swe-next-14b": SWE_FORMAT,
    "devstral-small-2507": MISTRAL_FORMAT,
}


def candidate_profile(candidate_id):
    prior = loading_profile(candidate_id)
    return {**prior, "version": VERSION, "native_format": NATIVE_FORMATS[candidate_id],
            "native_codec_version": NATIVE_VERSION,
            "swe_author_protocol_commit": SWE_AUTHOR_COMMIT if candidate_id == "swe-next-14b" else None,
            "learning_execution": copy.deepcopy(LEARNING_CONTRACT),
            "tool_hint_scope": "Only function names actually declared by this request",
            "sampling_execution": "Unchanged original HF cached generation and FP32 sampling scores",
            "scope": "New declared native-interface/replay runtime combination. Original v030 failures remain unchanged; not an allocation effect or causal model-size comparison."}


def bind_profile(actual_loading_profile):
    """Preserve actual storage/library evidence while binding the new contract."""
    candidate = actual_loading_profile["candidate_id"]
    expected = loading_profile(candidate)
    if any(actual_loading_profile.get(key) != value for key, value in expected.items()):
        raise ValueError("The reused weight/sampling loader differs from its original declared profile")
    return {**copy.deepcopy(actual_loading_profile), **candidate_profile(candidate),
            "weight_and_sampling_loader_version": expected["version"],
            "official_native_tokenizer": (
                "Official Qwen2 chat boundaries with author-declared XML content protocol and tools=None"
                if candidate == "swe-next-14b" else "Official mistral-common==1.7.0 v13 input IDs"),
            "initial_binding_scope": "Final v031 native/replay profile is bound before owner construction, identity, optimizers, checkpoint or model calls."}


class CandidateActor(DenseCandidateActor):
    def __init__(self, model, tokenizer, *, inference_profile, **kwargs):
        super().__init__(model, tokenizer, inference_profile=bind_profile(inference_profile), **kwargs)

    def prepare_request(self, request):
        from .native_codecs_v031 import prepare_code_request
        return prepare_code_request(request, self.tokenizer, self.inference_profile["candidate_id"])

    def parse_response(self, raw, request):
        from .native_codecs_v031 import parse_code_response
        return parse_code_response(raw, request, self.inference_profile["candidate_id"])

    def learning_logprobs(self, trace):
        self.head_execution.verify_installed()
        return learning_logprobs(self.model, trace)

    @classmethod
    def from_candidate(cls, model_path, *, manifest, profile, output, recipe=None):
        if profile != candidate_profile(profile["candidate_id"]):
            raise ValueError("The v031 native/replay candidate profile changed after declaration")
        # The parent classmethod constructs cls, whose constructor binds the
        # final profile before SharedActor persists any identity or owner record.
        return super().from_candidate(model_path, manifest=manifest,
            profile=loading_profile(profile["candidate_id"]), output=output, recipe=recipe)
