"""Deterministic relocation of the frozen offline content tokenizer only."""
from __future__ import annotations

import copy
import json
from pathlib import Path, PurePosixPath

from .storage import digest, json_bytes

VERSION = 'v141-relocated-official-content-tokenizer-r1'
ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json'
PREFIX = '/opt/pws-runtime/content-tokenizer'


def manifest_bytes(prefix=PREFIX):
    raw = SOURCE.read_bytes()
    source = json.loads(raw)
    value = {key: source[key] for key in ('version', 'recipe_version', 'tokenizer_model')}
    overlay = Path(source['overlay_path'])
    value.update(overlay_path=prefix+'/overlay', relocated_from_sha256=digest(raw),
                 relocation_version=VERSION)
    value['installed_files'] = []
    for reference in source['installed_files']:
        relative = Path(reference['path']).relative_to(overlay)
        value['installed_files'].append({**copy.deepcopy(reference),
            'path': prefix+'/overlay/'+relative.as_posix()})
    value['tokenizer_files'] = [{**copy.deepcopy(reference),
        'path': prefix+'/tokenizer/'+Path(reference['path']).name}
        for reference in source['tokenizer_files']]
    return json_bytes(value)


def descriptor():
    raw = manifest_bytes()
    value = json.loads(raw)
    vocabulary = next(row for row in value['tokenizer_files'] if Path(row['path']).name == 'tokenizer.json')
    return {'version': VERSION, 'manifest': {'path': PREFIX+'/manifest.json',
            'sha256': digest(raw), 'bytes': len(raw)},
        'source_manifest_sha256': value['relocated_from_sha256'],
        'vocabulary_sha256': vocabulary['sha256'], 'require_content_counter': True,
        'content_tokens_are_provider_billing': False}


def validate_descriptor(value):
    import re
    if (not isinstance(value, dict) or set(value) != {'version', 'manifest',
            'source_manifest_sha256', 'vocabulary_sha256', 'require_content_counter',
            'content_tokens_are_provider_billing'} or value['version'] != VERSION
            or value['require_content_counter'] is not True
            or value['content_tokens_are_provider_billing'] is not False):
        raise ValueError('An exact local content-tokenizer descriptor is required')
    reference = value['manifest']
    if (not isinstance(reference, dict) or set(reference) != {'path', 'sha256', 'bytes'}
            or PurePosixPath(reference['path']) != PurePosixPath(PREFIX+'/manifest.json')
            or type(reference['bytes']) is not int or not 0 < reference['bytes'] <= 65536
            or any(not isinstance(item, str) or re.fullmatch('[0-9a-f]{64}', item) is None
                   for item in (reference['sha256'], value['source_manifest_sha256'], value['vocabulary_sha256']))):
        raise ValueError('Content-tokenizer source or deployment identity changed')
    return copy.deepcopy(value)


def load_counter(value):
    from .software_collaboration_observation_v141 import load_official_content_counter
    value = validate_descriptor(value)
    reference = value['manifest']
    raw = Path(reference['path']).read_bytes()
    if len(raw) != reference['bytes'] or digest(raw) != reference['sha256']:
        raise ValueError('The deployed content-tokenizer manifest bytes changed')
    manifest = json.loads(raw)
    if manifest.get('relocated_from_sha256') != value['source_manifest_sha256']:
        raise ValueError('The relocated tokenizer lost its original manifest identity')
    counter, metadata = load_official_content_counter(reference['path'], manifest_sha256=reference['sha256'])
    if metadata['vocabulary_sha256'] != value['vocabulary_sha256']:
        raise ValueError('Content counting changed the frozen vocabulary')
    return counter, metadata
