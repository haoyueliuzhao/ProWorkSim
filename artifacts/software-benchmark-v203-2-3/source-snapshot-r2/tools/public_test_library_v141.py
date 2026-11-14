"""Shared public-test selections, compiled to argv without a shell or oracle.

Only frozen public frontends are selected. The managed actor remains the
authority for source-version synchronization, execution quotas and isolation.
"""
from __future__ import annotations

import copy
import hashlib
import json
import importlib.util
import math
import os
import re
import stat
import time
from pathlib import Path, PurePosixPath

VERSION = 'v110-public-test-selection-r1'
MAX_TARGETS = 16
MAX_EXPRESSION = 256
CONTRACT_VERSION = 'v110-shared-public-test-contract-r1'
CONTRACT_PATH = Path('/pws/control/public-test-contract.json')
MAX_OUTPUT_BYTES = 32 * 1024**2
SELECTION_SCHEMA = {
    'type': 'object', 'additionalProperties': False, 'required': ['kind'],
    'properties': {
        'kind': {'type': 'string', 'enum': ['full', 'pytest', 'django', 'sympy']},
        'targets': {'type': 'array', 'maxItems': MAX_TARGETS,
                    'items': {'type': 'string', 'minLength': 1, 'maxLength': 512}},
        'keyword': {'type': 'string', 'maxLength': MAX_EXPRESSION},
        'markers': {'type': 'string', 'maxLength': MAX_EXPRESSION},
        'keywords': {'type': 'array', 'maxItems': 8,
                     'items': {'type': 'string', 'minLength': 1, 'maxLength': 100}},
    },
}
SELECTION_GUIDANCE = (
    'run_tests() preserves the frozen public full-suite entrypoint. For focused tests, '
    'pass selection with kind pytest/django/sympy matching the disclosed frontend. '
    'pytest accepts current repository paths or node IDs in targets, plus optional '
    'keyword (-k) and markers (-m) boolean filters. Django accepts public dotted '
    'test labels in targets. Sympy accepts public test paths and optional keywords '
    'as its own -k list. Use only tests found in public code; hidden acceptance '
    'tests are unavailable. All selections share the original test/time allowance '
    'and record this exact source version; no selection executes a shell.'
)


class PublicTestSelectionError(ValueError):
    pass


def frontend(entry):
    argv = entry.get('argv', [])
    if not isinstance(argv, list) or not argv or any(not isinstance(x, str) for x in argv):
        raise PublicTestSelectionError('The frozen public argv is missing')
    if argv[1:] == ['-m', 'pytest']:
        return 'pytest'
    if argv[1:] == ['bin/test']:
        return 'sympy'
    if argv[1:] == ['tests/runtests.py', '--noinput', '--parallel', '1']:
        return 'django'
    return 'full_only'


def capabilities(entry):
    kind = frontend(entry)
    return {'version': VERSION, 'frontend': kind,
            'selection_kinds': ['full'] + ([] if kind == 'full_only' else [kind]),
            'maximum_targets': MAX_TARGETS,
            'arbitrary_commands': False, 'hidden_material_used': False,
            'same_interpreter_cwd_timeout': True}


def normalize_selection(selection=None):
    if selection is None:
        return {'kind': 'full'}
    if not isinstance(selection, dict) or not isinstance(selection.get('kind'), str):
        raise PublicTestSelectionError('Use a public selection object with an explicit kind')
    kind = selection['kind']
    allowed = {'full': {'kind'}, 'pytest': {'kind', 'targets', 'keyword', 'markers'},
               'django': {'kind', 'targets'}, 'sympy': {'kind', 'targets', 'keywords'}}
    if kind not in allowed or set(selection) - allowed[kind]:
        raise PublicTestSelectionError('Selection fields are not supported by this public frontend')
    result = {'kind': kind}
    if kind == 'full':
        return result
    targets = selection.get('targets', [])
    if (not isinstance(targets, list) or len(targets) > MAX_TARGETS
            or any(not isinstance(x, str) or not 0 < len(x) <= 512 for x in targets)
            or len(set(targets)) != len(targets)):
        raise PublicTestSelectionError('Use at most 16 distinct nonempty public targets')
    result['targets'] = list(targets)
    for key in ('keyword', 'markers') if kind == 'pytest' else ():
        value = selection.get(key, '')
        if not isinstance(value, str):
            raise PublicTestSelectionError('Pytest filters must be strings')
        if value:
            _boolean_filter(value, markers=key == 'markers')
            result[key] = value
    if kind == 'sympy':
        words = selection.get('keywords', [])
        if (not isinstance(words, list) or len(words) > 8
                or any(not isinstance(x, str) or not re.fullmatch(r'[A-Za-z0-9_]{1,100}', x) for x in words)):
            raise PublicTestSelectionError('Sympy keywords are simple name substrings, not pytest expressions')
        if words:
            result['keywords'] = list(words)
    return result


def _boolean_filter(value, *, markers):
    if len(value) > MAX_EXPRESSION or any(c in value for c in '\r\n\x00'):
        raise PublicTestSelectionError('Public test filters are bounded single-line expressions')
    word = r'[A-Za-z_][A-Za-z0-9_]*' if markers else r'[A-Za-z0-9_][A-Za-z0-9_.:\[\]-]*'
    tokens = re.findall(word + r'|\(|\)|\S', value)
    position = 0

    def atom():
        nonlocal position
        if position >= len(tokens):
            raise PublicTestSelectionError('Incomplete public boolean filter')
        token = tokens[position]
        position += 1
        if token == 'not':
            atom()
        elif token == '(':
            expression()
            if position >= len(tokens) or tokens[position] != ')':
                raise PublicTestSelectionError('Unbalanced public boolean filter')
            position += 1
        elif token in {'and', 'or', ')'} or re.fullmatch(word, token) is None:
            raise PublicTestSelectionError('Only test terms, and/or/not, and parentheses are allowed')

    def expression():
        nonlocal position
        atom()
        while position < len(tokens) and tokens[position] in {'and', 'or'}:
            position += 1
            atom()

    expression()
    if position != len(tokens):
        raise PublicTestSelectionError('Unexpected public filter syntax')


def _path_text(value):
    if (not value or value.startswith(('-', '/', '\\')) or '\\' in value
            or any(c in value for c in '\r\n\x00') or '://' in value):
        raise PublicTestSelectionError('Public targets must be repository-relative paths')
    path = PurePosixPath(value)
    if any(part in {'', '.', '..', '.git'} for part in value.split('/')):
        raise PublicTestSelectionError('Parent, control and noncanonical paths are not public test targets')
    return path.as_posix()


def _check_path(path, *, files=None, entry_metadata=None, root=None):
    path = _path_text(path)
    if files is not None:
        if not isinstance(files, dict) or not isinstance(entry_metadata, dict):
            raise PublicTestSelectionError('A complete current source manifest is required')
        for i in range(1, len(PurePosixPath(path).parts) + 1):
            ancestor = '/'.join(PurePosixPath(path).parts[:i])
            if entry_metadata.get(ancestor, {}).get('kind') == 'symlink':
                raise PublicTestSelectionError('Test selections do not traverse source symlinks')
        if path not in files and not any(name.startswith(path + '/') for name in files):
            raise PublicTestSelectionError('The selected path is not in the current public source tree')
        if path in files and entry_metadata.get(path, {}).get('kind') != 'file':
            raise PublicTestSelectionError('The selected target is not a regular public source file')
    elif root is not None:
        root = Path(root).resolve(strict=True)
        target = root.joinpath(*PurePosixPath(path).parts)
        current = root
        for part in PurePosixPath(path).parts:
            current /= part
            if current.is_symlink():
                raise PublicTestSelectionError('Test selections do not traverse source symlinks')
        if not target.exists() or not target.resolve().is_relative_to(root):
            raise PublicTestSelectionError('The selected public path is missing or escapes the repository')
        if not target.is_file() and not target.is_dir():
            raise PublicTestSelectionError('The selected target is not a regular public file or directory')
    else:
        raise PublicTestSelectionError('A current public source tree is required for target validation')
    return path


def selected_entry(entry, selection=None, *, files=None, entry_metadata=None, root=None):
    """Compile only public selection arguments; retain the frozen execution envelope."""
    if (entry.get('cwd') != '/testbed' or entry.get('hidden_material_used') is not False
            or type(entry.get('timeout_seconds')) is not int or not 1 <= entry['timeout_seconds'] <= 1800):
        raise PublicTestSelectionError('The public entrypoint lost its original execution envelope')
    selection = normalize_selection(selection)
    kind = selection['kind']
    actual = frontend(entry)
    if kind != 'full' and kind != actual:
        raise PublicTestSelectionError('This selection does not match the frozen public frontend: ' + actual)
    args = list(entry['argv'])
    targets = selection.get('targets', [])
    for target in targets:
        if kind == 'django':
            if re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*', target, flags=re.ASCII) is None:
                raise PublicTestSelectionError('Django targets are public dotted test labels')
            first = target.split('.')[0]
            path = 'tests/' + first
            try:
                _check_path(path, files=files, entry_metadata=entry_metadata, root=root)
            except PublicTestSelectionError:
                _check_path(path + '.py', files=files, entry_metadata=entry_metadata, root=root)
        else:
            base, *nodes = target.split('::')
            _check_path(base, files=files, entry_metadata=entry_metadata, root=root)
            if kind != 'pytest' and nodes:
                raise PublicTestSelectionError('Only pytest supports :: node identifiers')
            if nodes and (not base.endswith('.py') or any(not x or any(c in x for c in '\r\n\x00') for x in nodes)):
                raise PublicTestSelectionError('Use bounded pytest node identifiers in a public Python file')
    if kind == 'pytest':
        for key, flag in (('keyword', '-k'), ('markers', '-m')):
            if selection.get(key):
                args.extend((flag, selection[key]))
        if targets:
            args.extend(['--', *targets])
    elif kind == 'django':
        args.extend(targets)
    elif kind == 'sympy':
        args.extend(targets)
        if selection.get('keywords'):
            args.extend(['-k', *selection['keywords']])
    result = copy.deepcopy(entry)
    result['argv'] = args
    return result, selection


def contract_for_actor(config):
    """Derive only public fields from an admitted, future owned actor config."""
    public = config['public_environment']
    value = {'version': CONTRACT_VERSION, 'instance_id': config['instance_id'],
             'actor_image_id': config['actor_image_id'],
             'baseline_head': config['baseline_head'], 'baseline_tree': config['baseline_tree'],
             'entry': copy.deepcopy(config['public_test_entry']),
             'environment': copy.deepcopy(public['environment']),
             'public_python': public['public_python'],
             'actor_lifecycle_deadline': config['lifecycle_deadline']}
    return validate_contract(value)


def validate_contract(value):
    fields = {'version', 'instance_id', 'actor_image_id', 'baseline_head', 'baseline_tree',
              'entry', 'environment', 'public_python', 'actor_lifecycle_deadline'}
    if (not isinstance(value, dict) or set(value) != fields or value['version'] != CONTRACT_VERSION
            or not isinstance(value['instance_id'], str) or not value['instance_id']
            or re.fullmatch(r'sha256:[0-9a-f]{64}', value['actor_image_id']) is None
            or any(re.fullmatch(r'[0-9a-f]{40}', value[k]) is None for k in ('baseline_head', 'baseline_tree'))
            or not isinstance(value['public_python'], str) or not value['public_python'].startswith('/')
            or type(value['actor_lifecycle_deadline']) not in (float, int)
            or not math.isfinite(value['actor_lifecycle_deadline'])):
        raise PublicTestSelectionError('The shared public test contract lost its owned task identity')
    entry = value['entry']
    if (not isinstance(entry, dict) or set(entry) != {'version', 'instance_id', 'argv', 'cwd', 'timeout_seconds', 'hidden_material_used'}
            or entry['version'] != 'v064-repository-public-test-entry-r1'
            or entry['instance_id'] != value['instance_id'] or not entry.get('argv')
            or entry['argv'][0] != value['public_python']):
        raise PublicTestSelectionError('The contract must keep the exact admitted public interpreter and entry')
    selected_entry(entry)
    environment = value['environment']
    if (not isinstance(environment, dict) or not environment
            or any(not isinstance(k, str) or not isinstance(v, str) or '\x00' in k + v
                   for k, v in environment.items())
            or environment.get('PATH', '').split(':')[0] != str(Path(value['public_python']).parent)
            or any(marker in text for text in environment.values()
                   for marker in ('/data0/', '/data1/', '/data2/', '/home/zhuxinrui', '/opt/pws-runtime'))):
        raise PublicTestSelectionError('Public tests must use only the admitted public environment')
    return copy.deepcopy(value)


def read_actor_contract(config):
    """A future worker validates the host-copied root-owned public contract."""
    info = CONTRACT_PATH.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o222):
        raise PublicTestSelectionError('The public contract must be a root-owned read-only regular file')
    raw = CONTRACT_PATH.read_bytes()
    if (len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != config.get('public_test_contract_sha256')):
        raise PublicTestSelectionError('The copied public contract differs from its host-admitted bytes')
    value = validate_contract(json.loads(raw))
    if value != contract_for_actor(config):
        raise PublicTestSelectionError('The public contract belongs to another actor task or lifetime')
    return value


def assert_native_actor_process():
    """The executable public launcher is never a host-side test runner."""
    if os.getpid() == 1 or not Path('/testbed').is_dir():
        raise PublicTestSelectionError('Invoke this public launcher only through the native actor terminal')
    command = Path('/proc/1/cmdline').read_bytes().split(b'\0')
    if b'/opt/pws-runtime/worker.py' not in command:
        raise PublicTestSelectionError('A private native actor PID namespace is required')
    status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    if (status.get('NoNewPrivs', '').strip() != '1'
            or any(int(status[name].strip(), 16) for name in ('CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb'))):
        raise PublicTestSelectionError('The public launcher requires the original capability-free actor boundary')
    interfaces = [line.split(':', 1)[0].strip() for line in Path('/proc/net/dev').read_text().splitlines()[2:]]
    if interfaces != ['lo']:
        raise PublicTestSelectionError('The public launcher cannot acquire an external network')


def _dependency_helper():
    here = Path(__file__).resolve()
    path = here.with_name('public-test-dependencies.py' if here.name == 'public-test-library.py'
                          else 'public_test_dependencies_v130.py')
    spec = importlib.util.spec_from_file_location('_pws_public_dependencies_v130', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_native_public_test(selection=None):
    """The same selected argv inside the existing native actor, with bounded output/time.

    Native terminal execution has no PROJECT version or delivery receipt. Its
    actor retains final namespace cleanup; this helper only manages its own
    subprocess group and never stops the persistent terminal or actor worker.
    """
    assert_native_actor_process()
    info = CONTRACT_PATH.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o222:
        raise PublicTestSelectionError('A root-owned read-only public contract must be installed')
    value = validate_contract(json.loads(CONTRACT_PATH.read_bytes()))
    if time.monotonic() >= value['actor_lifecycle_deadline']:
        raise PublicTestSelectionError('The original actor lifetime is exhausted')
    helper = _dependency_helper()
    dependency_profile = helper.native_profile(value['instance_id'])
    environment = helper.effective_test_environment(value['environment'], dependency_profile)
    entry, selected = selected_entry(value['entry'], selection, root='/testbed')
    timeout = min(entry['timeout_seconds'], value['actor_lifecycle_deadline'] - time.monotonic())
    here = Path(__file__).resolve()
    execution_path = here.with_name('public-test-execution.py'
        if here.name == 'public-test-library.py' else 'public_test_execution_v141.py')
    spec = importlib.util.spec_from_file_location('_pws_public_test_execution_v141', execution_path)
    execution = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(execution)
    observed = execution.execute_public_entry(entry, root='/testbed', environment=environment,
                                               timeout_seconds=timeout)
    return {**observed, 'version': VERSION,
            'public_test_result_revision': 'v141-session-bound-public-test-execution-r1',
            'public_dependency_profile': dependency_profile, 'selection': selected,
            'instance_id': value['instance_id'], 'timeout_seconds': timeout,
            'hidden_evaluation': False, 'arbitrary_command': False,
            'project_version_or_delivery_evidence': False,
            'contract_is_runtime_authority': False,
            'scope': 'Native convenience entry; existing terminal capabilities remain available'}
