"""Install the sealed host-only pool reader before the original episode runner."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from proworksim.software_benchmark_candidates_v054 import reference


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-revision", type=Path, required=True)
    parser.add_argument("--host-sha256", required=True)
    parser.add_argument("--overlay", type=Path, required=True)
    parser.add_argument("--overlay-sha256", required=True)
    parser.add_argument("episode_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if not args.episode_args or args.episode_args[0] != "--":
        raise ValueError("Original episode arguments require an explicit separator")
    from run_qwen_ref_handoff_v054_r5 import pool_overlay, validate_revision
    host_ref, overlay_ref = reference(args.host_revision), reference(args.overlay)
    if host_ref["sha256"] != args.host_sha256 or overlay_ref["sha256"] != args.overlay_sha256:
        raise ValueError("Episode handoff revision/overlay SHA differs")
    revision = validate_revision(host_ref, initial=True)
    if revision["pool_overlay"] != overlay_ref:
        raise ValueError("Episode overlay is not sealed by the queue host revision")
    pool_overlay.install(overlay_ref)
    # This import follows installation: any original factory/session imports
    # use the same canonical module. Model/tool/claim logic stays unchanged.
    from proworksim.software_benchmark_runner_v054 import main as original_main
    old_argv = sys.argv
    try:
        sys.argv = [str(Path(__file__).resolve()), *args.episode_args[1:]]
        return original_main()
    finally:
        sys.argv = old_argv


if __name__ == "__main__":
    raise SystemExit(main())
