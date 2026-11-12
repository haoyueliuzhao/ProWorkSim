"""Ordinary-user pinned Python for REF, without host mounts or namespaces.

The ELF loader's argv0 option makes Python expose this small launcher as
sys.executable. Multiprocessing and Python subprocesses therefore use the same
private loader, while host compilers retain their own normal libc environment.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

from .software_benchmark_candidates_v054 import checked, reference, write_new

ROOT = Path(__file__).resolve().parents[2]
SYSROOT = Path('/data0/zhuxinrui/proworksim-runtime/sysroot')
RUNTIME = ROOT / 'runs/software-benchmark-v061/model-runtime-r3'
SITE = ROOT / 'runs/software-benchmark-v054/ref-venv/lib/python3.12/site-packages'
HEADERS_SOURCE = ROOT / 'runs/software-benchmark-v054/ref-toolchain/usr/include'
HEADER_PACKAGE = ROOT / 'runs/software-benchmark-v054/ref-toolchain-apt/var/cache/apt/archives/libpython3.12-dev_3.12.3-1_amd64.deb'
HEADER_PACKAGE_SHA256 = 'f5924a06298ae0689128498276d3a555e02615a4ecfa8f4417d679a097586f35'
VERSION = 'v061-ordinary-ref-python-loader-r3-private-python-headers'


def wrapper_source(directory=RUNTIME):
    loader = SYSROOT / 'usr/lib64/ld-linux-x86-64.so.2'
    python = SYSROOT / 'usr/bin/python3.12'
    libraries = ':'.join(map(str, (SYSROOT / 'usr/lib/x86_64-linux-gnu', SYSROOT / 'usr/lib',
                                    Path('/usr/lib/x86_64-linux-gnu'))))
    return r'''#include <unistd.h>
#include <stdlib.h>
#include <stdio.h>
#include <limits.h>
int main(int argc, char **argv) {
    if (getuid() == 0 || geteuid() == 0) { fputs("ordinary user required\n", stderr); return 126; }
    char self[PATH_MAX]; ssize_t n = readlink("/proc/self/exe", self, sizeof(self)-1);
    if (n <= 0 || n >= (ssize_t)sizeof(self)-1) return 126;
    self[n] = 0;
    char **args = calloc((size_t)argc + 9, sizeof(char *));
    if (!args) return 126;
    args[0] = LOADER; args[1] = "--library-path"; args[2] = LIBRARIES;
    args[3] = "--argv0"; args[4] = self; args[5] = PYTHON;
    args[6] = "-S"; args[7] = "-P";
    for (int i=1; i<argc; ++i) args[i+7] = argv[i];
    execv(args[0], args); perror("private Python exec"); free(args); return 126;
}
'''.replace('LOADER', json.dumps(str(loader))).replace('LIBRARIES', json.dumps(libraries)).replace('PYTHON', json.dumps(str(python)))


def runtime_environment(*, gpu_uuid=None, cache=None, inherited=None):
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError('REF host Python must run as an ordinary user')
    source = os.environ if inherited is None else inherited
    env = {name: source[name] for name in ('HOME', 'USER', 'LOGNAME') if name in source}
    env.update(PYTHONHOME=str(SYSROOT / 'usr'), PYTHONPATH=os.pathsep.join((str(ROOT / 'src'), str(SITE))),
        PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', PYTHONSAFEPATH='1',
        PATH=str(RUNTIME) + ':/usr/local/cuda-13.0/bin:/usr/bin:/bin', LANG='C.UTF-8', LC_ALL='C.UTF-8',
        HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
        LITELLM_LOCAL_MODEL_COST_MAP='True', VLLM_NO_USAGE_STATS='1', DO_NOT_TRACK='1',
        PYTHON_DOTENV_DISABLED='1', HTTP_PROXY='', HTTPS_PROXY='', ALL_PROXY='',
        http_proxy='', https_proxy='', all_proxy='', NO_PROXY='*', no_proxy='*',
        CUDA_HOME='/usr/local/cuda-13.0', TRITON_LIBCUDA_PATH='/usr/lib/x86_64-linux-gnu',
        PYTORCH_CUDA_ALLOC_CONF='backend:native', CUDA_VISIBLE_DEVICES=gpu_uuid or '')
    includes = os.pathsep.join((str(RUNTIME / 'include/python3.12'), str(RUNTIME / 'include')))
    env.update(CPATH=includes, C_INCLUDE_PATH=includes, CPLUS_INCLUDE_PATH=includes)
    if cache is not None:
        cache = Path(cache).resolve()
        if not cache.is_relative_to(ROOT / 'runs/software-benchmark-v061'):
            raise ValueError('REF caches must remain in the independent v061 run root')
        env.update(TMPDIR=str(cache), VLLM_CACHE_ROOT=str(cache), XDG_CACHE_HOME=str(cache),
                   TORCHINDUCTOR_CACHE_DIR=str(cache / 'inductor'), CUDA_CACHE_PATH=str(cache / 'cuda'))
    return env


def prepare_runtime():
    """Compile only a tiny user executable; no GPU or model is initialized."""
    runtime_environment()
    if not SITE.is_dir() or not (SYSROOT / 'usr/bin/python3.12').is_file():
        raise ValueError('Pinned local REF Python/packages are unavailable')
    manifest = RUNTIME / 'manifest.json'
    if manifest.exists():
        value = json.loads(manifest.read_bytes())
        for field in ('binary', 'source', 'python', 'loader', 'adapter', 'ninja',
                      'python_header', 'pyconfig_header', 'patchlevel_header'):
            checked(value[field])
        if value['version'] != VERSION or checked(value['adapter']) != Path(__file__).resolve():
            raise ValueError('Prepared Python launcher does not bind this source')
        return value
    RUNTIME.mkdir(parents=True, exist_ok=True)
    package = reference(HEADER_PACKAGE)
    if package['sha256'] != HEADER_PACKAGE_SHA256:
        raise ValueError('Cached Python development package differs from its authenticated index')
    for relative in ('python3.12', 'x86_64-linux-gnu/python3.12'):
        source_headers, target_headers = HEADERS_SOURCE / relative, RUNTIME / 'include' / relative
        if not target_headers.exists():
            shutil.copytree(source_headers, target_headers)
    if '#define PY_VERSION              "3.12.3"' not in (RUNTIME / 'include/python3.12/patchlevel.h').read_text():
        raise ValueError('Private compiler headers must match Python 3.12.3')
    source, binary = RUNTIME / 'python-loader.c', RUNTIME / 'python'
    source.write_text(wrapper_source())
    subprocess.run(['/usr/bin/gcc', '-O2', '-Wall', '-Wextra', '-Werror', '-o', str(binary), str(source)],
                   env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'}, check=True, timeout=60)
    ninja_source = ROOT / 'runs/software-benchmark-v054/ref-venv/bin/ninja'
    if not ninja_source.is_file():
        raise ValueError('The pinned local compiler scheduler is missing')
    ninja = RUNTIME / 'ninja'
    if not ninja.exists():
        ninja.symlink_to(ninja_source)
    if ninja.resolve() != ninja_source.resolve():
        raise ValueError('Unexpected compiler scheduler target')
    value = {'version': VERSION, 'binary': reference(binary), 'source': reference(source),
        'adapter': reference(__file__), 'python': reference(SYSROOT / 'usr/bin/python3.12'),
        'loader': reference(SYSROOT / 'usr/lib64/ld-linux-x86-64.so.2'),
        'pinned_package_directory': str(SITE), 'ninja': reference(ninja_source), 'host_root_operations': False,
        'python_header': reference(RUNTIME / 'include/python3.12/Python.h'),
        'pyconfig_header': reference(RUNTIME / 'include/x86_64-linux-gnu/python3.12/pyconfig.h'),
        'patchlevel_header': reference(RUNTIME / 'include/python3.12/patchlevel.h'),
        'header_source': str(HEADERS_SOURCE), 'header_package': package,
        'compiler_include_paths': runtime_environment()['CPATH'].split(os.pathsep),
        'shared_sysroot_or_system_headers_changed': False,
        'global_loader_environment_changed': False, 'model_loads': 0}
    write_new(manifest, value)
    return value


def launch_spec(arguments, *, gpu_uuid=None, cache=None):
    if not arguments:
        raise ValueError('Pass a Python script or module')
    prepared = prepare_runtime()
    return [str(checked(prepared['binary'])), *map(str, arguments)], runtime_environment(gpu_uuid=gpu_uuid, cache=cache)
