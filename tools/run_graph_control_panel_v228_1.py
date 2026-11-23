"""Run the remaining frozen task order with outcome-bearing observer evidence."""
import argparse
from run_graph_control_panel_v228 import ROOT,DB,OUT,read,save,run,invoke as original
from proworksim.software_fixed_organization_clone_v131 import clone_function
from run_graph_control_panel_v228 import main as first_revision
PLAN=ROOT/'artifacts/software-benchmark-v228/control-r2'


def invoke(script,args,destination,receipt):
    if script=='run_graph_control_episode_v228.py':
        script='run_graph_control_episode_v228_1.py'
    return original(script,args,destination,receipt)


run=clone_function(run,{**run.__globals__,'invoke':invoke})
main=clone_function(first_revision,{**first_revision.__globals__,'PLAN':PLAN,'run':run})
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('indices',nargs='+',type=int)
    main(parser.parse_args().indices)
