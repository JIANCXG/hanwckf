#!/usr/bin/env python3
"""Pin upstream feeds and remember only firmware builds that were published."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / '.github/ax3000t-passwall-last-success.json'
FEEDS = {
    'passwall_luci': 'https://github.com/Openwrt-Passwall/openwrt-passwall.git',
    'passwall_packages': 'https://github.com/Openwrt-Passwall/openwrt-passwall-packages.git',
}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def pin_feeds(text, revisions):
    for name, url in FEEDS.items():
        sha = revisions[name]
        if not re.fullmatch(r'[0-9a-f]{40}', sha):
            raise ValueError(f'Invalid upstream revision for {name}')
        pattern = rf'^src-git\s+{name}\s+{re.escape(url)}(?:[;^][^\s]+)?\s*$'
        text, count = re.subn(pattern, f'src-git {name} {url}^{sha}', text, flags=re.M)
        if count != 1:
            raise ValueError(f'Expected exactly one {name} feed, found {count}')
    return text


def fingerprint(feeds):
    # State-only and feed-pin commits must not cause an endless rebuild loop.
    tree = git('ls-tree', '-r', 'HEAD').splitlines()
    excluded = {'feeds.conf.default', STATE.relative_to(ROOT).as_posix()}
    tree = [line for line in tree if line.split('\t', 1)[1] not in excluded]
    return hashlib.sha256(('\n'.join(tree) + '\n' + feeds).encode()).hexdigest()


def output(values):
    for name, value in values.items():
        print(f'{name}={value}')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
            for name, value in values.items():
                stream.write(f'{name}={value}\n')


def check(force=False):
    revisions = {}
    for name, url in FEEDS.items():
        lines = git('ls-remote', '--exit-code', url, 'HEAD').splitlines()
        if len(lines) != 1:
            raise ValueError(f'Could not resolve upstream HEAD for {name}')
        revisions[name] = lines[0].split()[0]
    path = ROOT / 'feeds.conf.default'
    original = path.read_text(encoding='utf-8')
    pinned = pin_feeds(original, revisions)
    digest = fingerprint(pinned)
    previous = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {}
    should_build = force or previous.get('fingerprint') != digest
    if pinned != original:
        path.write_text(pinned, encoding='utf-8', newline='\n')
    output({
        'should_build': str(should_build).lower(),
        'fingerprint': digest,
        **revisions,
    })


def success(args):
    values = {
        'fingerprint': args.fingerprint,
        'passwall_luci': args.passwall_luci,
        'passwall_packages': args.passwall_packages,
        'source_commit': args.source_commit,
        'run_url': args.run_url,
        'release_tag': args.release_tag,
    }
    if not re.fullmatch(r'[0-9a-f]{64}', values['fingerprint']):
        raise ValueError('Invalid build fingerprint')
    for name in ('passwall_luci', 'passwall_packages', 'source_commit'):
        if not re.fullmatch(r'[0-9a-f]{40}', values[name]):
            raise ValueError(f'Invalid revision for {name}')
    STATE.write_text(json.dumps(values, indent=2) + '\n', encoding='utf-8', newline='\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    checker = commands.add_parser('check')
    checker.add_argument('--force', action='store_true')
    recorder = commands.add_parser('success')
    for option in ('fingerprint', 'passwall-luci', 'passwall-packages',
                   'source-commit', 'run-url', 'release-tag'):
        recorder.add_argument('--' + option, required=True)
    args = parser.parse_args()
    if args.command == 'check':
        check(args.force)
    else:
        success(args)
