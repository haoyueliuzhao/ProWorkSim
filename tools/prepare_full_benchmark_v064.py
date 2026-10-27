"""Freeze the full 500 x 12 matrix using only the existing public projection."""
import json

from proworksim.software_benchmark_full_plan_v064 import prepare


if __name__ == "__main__":
    print(json.dumps(prepare(), ensure_ascii=False))
