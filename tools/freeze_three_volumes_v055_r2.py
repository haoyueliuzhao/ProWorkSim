"""Seal already mounted source volumes; never create or mount their directories."""
import argparse
import json
from pathlib import Path

from proworksim import software_benchmark_disk_volumes_v055_r2 as volumes
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--secondary', type=Path, required=True)
    parser.add_argument('--tertiary', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(volumes.ROOT / 'runs/software-benchmark-v055'):
        raise ValueError('Volume manifest must remain in the current experiment root')
    value = {'version': volumes.MANIFEST_VERSION, 'created_utc': volumes.now(),
        'helper_source': reference(volumes.__file__),
        'secondary_registration': reference(args.secondary),
        'tertiary_registration': reference(args.tertiary),
        'all_three_devices_must_differ': True, 'mount_loss_fallback': False,
        'inflight_directories_moved': False, 'model_calls': 0, 'formal_claims': 0,
        'volume_policy': volumes.VOLUME_POLICY}
    identities = volumes._live_identity(value)
    output.parent.mkdir(parents=True, exist_ok=True)
    ref = write_new(output, value)
    print(json.dumps({'reference': ref, 'identity': identities}))


if __name__ == '__main__':
    main()
