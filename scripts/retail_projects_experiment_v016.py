"""Finite CPU witness of actual retail project publication and feedback.

SQL below is a private feasibility program, never provided to an H1/model run.
Only explicit world calls edit/build/publish/consume products. Host-side Decimal
checks happen after work and provide no repair or numeric answer to a worker.
"""
import argparse
import copy
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.core.adoption import binding_for
from proworksim.core.work import current_id
from proworksim.core.world import object_identity
from proworksim.domains.retail_work import expected_metrics
from proworksim.episode import begin_episode, finish_episode
from proworksim.experience import ExperienceRecorder, capture_port
from proworksim.scenarios import build_scenario, save_deployment
from proworksim.storage import json_bytes
from proworksim.templates.retail_projects import ACTORS, SOURCES, VERSION, request, scenario_spec
from proworksim.templates.retail_work import witness_code


def records(table):
    return [dict(zip([c['name'] for c in table['columns']], r)) for r in table['rows']]


def sql_program(project):
    if project == 'P1':
        return witness_code()
    if project == 'P2':
        code = witness_code()
        sql = code['models'][0]['sql']
        code['models'] = [{'name': 'customer_analysis', 'sql': 'WITH customer_metrics AS (' + sql + ") SELECT CustomerID,revenue_pence,invoice_count,CASE WHEN revenue_pence>0 THEN 'positive' WHEN revenue_pence<0 THEN 'negative' ELSE 'zero' END AS segment FROM customer_metrics ORDER BY CustomerID"}]
        code['tests'] = []
        code['config']['exports'] = ['customer_analysis']
        return code
    if project == 'P3':
        return {'models': [{'name': 'integration', 'sql': 'SELECT COALESCE(m.CustomerID,a.CustomerID) AS CustomerID,m.revenue_pence AS metrics_pence,a.revenue_pence AS analysis_pence,m.revenue_pence-a.revenue_pence AS difference_pence,m.invoice_count AS metrics_invoices,a.invoice_count AS analysis_invoices,m.invoice_count-a.invoice_count AS invoice_difference FROM metrics m FULL OUTER JOIN customer_analysis a ON m.CustomerID=a.CustomerID ORDER BY CustomerID'}],
                'tests': [{'name': 'same_amount_count', 'sql': 'SELECT * FROM integration WHERE difference_pence<>0 OR invoice_difference<>0 OR metrics_pence IS NULL OR analysis_pence IS NULL'}],
                'config': {'exports': ['integration']}}
    raise ValueError('Unknown SQL project')


def run(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    deployment = build_scenario(scenario_spec(), output / 'world')
    if deployment.status != 'ready':
        raise ValueError(deployment.diagnostics)
    world = deployment.world
    captures = {p: [] for p in ACTORS}
    ports = {p: capture_port(world.session(a, p), captures[p]) for p, a in ACTORS.items()}
    recorder, offset = ExperienceRecorder(), len(world.state['event_history'])
    report = {'version': VERSION, 'model_execution': False, 'source': code_identity(),
              'origin': 'explicit_cpu_feasibility_program', 'editions': [], 'controls': [],
              'scope': 'Real four-project relationships and finite content checks; not autonomous model capability or parameter learning. P2/P3 independent checks run in this host report, not registered training reward.'}
    episode = output / 'episode'
    begin_episode(world, episode, experience=recorder.snapshot(), work_ids=[p + '::build' for p in ACTORS], scenario=deployment.spec, policies={})

    def work(project):
        return current_id(world.state, project + '::build')

    def call(project, tool, *, allow_error=False, **kwargs):
        nonlocal offset
        result = ports[project].call(tool, request_key=f'project-witness-{len(recorder.events)}', **kwargs)
        recorder.record('tool_call', captures[project][-1]['payload'], ACTORS[project])
        for event in world.state['event_history'][offset:]:
            recorder.record('environment_event', event)
        offset = len(world.state['event_history'])
        if not result['ok'] and not allow_error:
            raise ValueError({'project': project, 'tool': tool, 'arguments': kwargs, 'response': result})
        return result if allow_error else result['result']

    def read(project, alias):
        return call(project, 'read_alias', alias=alias, work_id=work(project))

    def reference(value):
        ref = value.get('reference', value)
        return {'object_id': ref.get('object_id', ref.get('artifact_id')), 'version_id': ref['version_id']}

    def share(project, alias, targets):
        ref = reference(read(project, alias))
        for target in targets:
            call(project, 'share', **ref, target_project=target, actor_ids=[ACTORS[target]], follow_updates=True)
        call(project, 'publish', **ref, target_projects=sorted(set(targets + [project])))
        return ref

    def consume(project):
        refs = []
        for alias, (pid, object_alias) in SOURCES[project].items():
            response = call(project, 'read_object', object_id=object_identity(pid, object_alias), work_id=work(project))
            ref = reference(response)
            binding = binding_for(world.state, work(project), alias)
            if binding is None:
                call(project, 'adopt', alias=alias, **ref, policy='current_published', work_ids=[work(project)])
            elif binding['version_id'] != ref['version_id']:
                call(project, 'adopt_version', alias=alias, version_id=ref['version_id'], work_id=work(project))
            refs.append(ref)
        return refs

    def build(project, *, write=True, expected_status='success'):
        refs = consume(project)
        if write:
            call(project, 'write_object', alias='code', work_id=work(project), data=sql_program(project), dependencies=refs)
        built = call(project, 'sql_build', work_id=work(project), code_alias='code', output_alias='result', input_aliases=list(SOURCES[project]))
        if built['execution_status'] != expected_status:
            raise ValueError({'actual_sql_failed': project, 'response': built})
        return read(project, 'result')

    try:
        # Initial contracts exist without waiting for a downstream product.
        data = read('P0', 'data')['data']
        note = read('P0', 'release_note')['data']
        call('P0', 'write_object', alias='release_note', work_id=work('P0'), data={**note, 'checked_source_row_count': len(data['tables']['retail']['rows']), 'field_names': [c['name'] for c in data['tables']['retail']['columns']]})
        data_ref = share('P0', 'data', ['P1', 'P2'])
        share('P0', 'release_note', ['P1', 'P2'])
        call('P0', 'submit', work_id=work('P0'), artifacts=['data', 'release_note'])
        share('P2', 'request', ['P1', 'P3'])
        # Readiness is actual source access/adoption. Neither branch requires the
        # other branch's result, so both can start from the same initial contract.
        consume('P1')
        consume('P2')
        report['initial_parallel_branches_ready'] = True
        report['initial_branch_sources'] = {p: copy.deepcopy(SOURCES[p]) for p in ('P1', 'P2')}
        initial_objects = {p: copy.deepcopy(world.state['artifacts'][object_identity(p, 'result')]['current_version']) for p in ('P1', 'P2', 'P3')}
        for edition in (1, 2):
            if edition == 2:
                old_binding = copy.deepcopy(world.state['adoptions'])
                old_work = work('P1')
                old_products = {p: world.state['artifacts'][object_identity(p, 'result')]['current_version'] for p in ('P1', 'P2', 'P3')}
                old_refs = {p: reference(read(p, 'result')) for p in ('P1', 'P2', 'P3')}
                changed = call('P2', 'write_object', alias='request', data=request(2))
                contract_ref = reference(changed)
                # A draft edit alone leaves previous scoped publication live.
                pre_release = {p: world.state['artifacts'][object_identity(p, 'result')]['current_version'] for p in ('P1', 'P2', 'P3')}
                report['controls'].append({'name': 'draft_never_rebuilds_downstream', 'passed': pre_release == old_products})
                call('P2', 'publish', **contract_ref, target_projects=['P1', 'P2', 'P3'])
                after_release = {p: world.state['artifacts'][object_identity(p, 'result')]['current_version'] for p in ('P1', 'P2', 'P3')}
                report['controls'].append({'name': 'publication_never_rebuilds_downstream', 'passed': after_release == old_products,
                                           'previous_adoptions_retained': all(world.state['adoptions'].get(k) == v for k, v in old_binding.items())})
                rejected = call('P1', 'submit', work_id=old_work, artifacts=['code', 'result'], allow_error=True)
                report['controls'].append({'name': 'superseded_work_rejects_old_product_submission', 'passed': not rejected['ok'], 'actual_response': rejected})
                report['feedback_previous_product_references'] = old_refs
            else:
                contract_ref = reference(read('P2', 'request'))
            before_p2 = world.state['artifacts'][object_identity('P2', 'result')]['current_version']
            metrics = build('P1')
            report['controls'].append({'name': f'edition_{edition}_P1_build_does_not_build_P2', 'passed': world.state['artifacts'][object_identity('P2', 'result')]['current_version'] == before_p2})
            share('P1', 'result', ['P3'])
            if edition == 2:
                mixed = build('P3', expected_status='tests_failed')
                mixed_rows = records(mixed['data']['tables']['integration'])
                mismatch = any(r['difference_pence'] != 0 or r['invoice_difference'] != 0
                               or r['metrics_pence'] is None or r['analysis_pence'] is None for r in mixed_rows)
                report['controls'].append({'name': 'mixed_new_metrics_old_analysis_really_disagrees',
                                           'passed': mismatch,
                                           'actual_sql_rows': mixed_rows,
                                           'actual_sources': mixed['data']['sources'],
                                           'actual_reference': reference(mixed),
                                           'editable_test_status': mixed['data']['status'],
                                           'not_submitted_as_correct': True})
            analysis = build('P2')
            share('P2', 'result', ['P3'])
            integration = build('P3')
            # Post-work independent arithmetic and immutable source checks.
            rules = records(request(edition)['tables']['basis_meta'])[0]
            expected = expected_metrics(records(data['tables']['retail']), records(data['tables']['customers']), rules)
            expected = sorted(expected, key=lambda r: r['CustomerID'])
            actual_m = records(metrics['data']['tables']['metrics'])
            actual_a = records(analysis['data']['tables']['customer_analysis'])
            actual_i = records(integration['data']['tables']['integration'])
            expected_a = [{**r, 'segment': 'positive' if r['revenue_pence'] > 0 else 'negative' if r['revenue_pence'] < 0 else 'zero'} for r in expected]
            expected_i = [{'CustomerID': r['CustomerID'], 'metrics_pence': r['revenue_pence'], 'analysis_pence': r['revenue_pence'], 'difference_pence': 0, 'metrics_invoices': r['invoice_count'], 'analysis_invoices': r['invoice_count'], 'invoice_difference': 0} for r in expected]
            exact_sources = (metrics['data']['sources'] == {'data': data_ref, 'basis': contract_ref}
                             and analysis['data']['sources'] == {'data': data_ref, 'basis': contract_ref}
                             and integration['data']['sources'] == {'metrics': reference(metrics), 'analysis': reference(analysis), 'basis': contract_ref})
            report['editions'].append({'edition': edition, 'metrics': actual_m, 'analysis': actual_a, 'integration': actual_i,
                                       'fixed_references': {p: reference(v) for p, v in [('P1', metrics), ('P2', analysis), ('P3', integration)]},
                                       'policy_reference': contract_ref, 'exact_sources_consumed': exact_sources,
                                       'decimal_metrics_pass': actual_m == expected, 'analysis_pass': actual_a == expected_a,
                                       'integration_pass': actual_i == expected_i,
                                       'work_ids': {p: work(p) for p in ('P1', 'P2', 'P3')}})
        for project in ('P1', 'P2', 'P3'):
            call(project, 'submit', work_id=work(project), artifacts=['code', 'result'])
        report['initial_empty_output_versions'] = initial_objects
        report['final_submissions'] = {p: copy.deepcopy(world.state['work_items'][work(p)]['submissions'][-1]) for p in ACTORS}
        report['maintenance'] = copy.deepcopy(world.state.get('maintenance_impacts', []))
        report['passed'] = (report['initial_parallel_branches_ready'] and all(c['passed'] for c in report['controls'])
                            and all(all(e[k] for k in ('exact_sources_consumed', 'decimal_metrics_pass', 'analysis_pass', 'integration_pass')) for e in report['editions'])
                            and report['editions'][0]['metrics'] != report['editions'][1]['metrics'])
        finish_episode(world, episode, experience=recorder.snapshot(), termination={'status': 'completed', 'reason': 'two declared editions executed with exact source consumption'})
    except Exception as exc:
        report['passed'] = False
        report['error'] = {'type': type(exc).__name__, 'message': str(exc)}
        finish_episode(world, episode, experience=recorder.snapshot(), termination={'status': 'environment_error', 'reason': str(exc)})
    finally:
        save_deployment(deployment)
        (output / 'capture.json').write_bytes(json_bytes(captures))
        (output / 'experience.json').write_bytes(json_bytes(recorder.snapshot()))
        (output / 'report.json').write_bytes(json_bytes(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output)
    print({'passed': result['passed'], 'editions': len(result['editions']), 'error': result.get('error')})


if __name__ == '__main__':
    main()
