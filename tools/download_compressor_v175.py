"""Pinned LLMLingua-2 weights from a domestic mirror, without proxy/training."""
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
META=ROOT/'artifacts/software-benchmark-v175/model-source-r1'
OUT=ROOT/'runs/software-benchmark-v175/compressor-model'
FILES=('config.json','special_tokens_map.json','tokenizer_config.json','tokenizer.json','model.safetensors')


class DomesticRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        host=urllib.parse.urlparse(newurl).hostname or ''
        if not (host.endswith('modelscope.cn') or ('.oss-cn-' in host and host.endswith('.aliyuncs.com'))):
            raise ValueError('The domestic model download would redirect outside its approved sources')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    domestic=json.loads((META/'modelscope-metadata.json').read_bytes())['Data']['Files']
    official=json.loads((META/'official-mirror-large-metadata.json').read_bytes())
    by_name={r['Name']:r for r in domestic};refs={r['rfilename']:r for r in official['siblings']}
    client=urllib.request.build_opener(urllib.request.ProxyHandler({}),DomesticRedirect())
    receipts=[]
    for name in FILES:
        row,expected=by_name[name],refs[name];path=OUT/name;partial=path.with_suffix(path.suffix+'.partial')
        assert row['Size']==expected['size']
        if expected.get('lfs'):assert row['Sha256']==expected['lfs']['sha256']
        url='https://modelscope.cn/api/v1/models/cooperwang1587/llmlingua-2-xlm-roberta-large-meetingbank/repo?'+urllib.parse.urlencode({'Revision':row['Revision'],'FilePath':name})
        if not path.exists():
            offset=partial.stat().st_size if partial.exists() else 0
            request=urllib.request.Request(url,headers={'Range':f'bytes={offset}-'} if offset else {})
            began=time.monotonic()
            with client.open(request,timeout=60) as response:
                if offset and response.status!=206:raise ValueError('Resume requires an exact range response')
                final_host=urllib.parse.urlparse(response.geturl()).hostname
                with partial.open('ab' if offset else 'xb') as stream:
                    while chunk:=response.read(1024**2):
                        stream.write(chunk);offset+=len(chunk)
                        if offset>row['Size']:raise ValueError('Unexpected model download size')
                    stream.flush();os.fsync(stream.fileno())
            if offset!=row['Size']:raise ValueError('Incomplete model bytes')
            partial.rename(path)
            print(json.dumps({'file':name,'bytes':offset,'source_host':final_host,'wall_seconds':time.monotonic()-began}),flush=True)
        h=hashlib.sha256();git=hashlib.sha1(b'blob '+str(row['Size']).encode()+b'\0')
        with path.open('rb') as stream:
            while chunk:=stream.read(4*1024**2):h.update(chunk);git.update(chunk)
        if h.hexdigest()!=row['Sha256'] or (not expected.get('lfs') and git.hexdigest()!=expected['blobId']):
            raise ValueError('Domestic asset differs from the pinned official repository')
        receipts.append({'path':str(path),'sha256':h.hexdigest(),'bytes':path.stat().st_size,
            'official_model_revision':official['sha'],'mirror_revision':row['Revision']})
    receipt={'official_model':official['id'],'official_revision':official['sha'],'files':receipts,
        'weight_SHA256_verified_against_official_HF_blob_page':True,
        'official_weight_page':'https://huggingface.co/microsoft/llmlingua-2-xlm-roberta-large-meetingbank/blob/main/model.safetensors',
        'download_source':'domestic_modelscope','proxy_used':False,'new_training':False,
        'old_Qwen_weights_restored':False,'remote_python_code_loaded':False}
    (META/'download-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print('Pinned domestic compressor download complete',flush=True)


if __name__=='__main__':
    os.nice(10);main()
