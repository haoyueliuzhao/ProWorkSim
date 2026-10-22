"""Read-only acceptance of the already-applied r4 migration after its control incident.

Never executes migration, clears a ledger flag, or changes queue/model state.
The missing independent pre-migration backup/hash remains an explicit limitation.
"""
from __future__ import annotations
import argparse
import fcntl
import json
from pathlib import Path
import sqlite3

from proworksim import software_benchmark_deepseek_api_v055 as old
from proworksim import software_benchmark_deepseek_api_v055_r4 as new
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_queue_v055 import ROOT, load, now
from tools.resume_deepseek_queue_after_reconciliation_v055_r1 import readonly_ledger_fingerprint, inactive_coordinator

RUN = ROOT / 'runs/software-benchmark-v055'
QUEUE = RUN / 'queue-r1'
LEDGER = RUN / 'budget-r1/ledger.sqlite3'
UNIT = 'proworksim-v055-deepseek-six-conditions-native-host-r7.service'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    audit_ref = reference(RUN / 'usage-bound-halt-audit-r1/audit.json')
    incident_ref = reference(RUN / 'budget-migration-incident-r1/incident-observation.json')
    quiet_ref = reference(RUN / 'queue-resume-quiescence-r1/receipt.json')
    qualification_ref = reference(RUN / 'budget-policy-control-r4-isolated/receipt.json')
    audit, quiet, qualification = load(audit_ref), load(quiet_ref), load(qualification_ref)
    if not qualification.get('passed') or qualification.get('actual_experiment_ledger_mutations') != 0:
        raise ValueError('Corrected isolated control is not qualified')
    directory = args.output.resolve().parent
    if not directory.is_relative_to(RUN):
        raise ValueError('Receipt must stay in its independent v055 evidence root')
    with (QUEUE / 'coordinator.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        inactive_coordinator(UNIT)
        state_ref = reference(QUEUE / 'state.json')
        if state_ref != quiet['queue_state'] or not quiet['all_registered_scopes_inactive']:
            raise ValueError('Previously observed drained boundary changed')
        with sqlite3.connect(LEDGER.as_uri() + '?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            totals = [dict(row) for row in db.execute('''SELECT status,COUNT(*) request_count,
                SUM(reserved_nanoyuan) reserved_nanoyuan,SUM(settled_nanoyuan) settled_nanoyuan
                FROM requests GROUP BY status ORDER BY status''')]
            if totals != audit['totals']:
                raise ValueError('Historical audit accounting changed')
            for row in audit['violating_rows']:
                actual = db.execute('SELECT * FROM requests WHERE request_id=?', (row['request_id'],)).fetchone()
                if actual is None or dict(actual) != row:
                    raise ValueError('Historical violating request changed')
            policy = db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()[0]
            if policy != new.policy_text():
                raise ValueError('Current accounting policy differs from reviewed implementation')
            for table in ('response_observations', 'provider_protocol_events'):
                if db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] != 0:
                    raise ValueError('A new API response exists before acceptance')
            uncertain = {r['request_id']: dict(r) for r in db.execute("SELECT * FROM requests WHERE status='uncertain'")}
            adjustments = [dict(r) for r in db.execute('SELECT * FROM budget_adjustments')]
            if len(uncertain) != 2 or len(adjustments) != 2:
                raise ValueError('Unexpected historical hold inventory')
            for adjustment in adjustments:
                prior = uncertain[adjustment['request_id']]
                if adjustment['amount_nanoyuan'] != new.ABSOLUTE_RESERVATION_NANOYUAN - prior['reserved_nanoyuan']:
                    raise ValueError('Historical hold does not reach the reviewed absolute bound')
            migrations = [dict(r) for r in db.execute('SELECT * FROM budget_policy_migrations')]
            if (len(migrations) != 1 or migrations[0]['previous_policy_json'] != old._json({**old.POLICY, 'max_concurrency': 64})
                    or migrations[0]['new_policy_json'] != policy or migrations[0]['previous_halt'] != audit['halted']):
                raise ValueError('Original halt or policy history was not preserved')
        fingerprint = readonly_ledger_fingerprint(LEDGER)
        if (fingerprint['requests_sha256'] != '3857188de594171c0e000e73ae05dc101dace2506d1d5e0cd07696f42658af60'
                or fingerprint['committed_nanoyuan'] != 134286501360 or fingerprint['adjustments_nanoyuan'] != 6258688000
                or fingerprint['halted'] is not None or fingerprint['inflight_count'] != 0
                or fingerprint['cap_nanoyuan'] != 2000 * 10**9 or fingerprint['max_concurrency'] != 64):
            raise ValueError('Read-only incident accounting invariants changed')
        directory.mkdir(parents=True, exist_ok=False)
        acceptance = write_new(args.output, {
            'version': 'v055-post-incident-readonly-budget-acceptance-r1', 'accepted_utc': now(),
            'source': reference(__file__), 'audit': audit_ref, 'incident': incident_ref,
            'corrected_isolated_qualification': qualification_ref, 'quiescence': quiet_ref,
            'executed_migration_source': reference(RUN / 'budget-migration-incident-r1/executed-migration-tool.py'),
            'post_incident_backup': reference(RUN / 'budget-migration-incident-r1/post-incident-ledger.sqlite3'),
            'ledger_after': fingerprint, 'integrity_restored': True, 'queue_resume_authorized': True,
            'basis': ['historical_request_aggregate_and_complete_violating_row_equal_independent_prior_audit',
                      'reviewed_executed_migration_SQL_has_no_request_row_mutation',
                      'executed_transaction_asserted_before_after_request_hash_equal_before_commit',
                      'current_all_table_snapshot_and_supplemental_holds_checked',
                      'old_queue_drained_and_no_new_API_response_since_migration'],
            'independent_pre_migration_full_request_hash_available': False,
            'pre_migration_backup_and_fixture_receipt_lost': True,
            'lost_usage_not_reconstructed': True, 'budget_cap_cny': 2000,
            'ledger_writes': 0, 'queue_writes': 0, 'model_calls': 0, 'slot_replays': 0})
        authorization = write_new(directory / 'queue-authorization.json', {
            'version': 'v055-queue-resume-after-reconciliation-r1', 'created_utc': now(),
            'queue_resume_authorized': True, 'ledger_integrity_restored': True,
            'all_financial_components_accounted': True, 'ledger_after': fingerprint,
            'committed_nanoyuan': fingerprint['committed_nanoyuan'], 'can_admit_minimum_request': True,
            'previous_coordinator_unit': UNIT, 'queue_state_before': state_ref,
            'legal_reconciliation_receipt': acceptance})
        print(json.dumps({'acceptance': acceptance, 'queue_authorization': authorization}))


if __name__ == '__main__':
    main()
