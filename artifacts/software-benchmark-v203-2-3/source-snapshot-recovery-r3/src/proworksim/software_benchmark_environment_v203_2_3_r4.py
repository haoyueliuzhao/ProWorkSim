"""Pinned current endpoint/CA plus raw-replayable completed HTTP idle proofs."""
from pathlib import Path
from . import software_benchmark_environment_v203_2_3_r2 as fixed
from . import software_benchmark_tcp_transport_v203_2_3_r4 as observed
from . import software_benchmark_http_framing_v203_2_3_r4 as framing
from .software_benchmark_candidates_v054 import reference

VERSION='v203.2.3-framing-proved-idle-environment-r4'
TASK=fixed.TASK
RESOLUTION=fixed.RESOLUTION


def private_environment(policy,runtime_scope,parent):
    environment=fixed.private_environment(policy,runtime_scope,parent)
    tls=environment.tls
    observed.bind_transport(tls.transport)
    parent_container=tls.EnvironmentContainer
    class CapturedHTTPContainer(parent_container):
        def start(self,*args,**kwargs):
            source=Path(self.preparation['path']).resolve()
            if (not source.is_relative_to(policy.GRADING_ROOT.resolve())
                    or source.parent.name!='official-output'
                    or self.preparation['mapping']['instance_id']!=TASK):
                raise ValueError('HTTP capture must belong to this exact owned Requests scorer')
            context=tls.transport.http_capture_context
            if context['path'] is not None:raise ValueError('A private scorer capture can be bound only once')
            context['path']=source.with_name('http-framing-stream.jsonl')
            return super().start(*args,**kwargs)
    tls.EnvironmentContainer=CapturedHTTPContainer
    previous_manifest=tls.environment_manifest
    def manifest():
        return {**previous_manifest(),'http_idle_observer':reference(observed.__file__),
            'http_framing_tracker':reference(framing.__file__),
            'http_framing_parser':observed.portable_parser(),
            'http_idle_policy':VERSION,
            'http_idle_requires_complete_framing_and_both_queues_empty':True,
            'TLS_idle_timeout_exempted':False,'forwarded_bytes_or_timeouts_changed':False,
            'raw_http_capture_maximum_bytes':observed.MAX_JOURNAL_BYTES,
            'application_test_success_inferred_from_HTTP':False}
    tls.environment_manifest=manifest
    tls.validate_environment.__globals__['environment_manifest']=manifest
    return environment


def validate_transport_evidence(receipt,quiet,observed_container,identity,folder,*,transport_directory=None,require_usage=True):
    result=fixed.validate_transport_evidence(receipt,quiet,observed_container,identity,folder,
        transport_directory=transport_directory,require_usage=require_usage)
    directory=Path(folder)/'official-output' if transport_directory is None else Path(transport_directory)
    if result.get('version')!=observed.VERSION:raise ValueError('Wrong HTTP observation revision')
    audit=result.get('http_frame_audit',{})
    replay=observed.validate_capture(audit,expected_path=directory/'http-framing-stream.jsonl')
    exemptions=audit['idle_exemptions']
    ids={row['connection_id'] for row in exemptions}
    closed={row['connection_id'] for row in result['connections'] if row.get('outcome')=='completed_http_keepalive_idle_close'}
    if len(ids)!=len(exemptions) or ids!=closed:raise ValueError('HTTP exception is not bound to an actual idle-close record')
    for row in result['connections']:
        if row['connection_id'] not in ids:continue
        state=row['http_observation']
        if not observed.idle_allowed(state['framing'],port=row['port'],
                upstream_pending=state['upstream_pending'],docker_pending=state['docker_pending']):
            raise ValueError('HTTP idle close lacks its empty-queue and complete-frame proof')
    return {**result,'http_raw_replay_validation':replay}
