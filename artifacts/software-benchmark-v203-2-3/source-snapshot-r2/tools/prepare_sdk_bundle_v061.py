"""Package the existing pinned SDK/Python for private owned Docker containers."""
import json

from proworksim.software_benchmark_sdk_bundle_v061 import prepare_bundle

if __name__ == "__main__":
    result = prepare_bundle()
    print(json.dumps({key: result[key] for key in ("version", "archive", "files", "uncompressed_file_bytes", "probe")}))
