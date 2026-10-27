#!/usr/bin/env python3
"""Connect the installed personal skill directory to Git without overwriting skills."""
import argparse
import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

DEFAULT_REPO = 'https://github.com/benitezhm/codex-skills.git'
START = '<!-- codex-skills-repository:start -->'
END = '<!-- codex-skills-repository:end -->'


def git(*args):
    return subprocess.run(['git', *map(str, args)], check=True, capture_output=True, text=True).stdout.strip()


def digest(path):
    return hashlib.sha256(path.read_bytes()).digest()


def remote_identity(url):
    return url.removeprefix('git@github.com:').removeprefix('https://github.com/').removesuffix('.git').rstrip('/')


def connect(repo, target):
    if target.is_symlink():
        raise ValueError('Target is a symlink; inspect it manually rather than replacing it')
    if (target / '.git').exists():
        if Path(git('-C', target, 'rev-parse', '--show-toplevel')).resolve() != target:
            raise ValueError('Target is not the repository root')
        if remote_identity(git('-C', target, 'remote', 'get-url', 'origin')) != remote_identity(repo):
            raise ValueError('Existing checkout has a different remote; no files changed')
        print(f'Already connected: {target}; existing changes preserved')
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='codex-skills-connect-', dir=target.parent) as temp:
        clone = Path(temp) / 'checkout'
        git('clone', '--', repo, clone)
        # Preflight every overlapping tracked path before copying anything.
        names = git('-C', clone, 'ls-files', '-z').split('\0')
        tracked = [Path(n) for n in names if n]
        for rel in tracked:
            dest = target / rel
            if any(p.is_symlink() for p in [dest, *dest.parents] if p != p.parent):
                raise ValueError(f'Symlink in destination path: {rel}; no installed files changed')
            if dest.exists() and (not dest.is_file() or digest(dest) != digest(clone / rel)):
                raise ValueError(f'Existing file differs: {rel}; no installed files changed. Review/back up that difference first.')
            for parent in dest.parents:
                if parent == target.parent:
                    break
                if parent.exists() and not parent.is_dir():
                    raise ValueError(f'Non-directory parent for {rel}; no installed files changed')
        target.mkdir(exist_ok=True)
        for rel in tracked:
            dest = target / rel
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(clone / rel, dest)
        # Git's normal clone metadata is portable; objects stay with the installed checkout.
        shutil.move(str(clone / '.git'), str(target / '.git'))
    print(f'Connected {target} to {repo}')
    status = git('-C', target, 'status', '--short')
    if status:
        print('Preserved local/untracked files:\n' + status)


def preference(target, codex_home):
    codex_home.mkdir(parents=True, exist_ok=True)
    override = codex_home / 'AGENTS.override.md'
    path = override if override.exists() and override.read_text().strip() else codex_home / 'AGENTS.md'
    if path.is_symlink():
        raise ValueError('Global instruction file is a symlink; update it manually')
    original = path.read_text() if path.exists() else ''
    block = f'''{START}
## Personal skills repository

- For new or updated reusable personal skills, work in `{target}`, the checkout
  of https://github.com/benitezhm/codex-skills, unless I request another location.
- Read its AGENTS.md. Keep private/project-specific content outside this public
  repository; inspect changes before committing and push only when authorized.
{END}'''
    if START in original or END in original:
        if original.count(START) != 1 or original.count(END) != 1 or original.index(START) > original.index(END):
            raise ValueError('Malformed existing managed preference block; update manually')
        text = original[:original.index(START)] + block + original[original.index(END)+len(END):]
    else:
        text = original.rstrip() + ('\n\n' if original.strip() else '') + block + '\n'
    if text != original:
        if path.exists():
            backup = path.with_name(path.name + '.before-codex-skills')
            if not backup.exists():
                shutil.copy2(path, backup)
        path.write_text(text)
    print(f'Personal-skill preference saved in {path}; unrelated instructions preserved')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default=DEFAULT_REPO)
    parser.add_argument('--target', type=Path, default=Path.home()/'.agents/skills')
    parser.add_argument('--register-preference', action='store_true',
                        help='Add a small managed preference block to the active global Codex AGENTS file')
    parser.add_argument('--codex-home', type=Path,
                        default=Path(os.environ.get('CODEX_HOME') or Path.home()/'.codex'))
    args = parser.parse_args()
    target = args.target.expanduser().absolute()
    connect(args.repo, target)
    if args.register_preference:
        preference(target, args.codex_home.expanduser())


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'Connection stopped: {error}')
