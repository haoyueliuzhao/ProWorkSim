"""Fixed control only for the new FP32 recurrent operator; no model load."""
import argparse
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
    parser=argparse.ArgumentParser()
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--family')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    plan=json.loads(args.plan.read_bytes())
    receipt={'version':'v054-fp32-recurrent-control-r1','plan':reference(args.plan),
        'source':plan['source'],'status':'starting','cases':[],
        'model_loads':0,'model_requests':0,'official_scoring_calls':0,
        'operator_only':True,'old_FLA_controls_repeated':False}
    try:
        import torch
        torch.set_num_threads(2)
        torch.set_num_interop_threads(1)
        if not torch.cuda.is_available() or torch.cuda.device_count()!=1:
            raise ValueError('Exactly one mapped GPU is required')
        total=torch.cuda.get_device_properties(0).total_memory
        torch.cuda.set_per_process_memory_fraction(plan['resources']['maximum_torch_allocator_bytes']/total,0)
        torch.cuda.reset_peak_memory_stats()
        if reference(Path(plan['source']['path']))!=plan['source']:
            raise ValueError('Frozen custom kernel source changed')
        from transformers.models.qwen3_5 import modeling_qwen3_5 as qwen
        raw=inspect.unwrap(qwen.torch_recurrent_gated_delta_rule)
        import proworksim_fp32_recurrent as kernel
        receipt['installation']=kernel.install()
        fast=qwen.torch_recurrent_gated_delta_rule
        closure=inspect.getclosurevars(fast).nonlocals
        assert closure['is_new_implementation'] is True
        assert inspect.unwrap(fast) is raw
        assert Path(inspect.getsourcefile(closure['implementation'])).resolve()==Path(plan['source']['path']).resolve()
        receipt.update(torch_version=torch.__version__,cuda_version=torch.version.cuda,
                       device_name=torch.cuda.get_device_name(0))
        generator=torch.Generator(device='cpu').manual_seed(plan['seed'])
        def random(shape,dtype=torch.bfloat16,scale=.5):
            return (torch.randn(shape,generator=generator,dtype=torch.float32)*scale).to(dtype).cuda()
        with torch.inference_mode():
            for case in plan['cases']:
                batch,steps=case['batch_size'],case['steps']
                query=random((batch,steps,32,128))
                key=random((batch,steps,32,128))
                value=random((batch,steps,32,128))
                decay=-random((batch,steps,32),torch.float32).abs()
                beta=torch.sigmoid(random((batch,steps,32),torch.float32))
                initial=None if case['initial_state'] is None else random((batch,32,128,128),torch.float32,.1).transpose(-2,-1)
                before=None if initial is None else initial.clone()
                def make_operation(which):
                    function=raw if which=='reference' else fast
                    def operation():
                        state=initial
                        outputs=[]
                        for index in range(steps):
                            output,state=function(query[:,index:index+1],key[:,index:index+1],value[:,index:index+1],
                                decay[:,index:index+1],beta[:,index:index+1],initial_state=state,
                                output_final_state=True,use_qk_l2norm_in_kernel=True)
                            outputs.append(output)
                        return torch.cat(outputs,dim=1),state
                    return operation
                result,_=run_case(torch,case['name'],'delta',make_operation,plan)
                result['initial_state_unchanged']=initial is None or torch.equal(initial,before)
                result['passed']=result['passed'] and result['initial_state_unchanged']
                result['batch_size']=batch
                result['steps']=steps
                result['reference_input_dtype']='torch.bfloat16'
                result['initial_state_strides']=None if initial is None else list(initial.stride())
                result['per_step_qkv_strides']=list(query[:,0:1].stride())
                receipt['cases'].append(result)
                write(args.output/'progress.json',receipt)
        receipt.update(status='completed',passed=all(c['passed'] for c in receipt['cases']),
            torch_peak_allocated_bytes=torch.cuda.max_memory_allocated(),
            torch_peak_reserved_bytes=torch.cuda.max_memory_reserved(),
            optimized_single_step_kernel_calls=40,reference_single_step_calls=40,
            initial_rng_seed=plan['seed'],thresholds_unchanged=True,
            full_model_equivalence_claimed=False,formal_deployment=False)
    except Exception as error:
        receipt.update(status='technical_unknown',passed=False,error={
            'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()})
    write(args.output/'receipt.json',receipt)
    return 0 if receipt.get('passed') else 1

if __name__=='__main__':
    raise SystemExit(main())
