"""Official LLMLingua-2 probabilities for complete observation units, no training."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

from proworksim.software_benchmark_candidates_v054 import checked,reference,write_new
from proworksim.software_context_compression_v175 import EvidenceStore,baseline,observations,KEEP_RECENT,eligible_observations

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'runs/software-benchmark-v175/context-replay-r1'
OUT=ROOT/'artifacts/software-benchmark-v175/llmlingua-unit-scores-r2'


def main(device):
    import torch
    from transformers import AutoTokenizer,AutoModelForTokenClassification
    torch.set_num_threads(4)
    torch.set_float32_matmul_precision('highest')
    OUT.mkdir(parents=True,exist_ok=True)
    plan=json.loads((RUN/'plan.json').read_bytes());texts={};point_refs={}
    for point in plan['rows']:
        payload=json.loads(checked(point['source_capture']['payload']).read_bytes())
        store=EvidenceStore(point['point_id'],point['slot_id'],point['member_id'])
        original,refs=baseline(payload,store);indices=observations(original)
        candidates=eligible_observations(original)
        point_refs[point['point_id']]={}
        for index in candidates:
            text=original['messages'][index]['content'];key=hashlib.sha256(text.encode()).hexdigest()
            texts[key]=text;point_refs[point['point_id']][refs[index]]=key
    model_path=ROOT/'runs/software-benchmark-v175/compressor-model'
    receipt=json.loads((ROOT/'artifacts/software-benchmark-v175/model-source-r1/download-receipt.json').read_bytes())
    if receipt['official_model']!='microsoft/llmlingua-2-xlm-roberta-large-meetingbank':
        raise ValueError('Only the frozen official encoder is permitted')
    if device.startswith('cuda'):
        free,total=torch.cuda.mem_get_info(0)
        if free<16*1024**3:raise RuntimeError('Keep shared GPU memory headroom')
        torch.cuda.set_per_process_memory_fraction(.10,0)
    tokenizer=AutoTokenizer.from_pretrained(str(model_path),local_files_only=True,trust_remote_code=False)
    model=AutoModelForTokenClassification.from_pretrained(str(model_path),local_files_only=True,
        trust_remote_code=False,torch_dtype=torch.float32).to(device).eval()
    assert model.config.num_labels==2
    scores={};began=time.monotonic();token_count=0
    for number,(key,text) in enumerate(sorted(texts.items()),1):
        ids=tokenizer.encode(text,add_special_tokens=False,truncation=False,verbose=False)
        # Every original token is scored; chunks are an encoder context limit,
        # not silent truncation of the original tool result.
        parts=[ids[i:i+510] for i in range(0,len(ids),510)] or [[]]
        kept=[]
        for start in range(0,len(parts),4):
            batch=parts[start:start+4]
            inputs=[[tokenizer.bos_token_id,*part,tokenizer.eos_token_id] for part in batch]
            width=max(map(len,inputs))
            encoded={'input_ids':torch.tensor([part+[tokenizer.pad_token_id]*(width-len(part))
                for part in inputs],device=device),
                'attention_mask':torch.tensor([[1]*len(part)+[0]*(width-len(part)) for part in inputs],device=device)}
            with torch.inference_mode():
                probabilities=model(**encoded).logits.softmax(dim=-1)[:,:,1]
            for i,part in enumerate(batch):kept.extend(probabilities[i,1:len(part)+1].float().cpu().tolist())
        if len(kept)!=len(ids):raise ValueError('Token classification coverage lost')
        token_count+=len(ids)
        scores[key]={'mean_preservation_probability':sum(kept)/len(kept) if kept else 0,
            'encoder_tokens':len(ids),'characters':len(text),'chunks':len(parts)}
        if number%25==0:print(json.dumps({'units':number,'total_units':len(texts),'seconds':time.monotonic()-began}),flush=True)
    value={'version':'v175-llmlingua2-whole-observation-ranking-r1','plan':reference(RUN/'plan.json'),
        'model_source':reference(ROOT/'artifacts/software-benchmark-v175/model-source-r1/download-receipt.json'),
        'scores':scores,'point_scores':{p:{ref:scores[key]['mean_preservation_probability'] for ref,key in items.items()}
            for p,items in point_refs.items()},'device':device,'physical_gpu':os.environ.get('CUDA_VISIBLE_DEVICES'),
        'neural_encoder_tokens':token_count,'wall_seconds':time.monotonic()-began,
        'peak_gpu_bytes':torch.cuda.max_memory_allocated(0) if device.startswith('cuda') else 0,
        'torch_version':torch.__version__,'new_training':False,'API_calls':0,
        'official_token_probability_class':1,'selection_unit':'complete_original_tool_observation',
        'original_paper_full_word_deletion_reproduction_claimed':False}
    write_new(OUT/'summary.json',value)
    print(json.dumps({'complete':True,'units':len(scores),'encoder_tokens':token_count,'seconds':value['wall_seconds']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--device',default='cpu');args=p.parse_args()
    os.nice(10);os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[-4:]);main(args.device)
