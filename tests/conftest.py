import itertools

import pytest

from proworksim.compiler import compile_world
from proworksim.designer import design
from proworksim.kernel import World


@pytest.fixture
def world_factory(tmp_path):
    sequence = itertools.count()

    def create(delivery="continuous", information="mail", seed=17):
        path = tmp_path / f"world-{next(sequence)}"
        compile_world(design(seed, delivery, information), path)
        return World(path)

    return create
