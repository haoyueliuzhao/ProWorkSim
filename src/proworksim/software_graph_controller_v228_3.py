"""Prospective diagnosis-header fix. Keep the frozen v228 execution and evidence checks."""
import re
from .software_graph_controller_v228 import ControlledWorld as PriorWorld
from .tool_outcomes import ToolRejection


class ControlledWorld(PriorWorld):
    def _tool_project_action(self,actor,project_id,tool,arguments,interface_profile=None):
        control=self.protocol().get('graph_control')
        body=arguments.get('body') if tool=='send_message' else None
        if not control or not isinstance(body,str) or not body.startswith('DIAG '):
            return super()._tool_project_action(actor,project_id,tool,arguments,interface_profile)
        # Only normalize the separator after a decimal event ID; preserve the finding text.
        normalized=re.sub(r'^DIAG ([0-9]+)[:：](?=\s)',r'DIAG \1',body,count=1)
        if normalized!=body:
            arguments={**arguments,'body':normalized}
        try:
            return super()._tool_project_action(actor,project_id,tool,arguments,interface_profile)
        except ToolRejection as exc:
            duty=control['duties'].get(arguments.get('task_id'))
            if (exc.rejection['code']=='graph_evidence_required' and duty and duty['status']=='pending'
                    and duty['owner']==actor and duty['recipient']==arguments.get('recipient')):
                exc.rejection['context']['available_own_evidence_sequences'] = self.diagnosis_evidence(actor)[-6:][::-1]
            raise
