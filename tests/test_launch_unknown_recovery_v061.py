"""The batch launcher may start only its named, bounded ordinary-user unit."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('v061_owned_launch', ROOT / 'tools/launch_unknown_recovery_v061.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def test_exact_coordinator_unit_and_fixed_cpu_memory_limits(monkeypatch):
    monkeypatch.setattr(launcher, 'checked', lambda _: None)
    argv = launcher.command({'unit': launcher.UNIT, 'user_id': launcher.os.getuid(),
                             'source': {}, 'ownership_token': 'owned-test-token'})
    assert argv[:4] == ['systemd-run', '--user', '--collect', '--no-block']
    assert '--unit=proworksim-v061-recovery.service' in argv
    assert '--property=CPUQuota=400%' in argv and '--property=MemoryMax=16G' in argv
    assert '--property=MemorySwapMax=0' in argv and '--property=Restart=no' in argv
    assert '--property=KillMode=mixed' in argv and '--property=TimeoutStopSec=420' in argv
    assert '--execute' == argv[-1]
    assert not {'sudo', '--system', 'restart', 'enable-linger'}.intersection(argv)


def test_unrelated_unit_is_rejected_before_command(monkeypatch):
    monkeypatch.setattr(launcher, 'checked', lambda _: pytest.fail('Must refuse before using any source'))
    with pytest.raises(ValueError, match='ownership'):
        launcher.command({'unit': 'other-work.service', 'user_id': launcher.os.getuid()})
