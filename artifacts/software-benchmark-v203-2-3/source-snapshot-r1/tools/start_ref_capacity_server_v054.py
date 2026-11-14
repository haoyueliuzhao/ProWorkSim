"""Inject a private local API key after entering the trusted REF runtime."""
import argparse
import os
from pathlib import Path
import runpy
import stat
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-key-file", required=True, type=Path)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    descriptor = os.open(args.api_key_file, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor) as stream:
        info = os.fstat(stream.fileno())
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("REF local API key must be owner-only 0600")
        key = stream.read().strip()
    if len(key) < 32 or "\n" in key:
        raise ValueError("Invalid private preparation API key")
    os.environ["VLLM_API_KEY"] = key
    arguments = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
    sys.argv = ["vllm", *arguments]
    runpy.run_module("vllm.entrypoints.cli.main", run_name="__main__")


if __name__ == "__main__":
    main()
