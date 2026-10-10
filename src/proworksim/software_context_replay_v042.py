"""CPU native-token measurement for the paged v042 protocol.

P_selected is the actual suffix selection; P_protected removes every removable
old complete tool round. The 1024-token engineering margin applies only to the
latter. All lengths and hashes encode complete native requests, never segments.
"""
import copy

from .software_context_replay_v041 import (
    DEFAULT_PLAN, encode_request, load_native_measurement as inherited_measurement, reference as reference,
)
from .software_context_v041 import project_software_request as prior_project
from .software_context_v042 import (
    project_software_request as new_project, protected_software_request,
)

VERSION = "software-native-context-measurement-v0.42"
PROTECTED_MARGIN = 1024


def load_native_measurement(plan_path=DEFAULT_PLAN):
    value = inherited_measurement(plan_path)
    value.identity = {**copy.deepcopy(value.identity), "version": VERSION,
        "inherited_native_identity_version": value.identity["version"],
        "protected_margin_tokens": PROTECTED_MARGIN,
        "protected_margin_scope": "Remove all legally removable old complete tool rounds, then measure the entire native request; not an information-theoretic minimum"}
    return value


def measure_request(request, measurement):
    options = {"render": measurement.render, "tokenizer": measurement.tokenizer,
               "context_limit": measurement.recipe["max_length"]}
    old_selected, old_projection = prior_project(request, **options)
    new_selected, new_projection = new_project(request, **options)
    protected = protected_software_request(request)
    # The pure helper returns the request and its index metadata.
    protected_selected = protected[0] if isinstance(protected, tuple) else protected
    protected_encoding = encode_request(protected_selected, measurement)
    protected_encoding["headroom_after_margin_tokens"] = protected_encoding["headroom_tokens"] - PROTECTED_MARGIN
    protected_encoding["margin_fits"] = protected_encoding["headroom_after_margin_tokens"] >= 0
    result = {"original": {"request": copy.deepcopy(request), "encoding": encode_request(request, measurement)},
        "old": {"selected": old_selected, "projection": old_projection, "encoding": encode_request(old_selected, measurement)},
        "new": {"selected": new_selected, "projection": new_projection,
            "encoding": encode_request(new_selected, measurement),
            "protected_selected": protected_selected, "protected_encoding": protected_encoding},
        "native_measurement_identity": copy.deepcopy(measurement.identity)}
    for key in ("old", "new"):
        projection, encoding = result[key]["projection"], result[key]["encoding"]
        if (projection["selected_prompt_tokens"] != encoding["prompt_tokens"]
                or projection["rendered_prompt_sha256"] != encoding["rendered_prompt_sha256"]
                or projection["input_ids_sha256"] != encoding["input_ids_sha256"]):
            raise ValueError("Full native encoding and selected projection disagree")
    if (new_projection["protected_prompt_tokens"] != protected_encoding["prompt_tokens"]
            or new_projection["protected_input_ids_sha256"] != protected_encoding["input_ids_sha256"]
            or new_projection["protected_rendered_prompt_sha256"] != protected_encoding["rendered_prompt_sha256"]):
        raise ValueError("Full native encoding and protected projection disagree")
    return result
