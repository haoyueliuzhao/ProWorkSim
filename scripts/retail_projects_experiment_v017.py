"""Finite real-world formal evaluator controls; CPU witnesses are not actors."""
import argparse
from pathlib import Path

from proworksim.core.adoption import binding_for
from proworksim.core.work import current_id
from proworksim.core.world import object_identity
from proworksim.episode import begin_episode, finish_episode
from proworksim.experience import ExperienceRecorder, capture_port
from proworksim.retail_project_rewards import assess_project_episode
from proworksim.scenarios import ScenarioController
from proworksim.storage import atomic_write, json_bytes
from proworksim.templates.retail_projects import ACTORS, SOURCES
from proworksim.templates.retail_projects_v017 import build_project_case
from scripts.retail_projects_experiment_v016 import sql_program


def run_case(output, *, changed=False, control=None):
    output = Path(output)
    prepared = build_project_case('retail-projects-v17-' + ('change' if changed else 'static'), output)
    world, recorder = prepared.world, ExperienceRecorder()
    captures = {p: [] for p in ACTORS}
    ports = {p: capture_port(world.session(a, p), captures[p]) for p, a in ACTORS.items()}
    controller = ScenarioController(prepared.deployment, recorder=recorder)
    controller.record_environment()
    episode = output / 'episode'
    begin_episode(world, episode, experience=recorder.snapshot(), work_ids=[],
                  work_nodes=[p + '::build' for p in ACTORS], scenario=prepared.scenario, policies={'origin': 'cpu_fixture'})
    early = None
    if control == 'later_backfill':
        finish_episode(world, episode, experience=recorder.snapshot(), termination={'status': 'bounded_early_end'})
        early = assess_project_episode(episode)
        episode = output / 'later-episode'
        begin_episode(world, episode, experience=recorder.snapshot(), work_ids=[], work_nodes=[p + '::build' for p in ACTORS],
                      scenario=prepared.scenario, policies={'origin': 'cpu_fixture_later_work'})

    def work(project):
        base = project + '::build'
        return current_id(world.state, world.state['projects'][project].get('maintenance_heads', {}).get(base, base))

    def call(project, action, **arguments):
        reply = ports[project].call(action, request_key=f'formal-cpu-{len(recorder.events)}', **arguments)
        recorder.record('tool_call', captures[project][-1]['payload'], ACTORS[project])
        controller.record_environment()
        if not reply['ok']:
            raise ValueError({'project': project, 'action': action, 'response': reply})
        return reply['result']

    def read(project, alias):
        return call(project, 'read_alias', alias=alias, work_id=work(project))

    def publish(project, alias, targets):
        reference = read(project, alias)['reference']
        return call(project, 'publish', **reference, target_projects=targets + [project])

    def build(project):
        refs = []
        for alias, (pid, name) in SOURCES[project].items():
            source = call(project, 'read_object', object_id=object_identity(pid, name), work_id=work(project))
            raw_ref = source['reference']
            reference = {'object_id': raw_ref.get('object_id', raw_ref.get('artifact_id')), 'version_id': raw_ref['version_id']}
            binding = binding_for(world.state, work(project), alias)
            if binding is None:
                call(project, 'adopt', alias=alias, **reference, policy='current_published', work_ids=[work(project)])
            elif binding['version_id'] != reference['version_id']:
                call(project, 'adopt_version', alias=alias, version_id=reference['version_id'], work_id=work(project))
            refs.append(reference)
        code = sql_program(project)
        if control in {'common_wrong', 'label_only'} and project in {'P1', 'P2'}:
            code['models'][0]['sql'] = code['models'][0]['sql'].replace('COALESCE(a.revenue_pence,0)', '(COALESCE(a.revenue_pence,0)+1)')
        call(project, 'write_object', alias='code', data=code, work_id=work(project), dependencies=refs)
        built = call(project, 'sql_build', work_id=work(project), code_alias='code', output_alias='result', input_aliases=list(SOURCES[project]))
        if built['execution_status'] not in {'success', 'tests_failed'}:
            raise ValueError({'actual_sql_error': built})
        if project == 'P2' and control in {'label_only', 'no_current_build'}:
            data = read(project, 'result')['data']
            if control == 'label_only':
                data.update(status='success', claimed_correct=True)
            call(project, 'write_object', alias='result', data=data, dependencies=refs, work_id=work(project))
        return built

    def deliver(project, *, late=False):
        if not late:
            call(project, 'submit', work_id=work(project), artifacts=['code', 'result'])
        if project != 'P3':
            for alias in ('code', 'result'):
                publish(project, alias, ['P3'])

    report = {'control': control, 'changed': changed, 'model_execution': False}
    try:
        data = read('P0', 'data')['data']
        note = read('P0', 'release_note')['data']
        call('P0', 'write_object', alias='release_note', data={**note, 'checked_source_row_count': len(data['tables']['retail']['rows'])}, work_id=work('P0'))
        call('P0', 'submit', work_id=work('P0'), artifacts=['data', 'release_note'])
        for alias in ('data', 'release_note'):
            publish('P0', alias, ['P1', 'P2'])
        for project in ('P1', 'P2', 'P3'):
            build(project)
            deliver(project, late=control == 'late_fixed_source' and project == 'P1')
        if control == 'late_fixed_source':
            call('P1', 'submit', work_id=work('P1'), artifacts=['code', 'result'])
        if changed:
            effects = controller.tick()
            if not effects or any(e['status'] != 'executed' for e in effects):
                raise ValueError({'declared_change_not_executed': effects})
            result = world.session('operator').call('wait', ticks=1)
            recorder.record('controller_action', {'origin': 'environment', 'tool': 'wait', 'response': result})
            controller.record_environment()
            projects = ('P1', 'P3') if control == 'mixed_versions' else ('P1', 'P2', 'P3')
            for project in projects:
                build(project)
                deliver(project)
        finish_episode(world, episode, experience=recorder.snapshot(), termination={'status': 'cpu_path_closed', 'controller': controller.snapshot()})
        report['assessment'] = assess_project_episode(episode)
        if early is not None:
            after = assess_project_episode(output / 'episode')
            report['early_assessment'] = early
            report['early_after_later_work'] = after
            report['old_episode_unchanged'] = early == after
    except Exception as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
        finish_episode(world, episode, experience=recorder.snapshot(), termination={'status': 'environment_error', 'reason': str(error)})
    report['actions'] = sum(e['kind'] == 'tool_call' for e in recorder.events)
    report['controller'] = controller.snapshot()
    atomic_write(output / 'capture.json', json_bytes(captures))
    atomic_write(output / 'report.json', json_bytes(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    for name, changed, control, expected in [
        ('static', False, None, 1), ('change', True, None, 1),
        ('common_wrong', False, 'common_wrong', 0), ('mixed_versions', True, 'mixed_versions', 0),
        ('label_only', False, 'label_only', 0), ('no_current_build', False, 'no_current_build', 0),
        ('late_fixed_source', False, 'late_fixed_source', 0), ('later_backfill', False, 'later_backfill', 1),
    ]:
        report = run_case(args.output / name, changed=changed, control=control)
        assessment = report.get('assessment', {})
        passed = not report.get('error') and assessment.get('eligible') is True and assessment.get('reward') == expected
        if control == 'common_wrong':
            passed &= assessment.get('dimensions') == {'P1_quality': False, 'P2_quality': False, 'P3_fixed_input_fidelity': True, 'overall_business_goal': False}
        if control == 'later_backfill':
            passed &= report.get('old_episode_unchanged') is True and report.get('early_assessment', {}).get('reward') == 0
        rows.append({'name': name, 'reward': assessment.get('reward'), 'expected': expected,
                     'dimensions': assessment.get('dimensions'), 'passed': passed, 'actions': report['actions'], 'error': report.get('error')})
        print(rows[-1], flush=True)
    atomic_write(args.output / 'summary.json', json_bytes({'version': 'retail-project-controls-v0.17', 'model_execution': False,
                                                          'cases': rows, 'passed': all(r['passed'] for r in rows)}))


if __name__ == '__main__':
    main()
