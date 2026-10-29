"""Privately bind every recovery episode and scoring guard to the new owner."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import ModuleType

from . import software_benchmark_api_scope_v091 as scope
from . import software_benchmark_recovery_bindings_v089 as original_bindings
from . import software_benchmark_recovery_grading_v089 as original_grading
from .software_benchmark_deepseek_runtime_v069 import private_function
from .software_benchmark_expansion_episode_v069 import clone_namespace

VERSION = 'v091-private-unentered-runtime-bindings-r1'

bindings = ModuleType(__name__+'.bindings')
bindings.__dict__.update(clone_namespace(original_bindings, scope=scope, VERSION=VERSION,
                                        __file__=__file__, __name__=bindings.__name__))

_grading = clone_namespace(original_grading, scope=scope, bindings=bindings,
                           VERSION=VERSION, __file__=__file__, __name__=__name__)


class Grading(original_grading.Grading):
    __init__ = private_function(original_grading.Grading.__init__, **_grading)

    def run_request(self, request_ref, stop_event=None):
        request = scope.load(request_ref)
        scope.require_grading_allowed('v091.run', slot_id=request['slot_id'], instance_id=request['instance_id'])

        def fixed_python(arguments):
            if arguments[:2] != ['-m', 'proworksim.software_benchmark_scorer_v066']:
                raise ValueError('Only the bounded official score child can be redirected')
            return self.base.fixed_python(['-m', 'proworksim.software_benchmark_recovery_runtime_v091', *arguments[2:]])

        return private_function(self.base.run_request, fixed_python=fixed_python)(request_ref, stop_event=stop_event)


_grading['Grading'] = Grading
grading = ModuleType(__name__+'.grading')
grading.__dict__.update(_grading)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    value = grading.score_request(json.loads(parser.parse_args().request.read_bytes()))
    print(json.dumps({key: value[key] for key in ('resource_key', 'status', 'resolved')}))
