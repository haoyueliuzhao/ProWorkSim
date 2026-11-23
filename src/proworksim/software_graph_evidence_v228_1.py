"""Bind each OSA evidence label to what the observer's original tool receipt established."""
from copy import deepcopy
from .software_anomaly_graph_v226 import TESTS,tested_nodes
from .software_project_relations_v217 import identity


def explain(node, observations, observer):
    records={item['outcome']['response']['command_id']:item['outcome']['response']
             for item in observations if item['outcome'].get('worker_id')==observer
             and (item['outcome'].get('response') or {}).get('command_id')}
    result=deepcopy(node)
    for ref in result['evidence_refs']:
        response=records.get(ref['command_id'])
        if not response or identity(response)!=ref['sha256']:raise ValueError('Missing authorized original receipt')
        payload=response.get('result') or {}
        if ref['tool'] in TESTS:
            failed,passed=tested_nodes(payload)
            subject=node.get('subject')
            ref['executed']=payload.get('executed') is True
            if subject in failed or subject in passed:
                ref.update(nodeid=subject,passed=subject in passed,outcome='case_passed' if subject in passed else 'case_failed')
            elif ref['executed'] and type(payload.get('passed')) is bool:
                ref.update(outcome='test_run_passed' if payload['passed'] else 'test_run_failed_case_unspecified')
            else:ref['outcome']='test_result_unknown'
        elif response.get('ok') is False:
            rejection=(response.get('error') or {}).get('rejection') or {}
            ref['outcome']=rejection.get('code') or 'operation_rejected'
        elif payload.get('conflicts') or (payload.get('conflict_count') or 0)>0:ref['outcome']='merge_conflict'
        elif response.get('ok') is True:ref['outcome']='operation_completed'
    return result
