"""Fixed operator control. Run only through the separately bounded GPU launcher."""
from __future__ import annotations

import argparse
import gc
import hashlib
import inspect
import json
from pathlib import Path
import statistics
import time
import traceback


def reference(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def write(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    temporary.replace(path)
    if path.name in {'progress.json', 'receipt.json'}:
        print('V054_KERNEL_' + ('RECEIPT' if path.name == 'receipt.json' else 'PROGRESS') + ' ' + json.dumps(value), flush=True)


def bindings(module, names):
    """Prove the actual decorator selected a separate optimized implementation."""
    raw, optimized, evidence = {}, {}, {}
    for name in names:
        symbol = getattr(module, name)
        original = inspect.unwrap(symbol)
        if original.__module__ != module.__name__ or original.__name__ != name:
            raise ValueError('Could not identify the original torch fallback: ' + name)
        node, selected = symbol, None
        while callable(node):
            closure = inspect.getclosurevars(node).nonlocals
            if {'implementation', 'is_new_implementation', 'torch_function'} <= closure.keys():
                selected = closure
                break
            node = getattr(node, '__wrapped__', None)
        if not selected or selected['is_new_implementation'] is not True:
            raise ValueError('No actual optimized implementation selected: ' + name)
        implementation = selected['implementation']
        package = 'causal_conv1d' if name.startswith('causal_conv') else 'fla'
        if not implementation.__module__.startswith(package + '.'):
            raise ValueError('Unexpected implementation package for ' + name)
        raw[name], optimized[name] = original, symbol
        evidence[name] = {'original': reference(inspect.getsourcefile(original)),
            'implementation_module': implementation.__module__,
            'implementation_qualname': implementation.__qualname__,
            'implementation': reference(inspect.getsourcefile(inspect.unwrap(implementation))),
            'is_new_implementation': True,
            'applicable_params': list(selected.get('applicable_params', ())) }
    return raw, optimized, evidence


def error_metrics(torch, left, right, plan, exact=False):
    thresholds = plan['numerical_thresholds']
    same_shape, same_dtype = left.shape == right.shape, left.dtype == right.dtype
    a, b = left.detach().cpu().float(), right.detach().cpu().float()
    finite = bool(torch.isfinite(a).all() and torch.isfinite(b).all())
    if same_shape and finite:
        diff = (a - b).abs()
        absolute = float(diff.max())
        rms = float((diff.square().mean()).sqrt())
        reference_rms = float(a.square().mean().sqrt())
        reference_max = float(a.abs().max())
        floor = thresholds['normalization_absolute_floor']
        nrms = rms / max(reference_rms, floor)
        nmax = absolute / max(reference_max, floor)
        equal = bool(torch.equal(a, b))
    else:
        absolute = rms = reference_rms = reference_max = nrms = nmax = None
        equal = False
    passed = same_shape and same_dtype and finite
    passed = passed and (equal if exact else nrms <= thresholds['normalized_rmse_maximum']
                         and nmax <= thresholds['normalized_max_absolute_error_maximum'])
    return {'shape': list(left.shape), 'reference_dtype': str(left.dtype), 'optimized_dtype': str(right.dtype),
        'shape_equal': same_shape, 'dtype_equal': same_dtype, 'finite': finite, 'bitwise_equal': equal,
        'max_absolute_error': absolute, 'rmse': rms, 'reference_rms': reference_rms,
        'reference_max_absolute': reference_max, 'normalized_rmse': nrms,
        'normalized_max_absolute_error': nmax, 'exact_required': exact, 'passed': bool(passed)}


def measured(torch, operation):
    torch.cuda.synchronize()
    started = time.perf_counter()
    result = operation()
    torch.cuda.synchronize()
    return result, (time.perf_counter() - started) * 1000


def run_case(torch, name, kind, make_operation, plan):
    operations = {which: make_operation(which) for which in ('reference', 'optimized')}
    first, initial = {}, {}
    for which in ('reference', 'optimized'):
        initial[which], first[which] = measured(torch, operations[which])
    checks = {'output': error_metrics(torch, initial['reference'][0], initial['optimized'][0], plan),
              'state': error_metrics(torch, initial['reference'][1], initial['optimized'][1], plan,
                                     exact=kind == 'convolution')}
    # Save only the short prefill's small cache for the true following decode checks.
    next_states = {which: initial[which][1].detach().clone() for which in initial}
    del initial
    for _ in range(plan['timing']['warmup_per_implementation']):
        for which in ('reference', 'optimized'):
            result, _ = measured(torch, operations[which])
            del result
    samples = {'reference': [], 'optimized': []}
    for index in range(plan['timing']['steady_samples_per_implementation']):
        order = ('reference', 'optimized') if index % 2 == 0 else ('optimized', 'reference')
        for which in order:
            result, elapsed = measured(torch, operations[which])
            samples[which].append(elapsed)
            del result
    medians = {which: statistics.median(values) for which, values in samples.items()}
    return {'name': name, 'kind': kind, 'checks': checks,
        'passed': all(value['passed'] for value in checks.values()),
        'first_call_ms_including_compile': first, 'steady_wall_ms': samples,
        'steady_wall_median_ms': medians,
        'observed_median_ratio_reference_over_optimized': medians['reference'] / medians['optimized'],
        'timing_includes_python_dispatch_and_same_state_clone': True,
        'shared_gpu_interference_uncontrolled': True,
        'torch_peak_allocated_bytes': torch.cuda.max_memory_allocated(),
        'torch_peak_reserved_bytes': torch.cuda.max_memory_reserved()}, next_states


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--family', choices=['all', 'delta', 'convolution'], default='all')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    plan = json.loads(args.plan.read_bytes())
    convolution = args.family in {'all', 'convolution'}
    delta = args.family in {'all', 'delta'}
    receipt = {'family': args.family, 'full_four_function_control': args.family == 'all', 'version': 'v054-kernel-control-r1', 'plan': reference(args.plan),
               'status': 'starting', 'cases': [], 'model_loads': 0, 'model_requests': 0,
               'official_scoring_calls': 0, 'initial_rng_seed': plan['seed']}
    try:
        import torch
        torch.set_num_threads(plan['resources']['maximum_cpu_threads'])
        torch.set_num_interop_threads(1)
        if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
            raise ValueError('Exactly the explicitly mapped control GPU must be visible')
        total = torch.cuda.get_device_properties(0).total_memory
        torch.cuda.set_per_process_memory_fraction(plan['resources']['maximum_torch_allocator_bytes'] / total, 0)
        torch.cuda.reset_peak_memory_stats()
        import triton
        receipt['triton_target'] = str(triton.runtime.driver.active.get_current_target())
        from transformers.models.qwen3_5 import modeling_qwen3_5 as qwen
        names = [name for name in plan['functions'] if (name.startswith('causal_conv') and convolution) or (name.startswith('torch_') and delta)]
        raw, fast, bound = bindings(qwen, names)
        receipt.update(torch_version=torch.__version__, cuda_version=torch.version.cuda,
            device_name=torch.cuda.get_device_name(0), bindings=bound,
            allocator_limit_bytes=plan['resources']['maximum_torch_allocator_bytes'])
        funcs = {'reference': raw, 'optimized': fast}
        generator = torch.Generator(device='cpu').manual_seed(plan['seed'])
        def random(shape, dtype=torch.bfloat16, scale=0.5):
            return (torch.randn(shape, generator=generator, dtype=torch.float32) * scale).to(dtype).cuda()
        short_states = {}
        with torch.inference_mode():
            for case in plan['prefill_cases']:
                length, channels, heads = case['sequence_length'], case['conv_channels'], case['value_heads']
                if convolution:
                    mixed = random((1, length, channels)).transpose(1, 2)
                    weight = random((channels, 4), scale=0.25)
                    def conv_operation(which, mixed=mixed, weight=weight):
                        def operation():
                            output = funcs[which]['causal_conv1d_fn'](mixed, weight, None, activation='silu')
                            return output, mixed[:, :, -4:].clone()
                        return operation
                    value, state = run_case(torch, 'conv_prefill_' + case['name'], 'convolution', conv_operation, plan)
                    value['input_shape'] = list(mixed.shape)
                    value['input_stride'] = list(mixed.stride())
                    receipt['cases'].append(value)
                    if case['name'] == 'short_actual_width':
                        short_states['conv'] = state
                        short_states['conv_weight'] = weight
                    del mixed, state, conv_operation
                if delta:
                    q = random((1, length, heads // 2, 128)).repeat_interleave(2, dim=2)
                    k = random((1, length, heads // 2, 128)).repeat_interleave(2, dim=2)
                    v = random((1, length, heads, 128))
                    g = -torch.nn.functional.softplus(random((1, length, heads), torch.float32)) * 0.1
                    beta = random((1, length, heads)).sigmoid()
                    def delta_operation(which, q=q, k=k, v=v, g=g, beta=beta):
                        return lambda: funcs[which]['torch_chunk_gated_delta_rule'](q, k, v, g=g, beta=beta,
                            initial_state=None, output_final_state=True, use_qk_l2norm_in_kernel=True)
                    value, state = run_case(torch, 'delta_prefill_' + case['name'], 'delta', delta_operation, plan)
                    value['input_shape'] = list(q.shape)
                    receipt['cases'].append(value)
                    if case['name'] == 'short_actual_width':
                        short_states['delta'] = state
                    del q, k, v, g, beta, state, delta_operation
                gc.collect()
                write(args.output / 'progress.json', receipt)
            for case in plan['decode_cases']:
                steps, channels, heads = case['steps'], case['conv_channels'], case['value_heads']
                if convolution:
                    mixed = random((1, steps, channels)).transpose(1, 2)
                    def conv_operation(which, mixed=mixed, steps=steps):
                        def operation():
                            state = short_states['conv'][which].clone()
                            outputs = []
                            for step in range(steps):
                                outputs.append(funcs[which]['causal_conv1d_update'](mixed[:, :, step:step+1], state,
                                    short_states['conv_weight'], None, activation='silu'))
                            return torch.cat(outputs, dim=-1), state
                        return operation
                    value, state = run_case(torch, 'conv_decode_' + case['name'], 'convolution', conv_operation, plan)
                    receipt['cases'].append(value)
                    del mixed, state, conv_operation
                if delta:
                    q = random((1, steps, heads // 2, 128)).repeat_interleave(2, dim=2)
                    k = random((1, steps, heads // 2, 128)).repeat_interleave(2, dim=2)
                    v = random((1, steps, heads, 128))
                    g = -torch.nn.functional.softplus(random((1, steps, heads), torch.float32)) * 0.1
                    beta = random((1, steps, heads)).sigmoid()
                    def delta_operation(which, q=q, k=k, v=v, g=g, beta=beta, steps=steps):
                        def operation():
                            # Both paths begin from exactly the same fp32 state.
                            # Differences then accumulate only within this decode chain.
                            state = short_states['delta']['reference'].clone()
                            outputs = []
                            for step in range(steps):
                                output, state = funcs[which]['torch_recurrent_gated_delta_rule'](
                                    q[:, step:step+1], k[:, step:step+1], v[:, step:step+1],
                                    g=g[:, step:step+1], beta=beta[:, step:step+1], initial_state=state,
                                    output_final_state=True, use_qk_l2norm_in_kernel=True)
                                outputs.append(output)
                            return torch.cat(outputs, dim=1), state
                        return operation
                    value, state = run_case(torch, 'delta_decode_' + case['name'], 'delta', delta_operation, plan)
                    receipt['cases'].append(value)
                    del q, k, v, g, beta, state, delta_operation
                gc.collect()
                write(args.output / 'progress.json', receipt)
        receipt.update(status='completed', passed=all(case['passed'] for case in receipt['cases']),
            torch_peak_allocated_bytes=torch.cuda.max_memory_allocated(),
            torch_peak_reserved_bytes=torch.cuda.max_memory_reserved())
    except BaseException as error:
        receipt.update(status='technical_unknown', passed=False,
            error={'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()})
    write(args.output / 'receipt.json', receipt)
    print(json.dumps({'status': receipt['status'], 'passed': receipt.get('passed'),
                      'cases_completed': len(receipt['cases'])}))
    return 0 if receipt.get('passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
