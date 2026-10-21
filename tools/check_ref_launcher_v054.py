"""One CPU check of the new compiler overlay and the exact installed REF CLI."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import traceback

from prepare_model_capacity_v054 import ref_argv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cli-only', action='store_true')
    parser.add_argument('--allow-device-metadata', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    record = {'started_utc': datetime.now(timezone.utc).isoformat(), 'passed': False,
              'model_loads': 0, 'model_calls': 0, 'gpu_opens': 0, 'weight_opens': 0,
              'external_network_attempts': 0, 'formal_execution_authorized': False}
    record['cli_only'] = args.cli_only
    record['device_metadata_access_authorized'] = args.allow_device_metadata
    def audit(event, values):
        if event in ('socket.connect', 'socket.getaddrinfo', 'socket.sendto'):
            record['external_network_attempts'] += 1
            raise RuntimeError('Network forbidden in this launcher CPU check')
        if event == 'open' and values and isinstance(values[0], (str, bytes)):
            name = os.fsdecode(values[0])
            if name.endswith(('.safetensors', '.gguf')):
                record['weight_opens'] += 1
                raise RuntimeError('No weights in launcher CPU check')
            if name.startswith('/dev/nvidia'):
                record['gpu_opens'] += 1
                if not args.allow_device_metadata:
                    raise RuntimeError('No GPU in launcher CPU check')
    sys.addaudithook(audit)
    try:
        assert bool(os.environ.get('CUDA_VISIBLE_DEVICES')) == args.allow_device_metadata
        record['compiler_paths'] = {name: shutil.which(name) for name in ('gcc', 'g++', 'ld', 'ninja')}
        assert all(record['compiler_paths'].values())
        source = args.output / 'check.cpp'
        source.write_text('#include <Python.h>\n#include <vector>\n'
            'static PyObject* check(PyObject*,PyObject*){return PyLong_FromLong(std::vector<int>{54}.at(0));}\n'
            'static PyMethodDef methods[]={{"check",check,METH_NOARGS,nullptr},{nullptr,nullptr,0,nullptr}};\n'
            'static PyModuleDef module={PyModuleDef_HEAD_INIT,"pws_v054_compiler",nullptr,-1,methods};\n'
            'PyMODINIT_FUNC PyInit_pws_v054_compiler(){return PyModule_Create(&module);}\n')
        extension = args.output / ('pws_v054_compiler' + sysconfig.get_config_var('EXT_SUFFIX'))
        if not args.cli_only:
            compilation = subprocess.run(['g++', '-shared', '-fPIC', '-O2', '-std=c++17',
                                         '-I' + sysconfig.get_path('include'), str(source), '-o', str(extension)],
                                        capture_output=True, text=True, timeout=60)
            record['compilation'] = {'exit_code': compilation.returncode, 'stderr': compilation.stderr}
            compilation.check_returncode()
            spec = importlib.util.spec_from_file_location('pws_v054_compiler', extension)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            assert module.check() == 54
            record['compiled_python_extension_loaded'] = True
        from vllm.utils.argparse_utils import FlexibleArgumentParser
        from vllm.entrypoints.cli.serve import ServeSubcommand
        command = ServeSubcommand()
        cli = FlexibleArgumentParser()
        command.subparser_init(cli.add_subparsers(dest='subcommand'))
        options = cli.parse_args(ref_argv()[2:])
        command.validate(options)
        for key, value in {'max_model_len': 131072, 'max_num_seqs': 1,
                           'gpu_memory_utilization': 0.8, 'tensor_parallel_size': 1,
                           'enable_prefix_caching': False, 'language_model_only': True,
                           'tool_call_parser': 'qwen3_coder', 'reasoning_parser': 'qwen3',
                           'generation_config': 'vllm', 'dtype': 'bfloat16'}.items():
            assert getattr(options, key) == value, key
        record['exact_installed_cli_passed'] = True
        record['ref_argv'] = ref_argv()
        import torch
        record['torch_cuda_initialized'] = torch.cuda.is_initialized()
        record['passed'] = True
    except BaseException as error:
        record['error'] = repr(error)
        record['traceback'] = traceback.format_exc()
    record['finished_utc'] = datetime.now(timezone.utc).isoformat()
    (args.output / 'receipt.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(record, ensure_ascii=False))
    return 0 if record['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
