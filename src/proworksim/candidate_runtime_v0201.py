"""Single declared follow-up: BF16 backbone with a frozen FP32 output projection.

The first v0.20 failure remains a failure. This module does not infer that the
output head caused it, nor does it relax its original probability tolerances.
"""

from .candidate_runtime_v020 import CandidateActor as PreviousActor
from .candidate_runtime_v020 import candidate_profile as previous_profile
from .candidate_runtime_v020 import inspect_parameter_storage as inspect_previous_storage
from .candidate_runtime_v020 import _no_autocast

VERSION = "candidate-runtime-v0.20.1"


def candidate_profile(candidate_id, *, dtype="bfloat16", devices=1):
    profile = previous_profile(candidate_id, dtype=dtype, devices=devices)
    profile.update(
        version=VERSION,
        base_storage_dtype="bfloat16_backbone_float32_lm_head",
        backbone_storage_dtype="bfloat16",
        lm_head_storage_dtype="float32",
        lm_head_input_dtype="float32",
        lm_head_output_dtype="float32",
        lm_head_trainable=False,
        lm_head_contract="Untied bias-free Linear; actual FP32 weight and pre-projection input; output remains FP32",
        dtype_scope=("Frozen text backbone BF16; frozen untied LM head FP32, with hidden "
                     "states promoted BEFORE its matrix multiplication and FP32 output. "
                     "Trainable LoRA and its matmuls FP32; PEFT projection results return "
                     "to BF16. Sampling and full-input selected-token normalization FP32. "
                     "Official DeltaNet/RMSNorm/rotary FP32 intermediates retained."),
    )
    return profile


def _head(model, torch):
    head = model.get_output_embeddings()
    if (type(head) is not torch.nn.Linear or head.bias is not None
            or head.weight.requires_grad or model.config.tie_word_embeddings
            or model.get_input_embeddings().weight is head.weight
            or list(head.named_buffers())):
        raise ValueError("v0.20.1 requires an untied frozen bias-free Linear head without buffers")
    names = [name for name, parameter in model.named_parameters() if parameter is head.weight]
    if len(names) != 1 or not names[0].endswith("lm_head.weight"):
        raise ValueError("Unambiguous original LM head parameter identity required")
    return head, names


def inspect_parameter_storage(model, torch):
    head, names = _head(model, torch)
    if head.weight.dtype != torch.float32:
        raise ValueError("LM head must actually be stored as FP32")
    result = inspect_previous_storage(model, torch, frozen_fp32_names=names)
    result["lm_head"] = {"parameter_names": names, "dtype": "float32",
                         "shape": list(head.weight.shape), "trainable": False,
                         "buffers": [], "tied_to_input_embeddings": False}
    return result


class HeadExecution:
    """Small detached counters: retain no activations, logits or computation graph."""

    def __init__(self, head, torch):
        self.head, self.torch = head, torch
        self.calls = 0
        self.source_input_dtypes = set()
        self.compute_input_dtypes = set()
        self.output_dtypes = set()
        self.before_handle = head.register_forward_pre_hook(self.before, with_kwargs=True)
        self.after_handle = head.register_forward_hook(self.after)

    def before(self, module, args, kwargs):
        _no_autocast(self.torch)
        if module is not self.head or module.weight.dtype != self.torch.float32:
            raise ValueError("The declared FP32 output projection changed")
        if len(args) != 1 or kwargs:
            raise ValueError("Unexpected LM head calling convention")
        self.source_input_dtypes.add(str(args[0].dtype))
        converted = args[0].float()
        self.compute_input_dtypes.add(str(converted.dtype))
        return (converted,), kwargs

    def after(self, module, args, output):
        if output.dtype != self.torch.float32:
            raise ValueError("LM head output must remain FP32")
        self.calls += 1
        self.output_dtypes.add(str(output.dtype))

    def verify_installed(self):
        if (self.before_handle.id not in self.head._forward_pre_hooks
                or self.after_handle.id not in self.head._forward_hooks):
            raise ValueError("LM head execution contract was removed")

    def snapshot(self):
        return {"completed_forward_calls": self.calls,
                "source_input_dtypes": sorted(self.source_input_dtypes),
                "compute_input_dtypes": sorted(self.compute_input_dtypes),
                "output_dtypes": sorted(self.output_dtypes),
                "scope": "Actual observed head forwards only; no full-vocabulary logits retained"}


class CandidateActor(PreviousActor):
    runtime_version = VERSION
    profile_factory = staticmethod(candidate_profile)
    storage_inspector = staticmethod(inspect_parameter_storage)

    def prepare_model(self, network, torch):
        # Validate the inherited official BF16 load BEFORE its one declared cast.
        inspect_previous_storage(network, torch)
        head, _ = _head(network, torch)
        head.to(dtype=torch.float32)
        self.head_execution = HeadExecution(head, torch)

    def _verify_execution(self):
        super()._verify_execution()
        self.head_execution.verify_installed()

    def _generate_tokens(self, inputs, trace, options):
        before = self.head_execution.calls
        generated, metadata = super()._generate_tokens(inputs, trace, options)
        metadata["lm_head_execution"] = {**self.head_execution.snapshot(),
                                         "calls_in_this_generation": self.head_execution.calls - before}
        return generated, metadata

    def execution_diagnostics(self):
        return {"version": VERSION, "lm_head_execution": self.head_execution.snapshot()}
