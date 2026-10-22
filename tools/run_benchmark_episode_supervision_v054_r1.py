"""Wrap only a future episode's host supervisor; preserve its original runner."""
from __future__ import annotations

import argparse
from pathlib import Path
import runpy
import sys

import supervision_proc_exit_overlay_v054_r1 as overlay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--overlay', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--source', choices=sorted(overlay.ROOTS), required=True)
    parser.add_argument('episode_args', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.episode_args or args.episode_args[0] != '--':
        raise ValueError('Original episode argv requires an explicit separator')
    ref = overlay.reference(args.overlay)
    if ref['sha256'] != args.sha256:
        raise ValueError('Future worker supervision SHA differs')
    value = overlay.install_parent(ref, args.source)
    entry = value['sources'][args.source]['entry']['path']
    sys.argv = [entry, *args.episode_args[1:]]
    runpy.run_path(entry, run_name='__main__')


if __name__ == '__main__':
    main()
