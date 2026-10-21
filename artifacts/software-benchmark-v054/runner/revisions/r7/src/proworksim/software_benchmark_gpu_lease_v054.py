"""Nonblocking host leases only; no CUDA import, allocation, placeholder or polling."""
from __future__ import annotations

import fcntl
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


class GpuLease:
    def __init__(self, gpu_uuid):
        if not re.fullmatch(r"GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", gpu_uuid):
            raise ValueError("Lease exactly one admitted physical GPU UUID")
        self.handles = []
        root = ROOT / "runs/v054-gpu/locks"
        root.mkdir(parents=True, exist_ok=True)
        try:
            device = (root / (gpu_uuid + ".lock")).open("a+b")
            self.handles.append(device)
            fcntl.flock(device, fcntl.LOCK_EX | fcntl.LOCK_NB)
            for index in range(4):
                gate = (root / ("resident-slot-" + str(index) + ".lock")).open("a+b")
                try:
                    fcntl.flock(gate, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    gate.close()
                    continue
                self.handles.append(gate)
                self.receipt = {"gpu_uuid": gpu_uuid, "physical_device_lock": str(device.name),
                                "global_resident_gate": str(gate.name), "maximum_residents": 4,
                                "GPU_memory_allocated_by_lease": 0}
                break
            else:
                raise BlockingIOError("All four resident leases are already held")
        except BaseException:
            self.close()
            raise

    def close(self):
        for handle in reversed(self.handles):
            handle.close()
        self.handles.clear()
