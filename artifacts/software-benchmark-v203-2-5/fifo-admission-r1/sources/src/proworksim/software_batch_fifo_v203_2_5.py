"""Batch-owned FIFO model service for the next organization pilot.

Uses the existing production wire protocol and FifoModelTransport. No listener,
host-global path, secret or service configuration is created. A provider backend
is injected explicitly; this revision admits deterministic controls only.
"""
from __future__ import annotations
import json,os,threading,time
from pathlib import Path
from . import software_benchmark_model_fifo_v064 as protocol


class BatchFifo:
    def __init__(self,folder,backend,*,guard=lambda:None):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=False)
        self.backend,self.guard=backend,guard
        self.stop=threading.Event();self.error=None;self.calls=[]
        self.request=protocol.open_fifo(self.folder/'model-request.fifo',create=True)
        self.response=protocol.open_fifo(self.folder/'model-response.fifo',create=True)
        self.transport=protocol.FifoModelTransport('http://127.0.0.1:18219',control=self.folder)
        self.thread=threading.Thread(target=self.serve,name='v20325-batch-model-fifo',daemon=True)
        self.thread.start()

    def serve(self):
        reader=protocol.LineReader(self.request);count=0
        try:
            while not self.stop.is_set():
                try:request=reader.read(time.monotonic()+.5)
                except TimeoutError:continue
                count+=1
                self.guard()
                outer=self
                class Backend:
                    def post(self,path,payload):return outer.backend(path,payload)
                response=protocol.model_response(request,Backend(),count)
                self.calls.append({'id':count,'path':request['path'],
                    'member_id':request['payload'].get('member_id'),
                    'usage_id':request['payload'].get('usage_id'),'ok':response['ok']})
                protocol.write_frame(self.response,response,time.monotonic()+30)
        except BaseException as error:
            self.error={'type':type(error).__name__,'message':str(error)}

    def post(self,path,payload):
        # Check before even counting/reserving the next model opportunity.
        self.guard()
        if self.error:raise RuntimeError(str(self.error))
        return self.transport.post(path,payload)

    def snapshot(self):
        return {'protocol':protocol.VERSION,'requests':len(self.calls),
            'generation_requests':sum(r['path']=='/chat/completions' for r in self.calls),
            'calls':self.calls,'error':self.error,'host_listener':False,
            'path_scope':'this_batch_owned_directory','external_API_calls':0,
            'provider':'deterministic_control_only','paid_backend_admitted':False}

    def close(self):
        self.stop.set();self.thread.join(2)
        if self.thread.is_alive():raise RuntimeError('Batch FIFO service did not quiesce')
        self.transport.close();os.close(self.request);os.close(self.response)
        for name in ('model-request.fifo','model-response.fifo'):(self.folder/name).unlink()
        (self.folder/'receipt.json').write_text(json.dumps(self.snapshot(),indent=2)+'\n')
