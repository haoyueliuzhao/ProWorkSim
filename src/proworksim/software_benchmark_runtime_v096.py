"""Private 79-ID runtime, current FIFO guard, and separately frozen PROJECT bundle."""
from __future__ import annotations

from types import ModuleType

from . import software_benchmark_api_scope_v096 as scope
from . import software_benchmark_dispatch_v066 as original
from . import software_benchmark_recovery_bindings_v089 as base_bindings
from .software_benchmark_candidates_v054 import reference
from .software_benchmark_expansion_episode_v069 import clone_namespace

VERSION = 'v096-original-first-entry-private-bindings-r1'


def dispatch_view(guard):
    constraints = {**original.CONSTRAINTS,'fresh_generation_slots':79,
        'generation_token_upper_bound':395_000_000,'api_generation_token_upper_bound':395_000_000,
        'api_total_budget_cny':'1700.00','maximum_actor_containers':79,'maximum_controller_containers':79,
        'maximum_control_containers':0,'maximum_code_score_containers':79,
        'maximum_delivery_score_containers':41,'maximum_score_containers':120,
        'maximum_containers':278,'maximum_named_volumes':79,'maximum_model_residents':0}
    namespace = clone_namespace(original,VERSION=VERSION,CONSTRAINTS=constraints,PLAN_FILE=scope.PLAN_FILE,
        AUTHORIZATION_FILE=scope.AUTH_FILE,RESUME_FILE=scope.INVENTORY_FILE,
        COORDINATOR_RUN_ROOT=scope.COORDINATOR_ROOT)

    def allowed(operation='v066.run',**identity):
        guard(operation,**identity)
        return {'version':VERSION,'status':'approved','plan':reference(scope.PLAN_FILE),
            'sources':reference(scope.SOURCE_FILE),'constraints':namespace['CONSTRAINTS']}

    namespace['require_v066_allowed']=allowed
    value=ModuleType(__name__+'.private_dispatch')
    value.__dict__.update(namespace)
    value.__file__=__file__
    return value


_bindings = clone_namespace(base_bindings,scope=scope,VERSION=VERSION,__file__=__file__,__name__=__name__)
_bindings['dispatch_view']=dispatch_view
bindings=ModuleType(__name__+'.bindings')
bindings.__dict__.update(_bindings)
_original_episode=bindings.episode


def episode(policy):
    from .software_benchmark_api_bridge_v094 import bind_episode
    from . import software_benchmark_sdk_bundle_v096 as bundle
    value=bind_episode(_original_episode(policy),scope_guard=policy.require_v066_allowed)
    namespace=value.run_episode.__globals__
    if namespace is not value._run.__globals__ or namespace.get('_run') is not value._run:
        raise ValueError('The actual episode entrypoint and execution globals differ')
    namespace['runtime']=bundle
    value.__dict__['runtime']=bundle
    if value._run.__globals__['runtime'] is not bundle:
        raise RuntimeError('Actual controller preparation did not retain the new bundle')
    return value


bindings.episode=episode


class PhysicalRuntimeView:
    def __init__(self,delegate,rows):
        self.delegate=delegate
        self.physical_rows={row['slot_id']:row for row in rows}
        canonical=scope.canonical_rows()
        self.canonical_rows={row['slot_id']:row for row in canonical}
        if (rows!=scope.load(reference(scope.INVENTORY_FILE))['rows']
                or self.physical_rows.keys()!=self.canonical_rows.keys()):
            raise PermissionError('Physical and original logical registries differ')
        for position,old in enumerate(canonical):
            row=self.physical_rows[old['slot_id']]
            scope._validate_physical_mapping_at(row,old,scope.load(row['configuration']),
                scope.load(old['configuration']),position)

    def __getattr__(self,name):
        return getattr(self.delegate,name)

    def canonical_row(self,row):
        if self.physical_rows.get(row.get('slot_id'))!=row:
            raise PermissionError('Broker cannot accept an unsealed physical row')
        old=self.canonical_rows[row['slot_id']]
        scope.validate_physical_mapping(row,old,scope.load(row['configuration']),scope.load(old['configuration']))
        return old

    def transport_factory(self,row,output):
        return self.delegate.transport_factory(self.canonical_row(row),output)

    def usage_for_slot(self,row):
        return self.delegate.usage_for_slot(self.canonical_row(row))


def build_api_runtime(*,rows,fd_guard,identity_file,scope_guard=scope.require_allowed):
    from . import software_benchmark_api_budget_v096 as budget
    raw=budget.build_runtime(scope_guard=scope_guard,identity_file=identity_file)
    return PhysicalRuntimeView(budget.RuntimeView(raw,fd_guard),rows)


def pressure_module():
    from .software_benchmark_pressure_v096 import pressure_view
    return pressure_view(scope.canonical_rows(),scope=scope)


# The async queue imports this factory without importing a scorer dependency
# manifest inside the API/tokenizer interpreter.
class GradingAdapter:
    @staticmethod
    def factory(*,watchdog_guard):
        from .software_benchmark_grading_v096 import factory
        return factory(watchdog_guard=watchdog_guard)


grading=GradingAdapter()
