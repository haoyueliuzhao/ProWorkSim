"""Readback accumulation for multi-file responsibility packages; original Harness acts."""
import copy,hashlib
from .software_responsibility_transfer_v203 import TransferEvidence as Previous
from .software_syntax_facts_v202 import SourceAssembler
from .software_dual_graph_v203 import identity

class MultiFileTransfer(Previous):
    def __init__(self,package):
        super().__init__(package);self.assembler=SourceAssembler();self.received={};self.read_receipts=[];self.adoptions={};self.package_stale=False;self.verification_current=False
        for f in package['required_facts']:
            if not {'fact_id','path','value','source_reference','value_sha256','start_character','end_character'}<=set(f):raise ValueError('Each required fact needs a file, exact version, range and content hash')
            if hashlib.sha256(f['value'].encode()).hexdigest()!=f['value_sha256']:raise ValueError('Required fact content hash mismatch')
            if f['end_character']-f['start_character']!=len(f['value']) or f['start_character']<0:raise ValueError('Required fact interval differs from text')
        if len({f['fact_id'] for f in package['required_facts']})!=len(package['required_facts']):raise ValueError('Duplicate fact identity')
    def read_fact(self,receipt):
        if self.state!='ACCEPTED' or not self.package_read_receipt:raise ValueError('Read full package after actual acceptance first')
        r=receipt.get('result',{});p=self.package
        if not receipt.get('ok') or receipt.get('tool')!='read_file' or receipt.get('actor')!=p['new_owner'] or not receipt.get('source'):raise ValueError('Recipient executed source read required')
        self.check_receipt(receipt)
        candidates=[f for f in p['required_facts'] if f['path']==r.get('path') and f['source_reference']==r.get('source_reference')]
        if not candidates:raise ValueError('Read version/path is not authorized by package')
        text=r['text'];start=r.get('start_character',0);end=r.get('end_character',start+len(text));total=r.get('total_characters')
        if total is None:raise ValueError('Partial read extent must be explicit')
        # Work on a copy so a conflicting page cannot poison previously accepted evidence.
        staged=copy.deepcopy(self.assembler);doc=staged.add(scope=['migration',p['new_owner']],path=r['path'],version=r['source_reference'],start=start,end=end,total=total,
            text=text,source_id=str(receipt['source']),message_sha256=hashlib.sha256(text.encode()).hexdigest())
        received=dict(self.received)
        for f in candidates:
            pieces=[x['result'] for x in self.read_receipts+[receipt] if x['result'].get('path')==f['path'] and x['result'].get('source_reference')==f['source_reference']]
            position=f['start_character'];value=''
            for piece in sorted(pieces,key=lambda x:(x['start_character'],-x['end_character'])):
                if piece['end_character']<=position:continue
                if piece['start_character']>position:break
                stop=min(piece['end_character'],f['end_character']);value+=piece['text'][position-piece['start_character']:stop-piece['start_character']];position=stop
                if position==f['end_character']:break
            if position==f['end_character']:
                if value!=f['value']:raise ValueError('Actual source differs from required fact')
                received[f['fact_id']]={'source':copy.deepcopy(receipt['source']),'version':r['source_reference'],'path':r['path']}
        self.assembler=staged;self.received=received;self.read_receipts.append(copy.deepcopy(receipt))
    def advance(self,target,receipt):
        self.check_receipt(receipt)
        if self.package_stale:raise ValueError('Task revision changed; migration package must be renegotiated')
        if target=='RESUMED':
            if set(self.adoptions)!=set(self.package['artifacts']) or receipt not in self.adoptions.values():raise ValueError('All required artifacts must be explicitly adopted')
        if target!='CONTEXT_TRANSFERRED':
            result=super().advance(target,receipt)
            if target=='VERIFIED':self.verification_current=True
            return result
        if self.state!='ACCEPTED' or not self.package_read_receipt or set(self.received)!={f['fact_id'] for f in self.package['required_facts']}:raise ValueError('All version-bound required facts must actually be read')
        if receipt not in self.read_receipts:raise ValueError('Unrecorded read receipt')
        self.history.append({'from':self.state,'to':target,'receipt':copy.deepcopy(receipt),'all_required_fact_receipts':copy.deepcopy(self.received)})
        self.state=target
    def acknowledge_package(self,receipt):
        self.check_receipt(receipt)
        return super().acknowledge_package(receipt)
    @staticmethod
    def check_receipt(receipt):
        original=receipt.get('full_response')
        if not original or original.get('result')!=receipt.get('result') or identity(original)!=receipt.get('source',{}).get('response_sha256'):raise ValueError('Readback differs from original executor receipt')
    def record_adoption(self,receipt):
        self.check_receipt(receipt);r=receipt['result']
        if self.state!='CONTEXT_TRANSFERRED' or not receipt.get('ok') or receipt['actor']!=self.package['new_owner'] or receipt['tool']!='integrate_patch' or r.get('patch_id') not in self.package['artifacts']:raise ValueError('Unbound adoption')
        self.adoptions[r['patch_id']]=copy.deepcopy(receipt)
    def observe_world_receipt(self,receipt):
        if not receipt.get('ok'):return
        self.check_receipt(receipt);r=receipt['result']
        if receipt['tool']=='revise_task' and r.get('task_id')==self.package['task_id'] and r.get('revision')!=self.package['task_revision']:self.package_stale=True
        if receipt['actor']==self.package['new_owner'] and receipt['tool'] in {'write_file','replace_file','create_file','delete_file','rename_file','integrate_patch'} and self.state in {'RESUMED','VERIFIED'}:
            self.recipient_version=r['source_reference'];self.verification_current=False
