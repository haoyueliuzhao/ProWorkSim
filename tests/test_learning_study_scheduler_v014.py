"""Process scheduling only; fixture children never import models or use GPUs."""

import json
from pathlib import Path
import subprocess
import sys


def test_fixed_jobs_keep_an_incomplete_run_without_replacing_or_dropping_it(tmp_path):
    project, source, output = tmp_path / 'project', tmp_path / 'source', tmp_path / 'supervisor'
    project.mkdir()
    (source / 'scripts').mkdir(parents=True)
    for env in ['.venv', '.train-venv']:
        (project / env / 'bin').mkdir(parents=True)
        (project / env / 'bin/python').symlink_to(sys.executable)
    actor = source / 'scripts/online_learning_v013.py'
    actor.write_text("""import argparse,json,os
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output');p.add_argument('--protocol');a,_=p.parse_known_args()
o=Path(a.output);(o/'online').mkdir(parents=True)
v=json.loads(Path(a.protocol).read_text())
(o/'online/report.json').write_text(json.dumps({'status':v['status'],'actor_steps_total':0,'critic_steps_total':0,'fixture_no_GPU':True,'visible_label':os.getenv('CUDA_VISIBLE_DEVICES')}))
""")
    launcher = tmp_path / 'fixture_launcher.py'
    launcher.write_text('import subprocess,sys\nsys.exit(subprocess.run(sys.argv[2:]).returncode)\n')
    jobs = []
    for i, status in enumerate(['complete', 'stopped_probability_mismatch', 'complete']):
        (source / f'p{i}.json').write_text(json.dumps({'status': status}))
        jobs.append({'name': f'j{i}', 'protocol': f'p{i}.json', 'run': f'runs/j{i}', 'launch': f'launch/j{i}'})
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'gpus': [7], 'jobs': jobs, 'resource_launcher': str(launcher),
                                    'model': 'fixture-no-model', 'weight_manifest': 'unused'}))
    script = Path(__file__).resolve().parents[1] / 'scripts/run_learning_study_v014.py'
    result = subprocess.run([sys.executable, str(script), '--manifest', str(manifest), '--source', str(source),
                             '--project', str(project), '--output', str(output)], capture_output=True, text=True)
    assert result.returncode == 1
    record = json.loads((output / 'scheduler.json').read_text())
    assert record['status'] == 'finished_with_incomplete_jobs'
    assert len(record['jobs']) == 3
    assert [j['online_status'] for j in record['jobs']] == ['complete', 'stopped_probability_mismatch', 'complete']
    assert all(j['status'] == 'finished' for j in record['jobs'])
    assert record['jobs'][2]['started_at'] >= record['jobs'][1]['ended_at']
    assert all(json.loads((project / f'runs/j{i}/online/report.json').read_text())['fixture_no_GPU'] for i in range(3))
