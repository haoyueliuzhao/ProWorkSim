"""Export the one original terminal snapshot whose model had already finished."""
import json

from proworksim.software_benchmark_snapshot_recovery_v061 import recover

if __name__ == "__main__":
    print(json.dumps(recover(), ensure_ascii=False))
