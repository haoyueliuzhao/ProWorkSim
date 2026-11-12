"""Migration evidence requires complete permitted package readback, not a preview."""
import copy,json
from .software_org_policy_v203 import TransferEvidence as BaseTransferEvidence

class TransferEvidence(BaseTransferEvidence):
    def __init__(self,package):
        super().__init__(package);self.package_read_receipt=None
    def acknowledge_package(self,receipt):
        r=receipt.get('result',{})
        if self.state!='ACCEPTED' or not receipt.get('ok') or not receipt.get('source') or receipt.get('tool')!='read_work_event' or receipt.get('actor')!=self.package['new_owner']:
            raise ValueError('Full addressed package requires successful recipient read_work_event')
        if r.get('recipient')!=self.package['new_owner'] or r.get('actor_id')!=self.package['old_owner'] or r.get('task_id')!=self.package['task_id']:
            raise ValueError('Wrong package sender, recipient or task')
        if json.loads(r.get('body','null'))!=self.package:raise ValueError('Package is incomplete or different')
        self.package_read_receipt=copy.deepcopy(receipt)
    def advance(self,target,receipt):
        if target=='ACCEPTED' and receipt.get('result',{}).get('task_id')!=self.package['task_id']:raise ValueError('Wrong accepted task')
        if target=='CONTEXT_TRANSFERRED' and self.package_read_receipt is None:raise ValueError('A message preview is not a complete migration package')
        return super().advance(target,receipt)
