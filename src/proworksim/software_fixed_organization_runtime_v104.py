"""Offline-injected SDK runtime for the five evidence-bound organizations.

All sessions share the original team budget and private harness. Organization
state restricts eligible actors; the scheduler never manufactures a decision,
test, merge, handoff, submission, or next sprint.
"""
from __future__ import annotations

import copy
from types import SimpleNamespace

from . import software_fixed_organization_runtime_v065 as previous
from . import software_fixed_organization_world_v104 as world
from .software_benchmark_budget_closure_v103 import RemainingBudgetContextTransport
from .software_benchmark_expansion_episode_v069 import clone_namespace, clone_function
from .software_fixed_organization_v104 import validate_organization, require_evaluation_disabled

VERSION = 'v104-evidence-bound-five-organization-runtime-r1'
base = previous.base
ProjectOwner = previous.ProjectOwner
ManagedTeamBudget = previous.ManagedTeamBudget
close_runtime = previous.close_runtime


class OrganizationSchedule:
    """Fair finite actor selection over current contract-eligible identities."""
    def __init__(self, spec):
        self.spec = validate_organization(spec)
        self.members = tuple(spec['fixed_members'])
        self.position = self.executed = self.skipped = 0

    def choose(self, runnable):
        runnable = set(runnable)
        if not runnable <= set(self.members):
            raise ValueError('No ghost or replacement member may enter the schedule')
        for _ in self.members:
            member = self.members[self.position % len(self.members)]
            if member in runnable:
                return {'organization_id': self.spec['id'], 'member': member,
                    'slot_position': self.position, 'cycle': self.position // len(self.members),
                    'phase_index': 0, 'phase_name': 'contract-eligible fair opportunity',
                    'selection_basis': 'persisted organization eligibility, then fair round-robin'}
            self.position += 1
            self.skipped += 1
        return None

    def consume(self, selection):
        if selection['slot_position'] != self.position:
            raise ValueError('Only the selected actor opportunity may be consumed')
        self.position += 1
        self.executed += 1

    def snapshot(self):
        return {'organization_id': self.spec['id'], 'position': self.position,
            'executed_opportunities': self.executed, 'skipped_unavailable_positions': self.skipped,
            'cycle_length': len(self.members), 'world_actions_created_by_scheduler': 0,
            'stage_changes_caused_by_round_robin': 0}


class OrganizationRuntime(previous.OrganizationRuntime):
    def __init__(self, *args, offline_fixture=False, **kwargs):
        if offline_fixture is not True:
            require_evaluation_disabled()
        base.OrganizationRuntime.__init__(self, *args, **kwargs)
        self.offline_fixture = True
        self.fixed_spec = validate_organization(self.prepared.case['fixed_organization'])
        self.members = tuple(self.fixed_spec['fixed_members'])
        self.schedule = OrganizationSchedule(self.fixed_spec)
        self._selected = None
        self.organization_blocked = False

    def select_next(self):
        self.sync_members()
        runnable = set(self.labels) - set(self.stopped) - set(self.waiting)
        eligible = set(self.prepared.world.organization_active_members())
        if not eligible <= set(self.members):
            raise ValueError('Organization eligibility introduced another identity')
        self.organization_blocked = bool(runnable) and not (runnable & eligible)
        self._selected = self.schedule.choose(runnable & eligible)
        if self._selected is not None:
            self.cursor = self.labels.index(self._selected['member'])
        return copy.deepcopy(self._selected)

    def _step(self):
        if self.offline_fixture is not True:
            require_evaluation_disabled()
        actual_world = self.prepared.world
        if getattr(actual_world, 'fixed_candidates_closed', False):
            raise ValueError('No model opportunity after candidate lock')
        selection = self._selected or self.select_next()
        if selection is None:
            raise ValueError('No organization-eligible member is runnable')
        self._selected = None
        member = selection['member']
        # Recheck immediately before the single-writer opportunity. A cached
        # selection cannot bypass a newly accepted organization transition.
        if member not in actual_world.organization_active_members():
            raise ValueError('The selected organization state became stale')
        self.cursor = self.labels.index(member)
        actual_world.scheduled_member = member
        actual_world.schedule_observation = copy.deepcopy(selection)
        before = self.opportunities
        self.recorder.record('fixed_organization_opportunity', {
            **selection, 'organization_runtime_version': VERSION,
            'team_budget_before': self.team_budget.snapshot()}, worker_id=member)
        try:
            return base.OrganizationRuntime._step(self)
        finally:
            try:
                if self.opportunities > before:
                    if self.opportunities != before + 1:
                        raise ValueError('One dispatch must consume exactly one real opportunity')
                    changed = actual_world.consume_organization_opportunity(actor=member)
                    self.recorder.record('organization_opportunity_consumed', {
                        'version': VERSION, 'opportunity_ordinal': self.opportunities,
                        'member_id': member, 'organization_state_transition': changed,
                        'automatic_work_created': False}, worker_id=member)
                    self.schedule.consume(selection)
            finally:
                actual_world.scheduled_member = None

    def snapshot(self):
        value = base.OrganizationRuntime.snapshot(self)
        value.update(organization_runtime_version=VERSION,
            fixed_organization=copy.deepcopy(self.fixed_spec), fixed_schedule=self.schedule.snapshot(),
            organization_eligible_members=list(self.prepared.world.organization_active_members()),
            organization_contract_blocked=self.organization_blocked)
        return value


# Clone the existing assembly and public callback against the new world and
# worker factory. No old module globals or frozen source files are modified.
def _repaired_worker_type():
    # The fixed SDK dependency set is needed only for a real SDK construction,
    # not ordinary World-only CPU checks using the project interpreter.
    from .software_benchmark_managed_v103 import worker_type
    return worker_type()


aligned = SimpleNamespace(**{**vars(previous.aligned),
    'ManagedContextTransport': RemainingBudgetContextTransport,
    'worker_type': _repaired_worker_type})
_namespace = clone_namespace(previous, world=world, aligned=aligned, VERSION=VERSION,
    OrganizationRuntime=OrganizationRuntime, FixedPhaseSchedule=OrganizationSchedule,
    validate_organization=validate_organization, require_evaluation_disabled=require_evaluation_disabled)


class PublicTestCallback(previous.PublicTestCallback):
    pass


for _name in ('__init__', 'bind_world', '__call__'):
    setattr(PublicTestCallback, _name,
            clone_function(getattr(previous.PublicTestCallback, _name), _namespace))
_namespace['PublicTestCallback'] = PublicTestCallback
worker_config = _namespace['worker_config']
prepare_case = _namespace['prepare_case']
build_runtime = _namespace['build_runtime']
lock_fixed_candidates = _namespace['lock_fixed_candidates']


def run_fragment(prepared, runtime, *, on_opportunity=None):
    """Run only an explicitly injected CPU fixture; preserve local rule refusals."""
    if getattr(runtime, 'offline_fixture', False) is not True:
        require_evaluation_disabled()
    outcomes, integrity_failure, reason = [], None, None
    deadline = runtime.deadline
    while True:
        deadline.check_hard('v104_organization_schedule')
        runtime.sync_members()
        budget = runtime.team_budget.snapshot()
        if budget.get('integrity_failure'):
            integrity_failure, reason = budget['integrity_failure'], 'execution_integrity_failure'
            break
        if any(budget[key] <= 0 for key in ('remaining_decisions', 'remaining_attempts', 'available_tokens')):
            reason = 'shared_team_pool_exhausted'
            break
        base._wake_reachable(runtime)
        selection = runtime.select_next()
        if selection is None:
            reason = ('organization_contract_blocked' if runtime.organization_blocked
                      else 'all_members_stopped_or_no_reachable_event')
            break
        if not deadline.admit_new_work('before_fixed_member_opportunity'):
            reason = 'administrative_soft_deadline'
            break
        member, first_event = selection['member'], len(runtime.recorder.events)
        result = runtime.step()
        status = result['status']
        rejection = (result.get('response') or {}).get('error', {}).get('rejection', {}).get('code')
        if rejection in {'world_power_denied', 'project_power_denied', 'trusted_context_override'}:
            result = {**result, 'original_status': status, 'status': 'model_permission_error',
                'reason': 'Trusted WorldCore permission/context boundary: ' + rejection}
            status = result['status']
            runtime.roles[member]['status'] = status
            runtime.recorder.record('critical_permission_boundary', {'code': rejection,
                'original_status': result['original_status'], 'status': status}, worker_id=member)
        outcomes.append(result)
        runtime.sync_members()
        fatal = status in previous.TECHNICAL_FAILURES and not (status == 'policy_error' and result.get('action_performed'))
        if status == 'administrative_soft_deadline':
            reason = status
        elif status == 'completed':
            base._sleep(runtime, member, status, result)
        elif fatal or status in previous.TERMINAL - {'completed', 'policy_error', 'model_format_error'}:
            runtime.stopped[member] = status
            runtime.terminal_details[member] = previous._terminal_detail(
                member, result, runtime, runtime.recorder.events[first_event:])
            runtime.waiting.pop(member, None)
            runtime.work_ended.pop(member, None)
            if fatal:
                integrity_failure = {'member': member, 'status': status, 'reason': result.get('reason')}
                reason = 'execution_integrity_failure'
        elif status in {'worker_waiting', 'world_blocked'}:
            base._sleep(runtime, member, status, result)
        runtime.note_population('v104_member_opportunity')
        if on_opportunity:
            on_opportunity(result)
        if integrity_failure is not None or status == 'administrative_soft_deadline':
            break
    runtime.note_population('v104_episode_closed')
    boundary = {'version': VERSION, 'status': 'execution_integrity_blocked' if integrity_failure else 'bounded_work_closed',
        'kind': 'fixed_roster_repository_terminal', 'organization_id': runtime.fixed_spec['id'],
        'closure_reason': reason, 'outcomes': outcomes, 'execution_integrity_failure': integrity_failure,
        'opportunities': runtime.opportunities, 'actions': runtime.actions,
        'team_budget': base.budget_snapshot(runtime, prepared), 'schedule': runtime.schedule.snapshot(),
        'initial_members': list(runtime.members), 'born_members': list(runtime.labels),
        'role_stops': copy.deepcopy(runtime.stopped), 'waiting_members': copy.deepcopy(runtime.waiting),
        'current_work_ended': copy.deepcopy(runtime.work_ended), 'work_boundaries': copy.deepcopy(runtime.work_boundaries),
        'terminal_details': copy.deepcopy(runtime.terminal_details), 'continuation': False,
        'execution_kind': 'explicit_scripted_cpu_fixture', 'real_model_calls_authorized': 0,
        'scripted_counters_are_not_actual_model_consumption': True,
        'training_eligible': False, 'admission_eligible': False,
        'action_error_policy': base.error_policy_summary(runtime),
        'administrative_censoring': deadline.prevented_work, 'deadline_receipt': deadline.snapshot(runtime.team_budget)}
    runtime.recorder.record('run_boundary', boundary)
    return boundary
