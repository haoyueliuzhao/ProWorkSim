"""Initialize the newly authorized ledger and launch the sealed owned pilot."""
import argparse
import json
from pathlib import Path
from proworksim import software_benchmark_scope_v203_2_1 as scope
from proworksim import software_benchmark_host_api_v203_2_1 as host
from proworksim.software_benchmark_candidates_v054 import reference


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true',required=True)
    parser.parse_args()
    scope.require_allowed('v203.2.1.run')
    if (scope.API_ROOT/'execution-started.json').exists():
        raise ValueError('Never automatically restart a consumed coordinator')
    admission=scope.dispatch_view().physical_capacity()
    if admission.get('passed') is not True:
        raise ValueError('Declared host resource headroom is not available')
    balances=host.initialize_ledger()
    if any(v.get('known_actual_tokens') or v.get('reserved_or_unknown_nanoyuan') for v in balances.values()):
        raise ValueError('Fresh pilot ledger is not unused')
    scope.retain(scope.API_ROOT/'cash-initialization.json',{
        'new_budget_CNY':'150.00','states':balances,'old_ledgers_touched':False,
        'plan':reference(scope.PLAN_FILE),'admission':admission})
    from launch_passive_pilot_v203_2_1 import launch
    print(json.dumps(launch(),ensure_ascii=False))


if __name__=='__main__':main()
