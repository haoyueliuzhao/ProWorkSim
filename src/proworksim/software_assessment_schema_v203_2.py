"""Independent dependency, misalignment and intervention judgments; no detector."""
DEPENDENCY_TYPES=('Code Dependency','Artifact Dependency','Task Prerequisite','Validation Dependency','Resource Dependency','Coordination Dependency')
MISALIGNMENT_TYPES=('Dependency Misalignment','Ownership Conflict','Responsibility Gap','Coordination Bottleneck','Validation Misalignment')
DECISIONS=('NO_CHANGE','ABSTAIN','INTERVENE')

def validate_assessment(row):
    for field in ('dependency','misalignment'):
        if row.get(field) not in {'PRESENT','ABSENT','UNKNOWN'}:raise ValueError('Each scientific judgment needs its own label')
    if row.get('decision') not in DECISIONS:raise ValueError('No-Change and Abstain are separate decisions')
    if any(t not in DEPENDENCY_TYPES for t in row.get('dependency_types',[])):raise ValueError('Unknown dependency type')
    if any(t not in MISALIGNMENT_TYPES for t in row.get('misalignment_types',[])):raise ValueError('Unknown misalignment type')
    if row['decision']!='ABSTAIN' and not row.get('decision_evidence'):raise ValueError('A substantive decision needs scoped source evidence')
    if row['decision']=='INTERVENE' and (row['misalignment']!='PRESENT' or not row.get('intervention_types')):raise ValueError('Dependency alone cannot authorize an organizational intervention')
    return {'schema_valid':True,'semantic_truth_not_verified':True,'world_actions':0,'unknowns_must_not_be_counted_as_negatives':True}
