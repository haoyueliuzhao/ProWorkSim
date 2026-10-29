"""Original Qwen episodes under the tolerant startup-status reader."""
from __future__ import annotations

from . import software_benchmark_resources_v084 as resources
from .software_benchmark_episodes_v075 import episode


class EpisodeBindings:
    def __init__(self, guard, *, watchdog_guard, capacity_probe=None, authorization_ref=None):
        self.primary_policy = resources.policy(guard, watchdog_guard=watchdog_guard,
            capacity_probe=capacity_probe, authorization_ref=authorization_ref)
        self.qwen = episode(self.primary_policy)
        self.qwen.run_episode.__globals__['capacity'] = self.primary_policy.physical_capacity

    def run_qwen(self, row, resident, **kwargs):
        if row.get('model_key') != 'QWEN':
            raise ValueError('This recovery cannot generate API tasks')
        return self.qwen.run_episode(row, resident, **kwargs)
