"""Only a parser metadata completion can reuse unchanged numerical execution."""

import pytest

from scripts.optimization_source_review_v019 import canonical_candidate


def test_exact_existing_parser_metadata_is_the_only_accepted_addition():
    before = """from .candidate_runtime_v017 import CandidateActor as PreviousActor
import copy
class CandidateActor(PreviousActor):
    def __init__(self, profile):
        profile.update(version="candidate-runtime-v0.19", attention="sdpa_explicit_kv")
        execute_real_model(profile)
"""
    after = before.replace(
        "import copy", "from .candidate_runtime_v017 import PARSER_CONTRACT\nimport copy"
    ).replace(
        "profile.update(version=",
        "profile.update(parser_contract=copy.deepcopy(PARSER_CONTRACT), version=",
    )
    assert canonical_candidate(before, allow_metadata_fix=False) == canonical_candidate(
        after, allow_metadata_fix=True
    )
    assert canonical_candidate(before, allow_metadata_fix=False) != canonical_candidate(
        after.replace("execute_real_model(profile)", "execute_different_model(profile)"),
        allow_metadata_fix=True,
    )
    with pytest.raises(ValueError, match="unchanged"):
        canonical_candidate(
            after.replace("copy.deepcopy(PARSER_CONTRACT)", "copy.deepcopy(CHANGED_PARSER)"),
            allow_metadata_fix=True,
        )
    with pytest.raises(ValueError, match="exactly one"):
        canonical_candidate(before, allow_metadata_fix=True)
