"""Research split/provenance registry, never supplied to an acting role."""

from pathlib import Path

from .storage import digest, json_bytes

FIELDS = {
    'scenario_id', 'source_cluster_id', 'world_family_id', 'base_project_id',
    'information_layout_id', 'split', 'generator_version', 'validator_version',
    'template_family_id', 'scenario_file', 'scenario_sha256',
}


def validate_registry(registry, *, root=None):
    if registry.get('version') != 'situation-registry-v0.12':
        raise ValueError('Unknown research registry version')
    sources = registry.get('sources', {})
    rows = registry.get('situations', [])
    if not isinstance(sources, dict) or not sources or not isinstance(rows, list) or not rows:
        raise ValueError('Explicit sources and nonempty situation inventory required')
    ids, cluster_splits, family_splits = set(), {}, {}
    for row in rows:
        if set(row) != FIELDS or any(not isinstance(row[k], str) or not row[k] for k in FIELDS):
            raise ValueError('Situation requires all declared provenance fields')
        if row['scenario_id'] in ids:
            raise ValueError('Duplicate exact situation identity')
        ids.add(row['scenario_id'])
        if row['source_cluster_id'] not in sources:
            raise ValueError('Situation source cluster not registered')
        if row['split'] not in {'development', 'policy_train', 'outer_development', 'independent_test'}:
            raise ValueError('Unknown declared data use')
        for mapping, field in [(cluster_splits, 'source_cluster_id'), (family_splits, 'world_family_id')]:
            old = mapping.setdefault(row[field], row['split'])
            if old != row['split']:
                raise ValueError('Source/world-family derivatives cannot cross data-use splits')
        if root is not None:
            base = Path(root).resolve()
            path = (base / row['scenario_file']).resolve()
            if not path.is_relative_to(base) or digest(path.read_bytes()) != row['scenario_sha256']:
                raise ValueError('Scenario file differs from the frozen registry')
    return {'sources': len(cluster_splits), 'world_families': len(family_splits),
            'exact_situations': len(ids), 'splits': sorted(set(cluster_splits.values())),
            'registry_sha256': digest(json_bytes(registry))}


def situation_fingerprint(row):
    if set(row) != FIELDS:
        raise ValueError('Complete situation registry row required')
    return digest(json_bytes(row))
