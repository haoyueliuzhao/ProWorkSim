"""Public pytest-2 string-form raises semantics on the frozen pytest 7 runner.

Loaded only by the separately admitted Requests public dependency profile.
The expressions are ordinary task test code: they run inside the same isolated
test process, with its existing cwd, interpreter, quotas and network boundary.
No assertion, exception or test outcome is suppressed or rewritten.
"""
from __future__ import annotations

import functools
import sys
import textwrap

VERSION = 'v130-public-pytest-legacy-string-raises-r1'
PYTEST_VERSION = '7.4.4'


def install_pytest_compat():
    import pytest
    if pytest.__version__ != PYTEST_VERSION:
        raise RuntimeError('The public compatibility profile requires frozen pytest 7.4.4')
    original = pytest.raises
    if getattr(original, '_pws_public_compat_version', None) == VERSION:
        return {'version': VERSION, 'already_installed': True}

    @functools.wraps(original)
    def raises(expected_exception, *args, **kwargs):
        if not args or not isinstance(args[0], str):
            return original(expected_exception, *args, **kwargs)
        if len(args) != 1:
            raise TypeError('The legacy string form accepts one source string')
        # Historical string form compiled source and evaluated it in a copy of
        # the caller's locals, extended with its keyword arguments. Keep actual
        # exception matching and DID-NOT-RAISE behavior in the real pytest code.
        frame = sys._getframe(1)
        local = dict(frame.f_locals)
        local.update(kwargs)
        source = textwrap.dedent(args[0]).strip() + '\n'
        code = compile(source, frame.f_code.co_filename, 'exec')
        try:
            with original(expected_exception) as caught:
                exec(code, frame.f_globals, local)
            return caught
        finally:
            del frame

    raises._pws_public_compat_version = VERSION
    pytest.raises = raises
    return {'version': VERSION, 'already_installed': False}


def pytest_configure(config):
    del config
    install_pytest_compat()
