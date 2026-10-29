"""Privately bind every recovery episode and scoring guard to the new owner."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import ModuleType

from . import software_benchmark_api_scope_v094 as scope
from . import software_benchmark_recovery_bindings_v089 as original_bindings
from . import software_benchmark_recovery_grading_v089 as original_grading
from .software_benchmark_deepseek_runtime_v069 import private_function
from .software_benchmark_expansion_episode_v069 import clone_namespace
from .software_benchmark_candidates_v054 import reference

VERSION = 'v094-private-unentered-runtime-bindings-r1'

bindings = ModuleType(__name__+'.bindings')
bindings.__dict__.update(clone_namespace(original_bindings, scope=scope, VERSION=VERSION,
                                        __file__=__file__, __name__=bindings.__name__))
_original_episode = bindings.episode


def episode_with_current_bridge(policy):
    from .software_benchmark_api_bridge_v094 import bind_episode
    return bind_episode(_original_episode(policy), scope_guard=policy.require_v066_allowed)


bindings.episode = episode_with_current_bridge

_grading = clone_namespace(original_grading, scope=scope, bindings=bindings,
                           VERSION=VERSION, __file__=__file__, __name__=__name__)


class Grading(original_grading.Grading):
    __init__ = private_function(original_grading.Grading.__init__, **_grading)

    def run_request(self, request_ref, stop_event=None):
        request = scope.load(request_ref)
        scope.require_grading_allowed('v094.run', slot_id=request['slot_id'], instance_id=request['instance_id'])

        def fixed_python(arguments):
            if arguments[:2] != ['-m', 'proworksim.software_benchmark_scorer_v066']:
                raise ValueError('Only the bounded official score child can be redirected')
            return self.base.fixed_python(['-m', 'proworksim.software_benchmark_recovery_runtime_v094', *arguments[2:]])

        return private_function(self.base.run_request, fixed_python=fixed_python)(request_ref, stop_event=stop_event)


_grading['Grading'] = Grading
grading = ModuleType(__name__+'.grading')
grading.__dict__.update(_grading)


class PhysicalRuntimeView:
    """Map exact new physical launches onto unchanged unused API identities."""
    def __init__(self, delegate, rows):
        self.delegate = delegate
        self.physical_rows = {row['slot_id']: row for row in rows}
        self.canonical_rows = {row['slot_id']: row for row in scope.canonical_rows()}
        if (rows != scope.load(reference(scope.INVENTORY_FILE))['rows']
                or self.physical_rows.keys() != self.canonical_rows.keys()):
            raise PermissionError('Physical and canonical attempt registries differ')
        for row in rows:
            old = self.canonical_rows[row['slot_id']]
            scope.validate_physical_mapping(row, old, scope.load(row['configuration']), scope.load(old['configuration']))

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def canonical_row(self, row):
        if self.physical_rows.get(row.get('slot_id')) != row:
            raise PermissionError('Broker cannot accept another physical launch or altered task')
        old = self.canonical_rows[row['slot_id']]
        scope.validate_physical_mapping(row, old, scope.load(row['configuration']), scope.load(old['configuration']))
        return old

    def transport_factory(self, row, output):
        return self.delegate.transport_factory(self.canonical_row(row), output)

    def usage_for_slot(self, row):
        return self.delegate.usage_for_slot(self.canonical_row(row))


def build_api_runtime(*, rows, fd_guard, identity_file, scope_guard=scope.require_allowed):
    from . import software_benchmark_deepseek_budget_v089 as budget
    raw = budget.build_runtime(scope_guard=scope_guard, retry_rows=scope.canonical_rows(),
        inventory_ref=reference(scope.CANONICAL_INVENTORY_FILE), identity_file=identity_file)
    return PhysicalRuntimeView(budget.RuntimeView(raw, fd_guard), rows)


def pressure_module():
    from types import SimpleNamespace
    from .software_benchmark_recovery_pressure_v091 import pressure_view
    # Pressure cancels by logical ownership token, not by physical index. The
    # canonical sealed 44 IDs are unchanged, while the manager limits are new.
    view = SimpleNamespace(**{**vars(scope), 'INVENTORY_FILE': scope.CANONICAL_INVENTORY_FILE})
    return pressure_view(scope.canonical_rows(), scope=view)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    value = grading.score_request(json.loads(parser.parse_args().request.read_bytes()))
    print(json.dumps({key: value[key] for key in ('resource_key', 'status', 'resolved')}))
