"""Independent12-case validation of source-labeled reading and format recovery."""
import copy

from . import software_context_probe_v178 as previous
from .software_context_api_v175 import ReplayLedger
from .software_context_compression_v175 import canonical
from .software_benchmark_candidates_v054 import reference
from .software_context_reader_v179 import SourceLabeledHistoryReader,citation_format_feedback

ROOT,OLD,MAX_DECISIONS,load=previous.ROOT,previous.OLD,previous.MAX_DECISIONS,previous.load
RUN=ROOT/'runs/software-benchmark-v179/recovery-reader-validation-r1'
evaluate=previous.evaluate


def restore_store(ref):
    data=load(ref);store=SourceLabeledHistoryReader(data['point_id'],data['slot_id'],data['member_id'])
    store.entries=data['entries'];return store


def input_payload(case):
    value=copy.deepcopy(previous.input_payload(case));value['user_id']='pws_v179_'+case['case_id']
    value['messages'][0]['content']+=' Source version_id always means source_reference.version_id, never the report format/schema version. Reader source_identity labels those separately. Copy exact citation objects from citable_messages; put commentary in rationale. Index metadata can locate a message but does not count as reading its contents.'
    value['tools'][0]['function']['description']+=' Returned citable_messages are copyable exact identities for text actually read. A source_identity header distinguishes report_schema_version from workspace_version_id. Index metadata includes exact tool-call pairing.'
    return value


class ProbeLedger(ReplayLedger):
    def __init__(self,*,phase_plan,authority):
        super().__init__(OLD/'api-ledger.sqlite',plan_ref=reference(OLD/'plan.json'))
        self.phase=load(phase_plan);self.allowed={'v179:'+c['case_id'] for c in self.phase['cases']}
        data=canonical({'plan':phase_plan,'authority':authority,'cumulative_cap_CNY':250,'old_rows_retained':True})
        with self.transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS phase_authorizations_v177(phase TEXT PRIMARY KEY,body TEXT NOT NULL)')
            prior=db.execute('SELECT body FROM phase_authorizations_v177 WHERE phase=?',('v179-recovery-reader-validation-r1',)).fetchone()
            if prior and prior[0]!=data:raise ValueError('Phase authority changed')
            db.execute('INSERT OR IGNORE INTO phase_authorizations_v177 VALUES(?,?)',('v179-recovery-reader-validation-r1',data))

    def admit(self,job_id,kind,*,job_cap=7_000_000_000):
        if job_id not in self.allowed or kind!='v179-recovery-probe' or job_cap!=7_000_000_000:
            raise ValueError('Only the frozen independent diagnostic cases are admitted')
        return super().admit(job_id,kind,job_cap=job_cap)

    def reserve(self,job_id,request_id,purpose,step,attempt,payload):
        if job_id not in self.allowed or purpose!='recovery' or not 0<=step<MAX_DECISIONS or payload['max_tokens']!=4096:
            raise ValueError('Read-only physical scope exceeded')
        return super().reserve(job_id,request_id,purpose,step,attempt,payload)
