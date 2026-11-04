"""One bounded CPU measurement of the retained 9070 pre-model OOM world.

No benchmark, container, model, network, signal or resource configuration is
used. A temporary selective extraction is deleted after the measurement.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import resource
import shutil
import socket
import subprocess
import tarfile
import tempfile
import time
from types import SimpleNamespace

from proworksim.software_benchmark_archive_storage_v064 import (
    CODEC_BINARY, open_verified_archive,
)
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_initial_state_hash_v132 import measure_initial_business_state
from proworksim.storage import Store


ROOT = Path(__file__).resolve().parents[1]
EPISODE = ROOT / "runs/software-benchmark-v131/fixed-organization-50-r1/episodes/9070"
OUT = ROOT / "artifacts/software-benchmark-v132/streamed-initial-hash-controls-r1/large-original.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measure", action="store_true", required=True)
    parser.parse_args()
    if OUT.exists():
        raise ValueError("This original large-data CPU measurement is not automatically repeated")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # Limits affect this new ordinary CPU process and its own decoder only.
    resource.setrlimit(resource.RLIMIT_AS, (8 * 1024**3, 8 * 1024**3))
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
    os.nice(10)
    def deny(*a, **kw):
        raise RuntimeError("This CPU measurement has no network or external-runtime authority")
    for name in ("connect", "bind", "sendto"):
        setattr(socket.socket, name, deny)
    socket.getaddrinfo = deny
    original_popen = subprocess.Popen
    def decoder_only(argv, **kwargs):
        if argv != [str(CODEC_BINARY), "-d", "--long=27", "-q", "-c"]:
            return deny(argv)
        return original_popen(argv, **kwargs)
    subprocess.Popen = decoder_only
    started = time.monotonic()
    transfer_file = EPISODE / "controller-output-transfer.json"
    transfer = json.loads(transfer_file.read_bytes())
    storage = transfer["archive_storage"]
    if storage.get("round_trip_verified") is not True:
        raise ValueError("Use only the previously verified retained controller archive")
    selected_bytes, selected_files = 0, 0
    with tempfile.TemporaryDirectory(prefix="proworksim-v132-state-hash-") as directory:
        root = Path(directory)
        with open_verified_archive(storage) as stream:
            with tarfile.open(fileobj=stream, mode="r|") as archive:
                for item in archive:
                    name = PurePosixPath(item.name.removeprefix("./"))
                    prefix = PurePosixPath("output/managed-world/world")
                    if not name.is_relative_to(prefix):
                        continue
                    relative = name.relative_to(prefix)
                    if relative != PurePosixPath("control/state.json") and not relative.is_relative_to("control/versions"):
                        continue
                    if item.isdir():
                        continue
                    if not item.isfile() or name.is_absolute() or ".." in relative.parts:
                        raise ValueError("Unexpected retained world file shape")
                    selected_bytes += item.size
                    selected_files += 1
                    if selected_bytes > 6 * 1024**3:
                        raise ValueError("This selective CPU fixture exceeds its local extraction bound")
                    destination = root / str(relative)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with destination.open("xb") as target:
                        shutil.copyfileobj(archive.extractfile(item), target, length=1024**2)
        state_file = root / "control/state.json"
        with state_file.open() as source:
            state = json.load(source)
        result = measure_initial_business_state(SimpleNamespace(state=state, store=Store(root)))
        del state
    result.update(version="v132-large-original-streamed-state-CPU-r1", passed=True,
        original_slot=9070, original_archive=storage["blob"], original_transfer=reference(transfer_file),
        raw_archive_bytes_verified=storage["decompressed_bytes"], selected_bytes=selected_bytes,
        selected_files=selected_files, peak_RSS_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        peak_decoder_RSS_bytes=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss * 1024,
        address_space_limit_bytes=8 * 1024**3, cpu_affinity=sorted(os.sched_getaffinity(0)),
        seconds=time.monotonic() - started, temporary_extracted_files_removed=True,
        old_full_hex_path_executed_on_this_large_original=False,
        exact_legacy_hash_equality_proven_by_separate_small_and_MATRIX_controls=True,
        model_calls=0, Docker_operations=0, benchmark_tests=0, network_operations=0,
        shared_server_configuration_changed=False)
    # Retain the measured scalars in stdout too if final filesystem IO fails.
    print(json.dumps(result), flush=True)
    write_new(OUT, result)
    print(json.dumps({"result": reference(OUT), "peak_RSS_bytes": result["peak_RSS_bytes"],
                      "hashed_bytes": result["hashed_bytes"], "seconds": result["seconds"]}))


if __name__ == "__main__":
    main()
