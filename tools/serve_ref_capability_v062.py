"""Run one explicitly authorized, ordinary-user v062 REF resident."""
import argparse
from pathlib import Path

from proworksim.software_benchmark_ref_resident_v062 import run_service


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, required=True)
    raise SystemExit(run_service(parser.parse_args().spec))
