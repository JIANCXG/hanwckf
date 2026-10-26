#!/usr/bin/env python3
"""Pin upstream feeds and remember only firmware builds that were published."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / '.github/ax3000t-passwall-last-success.json'
CHECK_STATE = '.github/ax3000t-passwall-last-check.json'
FEEDS = {
    'passwall_luci': 'https://github.com/Openwrt-Passwall/openwrt-passwall.git',
    'passwall_packages': 'https://github.com/Openwrt-Passwall/openwrt-passwall-packages.git',
    'packages': 'https://github.com/immortalwrt/packages.git',
    'luci': 'https://github.com/immortalwrt/luci.git',
    'routing': 'https://github.com/openwrt/routing.git',
    'telephony': 'https://github.com/openwrt/telephony.git',
}
BRANCHES = {name: ('main' if name.startswith('passwall_') else 'openwrt-21.02')
            for name in FEEDS}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def pin_feeds(text, revisions):
    for name, url in FEEDS.items():
        sha = revisions[name]
        if not re.fullmatch(r'[0-9a-f]{40}', sha):
            raise ValueError(f'Invalid upstream revision for {name}')
        pattern = rf'^src-git[ \t]+{name}[ \t]+{re.escape(url)}(?:[;^][^\s]+)?[ \t]*$'
        text, count = re.subn(pattern, f'src-git {name} {url}^{sha}', text, flags=re.M)
        if count != 1:
            raise ValueError(f'Expected exactly one {name} feed, found {count}')
    return text


def fingerprint(feeds):
    # State-only and feed-pin commits must not cause an endless rebuild loop.
    tree = git('ls-tree', '-r', 'HEAD').splitlines()
    excluded = {'feeds.conf.default', STATE.relative_to(ROOT).as_posix(), CHECK_STATE}
    tree = [line for line in tree if line.split('\t', 1)[1] not in excluded]
    return hashlib.sha256(('\n'.join(tree) + '\n' + feeds).encode()).hexdigest()


def output(values):
    for name, value in values.items():
        print(f'{name}={value}')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
            for name, value in values.items():
                stream.write(f'{name}={value}\n')


def check(force=False, scheduled=False, now=None):
    now = now or datetime.now(timezone.utc)
    check_state = ROOT / CHECK_STATE
    if scheduled and not force and check_state.exists():
        last_check = datetime.fromisoformat(json.loads(check_state.read_text(encoding='utf-8'))['checked_at'])
        if now - last_check < timedelta(hours=72):
            output({'should_build': 'false', 'checked': 'false'})
            return
    revisions = {}
    for name, url in FEEDS.items():
        ref = f'refs/heads/{BRANCHES[name]}'
        lines = git('ls-remote', '--exit-code', url, ref).splitlines()
        if len(lines) != 1:
            raise ValueError(f'Could not resolve {ref} for {name}')
        revisions[name] = lines[0].split()[0]
    path = ROOT / 'feeds.conf.default'
    original = path.read_text(encoding='utf-8')
    pinned = pin_feeds(original, revisions)
    digest = fingerprint(pinned)
    previous = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {}
    should_build = force or previous.get('fingerprint') != digest
    if pinned != original:
        path.write_text(pinned, encoding='utf-8', newline='\n')
    # Failed upstream queries do not advance the clock; retry on the next wake-up.
    check_state.write_text(json.dumps({'checked_at': now.isoformat(timespec='seconds')}, indent=2) + '\n',
                           encoding='utf-8', newline='\n')
    output({
        'should_build': str(should_build).lower(),
        'checked': 'true',
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
    checker.add_argument('--scheduled', action='store_true', help='Skip upstream queries within 72 hours')
    recorder = commands.add_parser('success')
    for option in ('fingerprint', 'passwall-luci', 'passwall-packages',
                   'source-commit', 'run-url', 'release-tag'):
        recorder.add_argument('--' + option, required=True)
    args = parser.parse_args()
    if args.command == 'check':
        check(args.force, args.scheduled)
    else:
        success(args)
