"""Start an independently qualified optimized resident without a second load."""
import argparse
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--kernel-plan", type=Path, required=True)
    parser.add_argument("--kernel-plan-sha256", required=True)
    args, remaining = parser.parse_known_args()
    from proworksim.software_benchmark_candidates_v054 import reference
    from proworksim.software_benchmark_kernel_diagnostic_v054 import qualify_loaded_owner
    from proworksim import software_calibration_runtime_v051 as runtime
    from proworksim.software_benchmark_interleaved_owner_v054 import main as serve
    plan_ref = reference(args.kernel_plan)
    if plan_ref["sha256"] != args.kernel_plan_sha256:
        raise ValueError("Independent kernel plan changed")
    original = runtime.load_actor

    def qualified_loader(*positional, **kwargs):
        owner = original(*positional, **kwargs)
        qualify_loaded_owner(owner, plan_ref)
        return owner

    runtime.load_actor = qualified_loader
    sys.argv = [sys.argv[0], *remaining]
    serve()


if __name__ == "__main__":
    main()
