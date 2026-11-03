"""Necessary local SDK schema control; no model, network or benchmark execution."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import sys

os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP='True', OPENHANDS_SUPPRESS_BANNER='1',
                  HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
network_attempts = []


def audit(event, args):
    if event == 'socket.getaddrinfo' or (
        event in {'socket.connect', 'socket.bind', 'socket.sendto'}
        and args and getattr(args[0], 'family', None) in (socket.AF_INET, socket.AF_INET6)
    ):
        network_attempts.append(event)
        raise RuntimeError('External network is forbidden in this local CPU control')


sys.addaudithook(audit)

def main():
    from openhands.sdk.tool import Action
    from proworksim.software_benchmark_public_tests_v110 import SELECTION_SCHEMA

    schema = {'type': 'object', 'additionalProperties': False, 'required': [],
              'properties': {'selection': SELECTION_SCHEMA}}
    kind = Action.from_mcp_schema('PublicSelectionRoundtripV110', schema)
    cases = [{}, {'selection': {'kind': 'full'}},
             {'selection': {'kind': 'pytest', 'targets': ['tests/test_a.py::test_one'],
                            'keyword': 'one and not slow', 'markers': 'not slow'}},
             {'selection': {'kind': 'django', 'targets': ['i18n.tests.SomeTests.test_one']}},
             {'selection': {'kind': 'sympy', 'targets': ['sympy/core/tests/test_basic.py'],
                            'keywords': ['test_one', 'test_two']}}]
    records = []
    for original in cases:
        observed = kind.model_validate(original).model_dump(mode='json', by_alias=True,
            exclude_unset=True, exclude_computed_fields=True)
        assert observed == original, (original, observed)
        records.append({'arguments': original, 'roundtrip_equal': True})
    result = {'version': 'v110-public-test-sdk-control-r1', 'passed': True,
              'actual_sdk_action_roundtrips': records, 'network_attempts': network_attempts,
              'api_calls': 0, 'docker_operations': 0, 'benchmark_test_processes': 0,
              'scope': 'Real pinned OpenHands Action parsing and serialization, no model execution'}
    target = Path('artifacts/software-benchmark-v110/public-test-controls-r1/sdk-control.json')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
