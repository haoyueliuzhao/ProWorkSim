"""Current bounded httpbin probe after failed historical-IP control; no retry."""
import importlib.util
import json
from pathlib import Path

from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_expansion_episode_v069 import clone_namespace
from proworksim import software_benchmark_preparation_grading_v203_2_3 as guard
from proworksim import software_benchmark_scope_v203_2_3 as scope

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'tools/check_httpbin_direct_v131.py'
OUT=scope.ARTIFACT_ROOT/'httpbin-current-probe-r1'


def main():
    spec=importlib.util.spec_from_file_location('_v20323_bounded_httpbin_parent',PARENT)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    def identity():
        guard.require_allowed('v066.resolve',instance_id='psf__requests-1766')
        return {'plan':reference(scope.PLAN_FILE),'authority':reference(guard.AUTH_FILE),
                'public_hostname':'httpbin.org','ports':[80,443],
                'parent_exact_probe_source':reference(PARENT),
                'new_wrapper_source':reference(__file__),
                'current_runtime_resolution_not_overwritten':True,
                'credentials_read':False,'maximum_connections':4,'maximum_application_bytes':65536}
    namespace=clone_namespace(module,ROOT=ROOT,__file__=__file__,
        OUTPUT=OUT/'diagnostic.json',INTENT=OUT/'intent.json',
        RESOLUTION=OUT/'proposed-network-resolution.json',readonly_panel_identity=identity)
    value=namespace['run'](prepare_readonly=True)
    print(json.dumps(value),flush=True)


if __name__=='__main__':main()
