"""CPU-only session sentinel; it never loads or unloads model weights."""
from proworksim.software_benchmark_resident_session_v054 import sentinel_main

if __name__ == "__main__":
    raise SystemExit(sentinel_main())
