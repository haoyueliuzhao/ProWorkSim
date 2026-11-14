"""Add only the new owned aggregate parent to an already isolated actor pair."""
from __future__ import annotations

from . import software_benchmark_api_parent_v131 as parent


class ParentContainers:
    def __init__(self, delegate):
        self.delegate = delegate

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def create(self, *args, **kwargs):
        if args or kwargs.get('cgroup_parent') is not None:
            raise ValueError('The exact new parent is injected only by this scoped provider')
        return self.delegate.create(**parent.container_options(kwargs))


class ParentClient:
    def __init__(self, delegate):
        self.delegate = delegate
        self.containers = ParentContainers(delegate.containers)

    def __getattr__(self, name):
        return getattr(self.delegate, name)


def parent_bound_pair(original):
    class BoundedTeamPair(original):
        def __init__(self, client, *args, **kwargs):
            super().__init__(ParentClient(client), *args, **kwargs)

        def create_container(self, *args, **kwargs):
            value = super().create_container(*args, **kwargs)
            value.reload()
            parent.validate_container_parent(value.attrs)
            return value

        def start(self, role):
            self.objects[role].reload()
            parent.validate_container_parent(self.objects[role].attrs)
            attrs = super().start(role)
            parent.validate_container_parent(attrs, require_running=True)
            return attrs

    return BoundedTeamPair
