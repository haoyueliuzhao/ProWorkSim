"""Keep Python startup diagnostics separate from the JSON isolation witness."""
import inspect
import json
import textwrap
from pathlib import Path
from .software_benchmark_candidates_v054 import write_new


def read_witness(container,argv,preparation):
    result=container.exec_run(argv,demux=True)
    stdout,stderr=result.output
    stdout,stderr=stdout or b'',stderr or b''
    if len(stdout)>65536 or len(stderr)>65536:raise ValueError('Startup witness output exceeds its bounded diagnostic size')
    record={'argv':argv,'exit_code':result.exit_code,'stdout':stdout.decode('utf-8'),
        'stderr':stderr.decode('utf-8',errors='replace'),'streams_separated':True,
        'official_tests_modified':False,'site_initialization_disabled':False}
    write_new(Path(preparation['path']).parent/'namespace-witness-output-v183.json',record)
    if result.exit_code!=0:raise RuntimeError('Private namespace witness interpreter failed')
    return json.loads(record['stdout'])


def bind_scorer(scorer):
    ns=scorer.validate_request.__globals__
    source=textwrap.dedent(inspect.getsource(ns['ObservedContainer'].start))
    old='''inside = json.loads(
        archive.checked_exec(
            self.delegate,
            [self.preparation["mapping"]["public_python"], "-c", source],
            timeout_note="Private grader boundary",
        )
    )'''
    if source.count(old)!=1:raise ValueError('The actual startup witness changed')
    source=source.replace(old,'''inside = read_witness(self.delegate,
        [self.preparation["mapping"]["public_python"], "-c", source], self.preparation)''')
    local={};exec(compile(source,__file__+':separated-witness','exec'),{**ns,'read_witness':read_witness},local)
    revised=type('SeparatedWitnessContainer',(ns['ObservedContainer'],),{'start':local['start']})
    ns['ObservedContainer']=revised;scorer.ObservedContainer=revised
    return scorer
