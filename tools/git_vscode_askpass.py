#!/usr/bin/env python3
"""Use this terminal's existing VS Code Git authentication, without storing tokens."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from urllib.parse import urlsplit


def owned_socket(path: Path, directory: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    return (path.parent == directory and stat.S_ISSOCK(info.st_mode)
            and info.st_uid == os.getuid())


def locate_session() -> dict[str, str]:
    directory = Path('/run/user') / str(os.getuid())
    hook = Path(os.environ.get('VSCODE_IPC_HOOK_CLI', ''))
    if not hook.name.startswith('vscode-ipc-') or not owned_socket(hook, directory):
        raise RuntimeError('Open this repository in the authenticated VS Code remote session first.')
    result = subprocess.run(['ss', '-xlpH'], check=True, capture_output=True,
                            text=True, timeout=5)
    lines = result.stdout.splitlines()
    owners = {pid for line in lines if str(hook) in line.split()
              for pid in re.findall(r'\bpid=(\d+)', line)}
    if len(owners) != 1:
        raise RuntimeError('Cannot identify the current VS Code session; no other session will be selected.')
    pid = owners.pop()
    process = Path('/proc') / pid
    if process.stat().st_uid != os.getuid():
        raise RuntimeError('The VS Code session belongs to a different user.')
    sockets = {Path(word) for line in lines
               if re.search(r'\bpid=' + pid + r'[,)]', line)
               for word in line.split()
               if word.startswith(str(directory / 'vscode-git-'))}
    sockets = {path for path in sockets if owned_socket(path, directory)}
    if len(sockets) != 1:
        raise RuntimeError('The current VS Code Git authentication socket is unavailable or ambiguous.')
    node = (process / 'exe').resolve(strict=True)
    scripts = node.parent / 'extensions/git/dist'
    shell, main = scripts / 'askpass.sh', scripts / 'askpass-main.js'
    if node.name != 'node' or not shell.is_file() or not main.is_file():
        raise RuntimeError('The current VS Code Git authentication programs were not found.')
    return {'node': str(node), 'askpass': str(shell), 'main': str(main),
            'socket': str(sockets.pop())}


def main() -> int:
    args = sys.argv[1:]
    if args != ['--check']:
        urls = re.findall(r"https://[^'\s]+", args[0]) if len(args) == 1 else []
        if len(urls) != 1 or urlsplit(urls[0]).hostname != 'github.com':
            raise RuntimeError('This repository helper accepts only GitHub HTTPS credential prompts.')
    session = locate_session()
    if args == ['--check']:
        print(json.dumps({'available': True, **session,
                          'credential_requests': 0, 'credentials_stored': False}))
        return 0
    environment = {**os.environ,
        'VSCODE_GIT_ASKPASS_NODE': session['node'],
        'VSCODE_GIT_ASKPASS_MAIN': session['main'],
        'VSCODE_GIT_ASKPASS_EXTRA_ARGS': '',
        'VSCODE_GIT_IPC_HANDLE': session['socket']}
    # stdout belongs exclusively to Git's credential exchange. Never log it.
    os.execve('/bin/sh', ['/bin/sh', session['askpass'], *args], environment)
    return 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print('VS Code Git authentication: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
