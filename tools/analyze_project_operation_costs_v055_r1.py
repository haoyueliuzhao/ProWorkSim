"""Count recorded managed actions and paging without reading experience streams."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
OUT = ROOT / 'runs/software-benchmark-v055/score-gap-evidence-r1'
rows = json.loads((OUT / 'normal-closed-slot-metadata.json').read_bytes())
groups = defaultdict(lambda: {'episodes': 0, 'actions': Counter(), 'response_ok_true': Counter(),
    'response_ok_false': Counter(), 'cursor_supplied': Counter(), 'episode_with_action': Counter(),
    'error_messages': Counter(), 'missing_decision_for_recorded_action': 0})
read_bytes = 0
for row in rows:
    if not row['group'].endswith(('PROJECT', 'PROJECT-thinking', 'PROJECT-nonthinking')):
        continue
    path = Path(row['controller']['path']).parent / 'managed-boundary.json'
    raw = path.read_bytes()
    read_bytes += len(raw)
    boundary = json.loads(raw)
    group = groups[row['group']]
    group['episodes'] += 1
    seen = set()
    for outcome in boundary['outcomes']:
        decision = outcome.get('decision', {})
        tool = decision.get('action')
        if not tool:
            group['missing_decision_for_recorded_action'] += outcome.get('action_performed') is True
            continue
        group['actions'][tool] += 1
        seen.add(tool)
        args = decision.get('arguments', {})
        if isinstance(args, dict) and args.get('cursor'):
            group['cursor_supplied'][tool] += 1
        response = outcome.get('response', {})
        if response.get('ok') is True:
            group['response_ok_true'][tool] += 1
        elif response.get('ok') is False:
            group['response_ok_false'][tool] += 1
            error = response.get('error', {})
            if isinstance(error, dict):
                group['error_messages'][str(error.get('message'))] += 1
    group['episode_with_action'].update(seen)
value = {'version': 'v055-project-operation-cost-metadata-r1', 'created_utc': datetime.now(timezone.utc).isoformat(),
    'scope': 'All original normal-closed PROJECT managed boundaries; never raw experience, model messages or repository files',
    'groups': dict(groups), 'read_bytes': read_bytes, 'model_calls': 0, 'test_executions': 0,
    'counting_caveat': 'Only outcomes retaining a decision action are classified by tool; missing decisions stay counted separately. Native shell commands are not equated to one managed operation.'}
for root in [OUT, ROOT / 'artifacts/software-benchmark-v055/score-gap-evidence-r1']:
    with (root / 'project-operation-costs.json').open('x') as stream:
        json.dump(value, stream, indent=2)
print(json.dumps({'groups': dict(groups), 'read_bytes': read_bytes}, indent=2))
