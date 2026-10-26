import contextlib
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

CI = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('updater', CI / 'passwall-update.py')
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)
DEVICES = ('xiaomi_mi-router-ax3000t', 'xiaomi_mi-router-ax3000t-stock',
           'xiaomi_mi-router-ax3000t-an8855', 'xiaomi_mi-router-ax3000t-an8855-stock')


class UpdateTests(unittest.TestCase):
    def test_pinning_and_missing_feed(self):
        text = ''.join(f'src-git {name} {url}^' + '0' * 40 + '\n'
                       for name, url in updater.FEEDS.items())
        revisions = {name: 'a' * 40 for name in updater.FEEDS}
        updated = updater.pin_feeds(text, revisions)
        self.assertEqual(updated.count('a' * 40), len(updater.FEEDS))
        self.assertEqual(updater.pin_feeds(updated, revisions), updated)
        with self.assertRaises(ValueError):
            updater.pin_feeds('', revisions)

    def test_success_state_only_skips_exact_success_and_failure_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / '.github/state.json'
            state.parent.mkdir()
            feeds = ''.join(f'src-git {name} {url}^' + '0' * 40 + '\n'
                            for name, url in updater.FEEDS.items())
            (root / 'feeds.conf.default').write_text(feeds)

            def fake_git(*args):
                if args[0] == 'ls-remote':
                    return 'a' * 40 + '\tHEAD'
                return '100644 blob ' + 'b' * 40 + '\tsource.c'

            def check():
                result = io.StringIO()
                with contextlib.redirect_stdout(result):
                    updater.check()
                return dict(line.split('=', 1) for line in result.getvalue().splitlines())

            with patch.object(updater, 'ROOT', root), patch.object(updater, 'STATE', state), \
                    patch.object(updater, 'git', side_effect=fake_git), \
                    patch.dict(os.environ, {'GITHUB_OUTPUT': ''}):
                first = check()
                self.assertEqual(first['should_build'], 'true')
                self.assertEqual(check()['should_build'], 'true')  # failed build has no state
                state.write_text(json.dumps({'fingerprint': first['fingerprint']}))
                self.assertEqual(check()['should_build'], 'false')
                (root / 'feeds.conf.default').write_text(feeds + '# another feed\n')
                self.assertEqual(check()['should_build'], 'true')

    def test_state_and_pin_commits_do_not_change_fingerprint(self):
        lines = ['100644 blob aaa\tfile.c', '100644 blob bbb\tfeeds.conf.default',
                 '100644 blob ccc\t.github/ax3000t-passwall-last-success.json',
                 '100644 blob fff\t.github/ax3000t-passwall-last-check.json']
        with patch.object(updater, 'git', return_value='\n'.join(lines)):
            first = updater.fingerprint('effective feeds\n')
        lines[1] = '100644 blob ddd\tfeeds.conf.default'
        lines[2] = '100644 blob eee\t.github/ax3000t-passwall-last-success.json'
        lines[3] = '100644 blob 999\t.github/ax3000t-passwall-last-check.json'
        with patch.object(updater, 'git', return_value='\n'.join(lines)):
            self.assertEqual(first, updater.fingerprint('effective feeds\n'))

    def test_72_hour_gate_and_manual_bypass(self):
        now = datetime(2026, 11, 1, 4, 17, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.github').mkdir()
            clock = root / updater.CHECK_STATE
            feeds = ''.join(f'src-git {name} {url}^' + 'a' * 40 + '\n'
                            for name, url in updater.FEEDS.items())
            (root / 'feeds.conf.default').write_text(feeds)
            for elapsed, scheduled, force, expected in (
                    (71, True, False, False), (72, True, False, True),
                    (1, False, False, True), (1, True, True, True)):
                clock.write_text(json.dumps({'checked_at': (now-timedelta(hours=elapsed)).isoformat()}))
                with patch.object(updater, 'ROOT', root), \
                        patch.object(updater, 'STATE', root / '.github/success.json'), \
                        patch.object(updater, 'git', return_value='a'*40+'\tHEAD') as git_mock, \
                        patch.object(updater, 'fingerprint', return_value='b'*64), \
                        patch.object(updater, 'output') as out:
                    updater.check(force=force, scheduled=scheduled, now=now)
                    self.assertEqual(git_mock.call_count, len(updater.FEEDS) if expected else 0)
                    self.assertEqual(out.call_args.args[0]['checked'], str(expected).lower())
                    if expected:
                        self.assertEqual(json.loads(clock.read_text())['checked_at'], now.isoformat(timespec='seconds'))

    def test_failed_query_keeps_check_time_and_feeds(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.github').mkdir()
            clock = root / updater.CHECK_STATE
            clock.write_text('{"checked_at": "2026-10-01T00:00:00+00:00"}\n')
            (root / 'feeds.conf.default').write_text('original feeds\n')
            before = clock.read_bytes()
            with patch.object(updater, 'ROOT', root), \
                    patch.object(updater, 'git', side_effect=['a'*40+'\tHEAD', RuntimeError('offline')]):
                with self.assertRaises(RuntimeError):
                    updater.check(scheduled=True)
            self.assertEqual(clock.read_bytes(), before)
            self.assertEqual((root / 'feeds.conf.default').read_text(), 'original feeds\n')

    def test_each_base_feed_change_triggers_build_and_uses_21_02_branch(self):
        for changed in ('packages', 'luci', 'routing', 'telephony'):
            with self.subTest(feed=changed), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / '.github').mkdir()
                state = root / '.github/success.json'
                feeds = ''.join(f'src-git {name} {url}^' + 'a' * 40 + '\n'
                                for name, url in updater.FEEDS.items())
                (root / 'feeds.conf.default').write_text(feeds)
                def fake_git(*args):
                    if args[0] == 'ls-remote':
                        name = next(name for name, url in updater.FEEDS.items() if url == args[2])
                        self.assertEqual(args[3], 'refs/heads/' + updater.BRANCHES[name])
                        return ('b' if name == changed else 'a') * 40 + '\t' + args[3]
                    return '100644 blob ' + 'c' * 40 + '\tsource.c'
                with patch.object(updater, 'ROOT', root), patch.object(updater, 'STATE', state), \
                        patch.object(updater, 'git', side_effect=fake_git), patch.object(updater, 'output') as out:
                    state.write_text(json.dumps({'fingerprint': updater.fingerprint(feeds)}))
                    updater.check()
                    result = out.call_args.args[0]
                    self.assertEqual(result['should_build'], 'true')
                    self.assertEqual(result[changed], 'b' * 40)
                    state.write_text(json.dumps({'fingerprint': result['fingerprint']}))
                    updater.check()
                    self.assertEqual(out.call_args.args[0]['should_build'], 'false')

    def test_last_feed_failure_does_not_save_partial_update(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.github').mkdir()
            clock = root / updater.CHECK_STATE
            clock.write_text('{"checked_at": "2026-10-01T00:00:00+00:00"}\n')
            feeds = root / 'feeds.conf.default'
            feeds.write_text('original feeds\n')
            before = clock.read_bytes(), feeds.read_bytes()
            responses = ['a' * 40 + '\tHEAD'] * (len(updater.FEEDS) - 1) + [RuntimeError('offline')]
            with patch.object(updater, 'ROOT', root), patch.object(updater, 'git', side_effect=responses):
                with self.assertRaises(RuntimeError):
                    updater.check()
            self.assertEqual(before, (clock.read_bytes(), feeds.read_bytes()))


class CollectorTests(unittest.TestCase):
    def fixture(self, root, omitted=None, stock_root_size=1024):
        script = root / 'scripts/ci/collect-ax3000t.py'
        script.parent.mkdir(parents=True)
        shutil.copyfile(CI / script.name, script)
        (root / '.config').write_text('CONFIG_PACKAGE_luci-app-passwall=y\n')
        recipe = root / 'package/network/services/dnsmasq/Makefile'
        recipe.parent.mkdir(parents=True)
        recipe.write_text('PKG_UPSTREAM_VERSION:=2.93\nPKG_RELEASE:=1\n')
        for relative, version, release in (
                ('passwall_luci/luci-app-passwall', '26.10.16', '2'),
                ('passwall_packages/xray-core', '26.10.21', '1'),
                ('passwall_packages/sing-box', '1.14.4', '1')):
            recipe = root / 'feeds' / relative / 'Makefile'
            recipe.parent.mkdir(parents=True)
            recipe.write_text(f'PKG_VERSION:={version}\nPKG_RELEASE:={release}\n'
                              'PKG_PO_VERSION:=$(PKG_VERSION)\n')
        subprocess.run([sys.executable, str(CI / 'prepare-passwall-luci.py')], cwd=root, check=True)
        images = root / 'bin/targets/mediatek/mt7981'
        images.mkdir(parents=True)
        profiles = {}
        for device in DEVICES:
            name = f'immortalwrt-mediatek-mt7981-{device}-squashfs-sysupgrade.bin'
            path = images / name
            with tarfile.open(path, 'w') as archive:
                for part in ('kernel', 'root'):
                    entry = tarfile.TarInfo(f'sysupgrade-{device}/{part}')
                    entry.size = stock_root_size if part == 'root' and device.endswith('-stock') else 1024
                    archive.addfile(entry, io.BytesIO(bytes(entry.size)))
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            profiles[device] = {'images': [{'name': name, 'type': 'sysupgrade', 'sha256': digest}]}
            if device == omitted:
                path.unlink()
        # Exercise the old build system's shared multi-profile manifest.
        (images / 'immortalwrt-mediatek-mt7981.manifest').write_text(
            'luci-app-passwall - 26.10.16-2\nluci-app-upnp - 1\n'
            'luci-i18n-upnp-zh-cn - 1\nminiupnpd - 1\ndnsmasq-full - 2.93-1\n'
            'xray-core - 26.10.21-1\nsing-box - 1.14.4-1\n')
        (images / 'profiles.json').write_text(json.dumps({'profiles': profiles}))
        return script

    def run_collector(self, script):
        env = dict(os.environ, **{name: 'a' * 40 for name in (
            'PASSWALL_LUCI', 'PASSWALL_PACKAGES', 'SOURCE_COMMIT', 'BUILD_FINGERPRINT')})
        return subprocess.run([sys.executable, str(script)], env=env, capture_output=True, text=True)

    def test_all_four_required_and_shared_manifest_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_collector(self.fixture(root))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(list((root / 'firmware').glob('*.bin'))), 4)
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_collector(self.fixture(Path(directory), omitted=DEVICES[-1]))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Missing firmware', result.stderr)

    def test_stock_rootfs_uses_78_mib_partition_and_rejects_oversize(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_collector(self.fixture(Path(directory), stock_root_size=36 * 1024 * 1024))
            self.assertEqual(result.returncode, 0, result.stderr)
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_collector(self.fixture(Path(directory), stock_root_size=78 * 1024 * 1024))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('exceeds partition capacity', result.stderr)

    def test_old_or_missing_dnsmasq_blocks_release(self):
        for entry in ('dnsmasq-full - 2.85-1\n', ''):
            with self.subTest(entry=entry), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                script = self.fixture(root)
                manifest = root / 'bin/targets/mediatek/mt7981/immortalwrt-mediatek-mt7981.manifest'
                manifest.write_text(manifest.read_text().replace('dnsmasq-full - 2.93-1\n', entry))
                result = self.run_collector(script)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('dnsmasq-full version mismatch', result.stderr)

    def test_missing_or_wrong_proxy_versions_block_release(self):
        for package in ('luci-app-passwall', 'xray-core', 'sing-box'):
            for replacement in ('', f'{package} - 0.0.0-1\n'):
                with self.subTest(package=package, replacement=replacement), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    script = self.fixture(root)
                    manifest = root / 'bin/targets/mediatek/mt7981/immortalwrt-mediatek-mt7981.manifest'
                    lines = manifest.read_text().splitlines(keepends=True)
                    manifest.write_text(''.join(replacement if line.startswith(package + ' - ') else line
                                                for line in lines))
                    result = self.run_collector(script)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(package + ' version mismatch', result.stderr)

    def test_changed_recipe_versions_are_used_without_hardcoding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = self.fixture(root)
            recipe = root / 'feeds/passwall_packages/xray-core/Makefile'
            recipe.write_text('PKG_VERSION:=27.01.01\nPKG_RELEASE:=3\n')
            self.assertNotEqual(self.run_collector(script).returncode, 0)
            manifest = root / 'bin/targets/mediatek/mt7981/immortalwrt-mediatek-mt7981.manifest'
            manifest.write_text(manifest.read_text().replace('26.10.21-1', '27.01.01-3'))
            result = self.run_collector(script)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_luci_compatibility_step_blocks_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = self.fixture(root)
            recipe = root / 'feeds/passwall_luci/luci-app-passwall/Makefile'
            recipe.write_text(recipe.read_text().replace('PKG_VERSION:=$(PKG_VERSION)-$(PKG_RELEASE)\n', ''))
            result = self.run_collector(script)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Unexpected package version assignments', result.stderr)


class CompatibilityTests(unittest.TestCase):
    def test_luci_version_tracks_new_upstream_versions_and_is_idempotent(self):
        for version, release in (('26.10.16', '2'), ('27.01.01', '7')):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                makefile = root / 'feeds/passwall_luci/luci-app-passwall/Makefile'
                makefile.parent.mkdir(parents=True)
                makefile.write_text(f'PKG_VERSION:={version}\nPKG_RELEASE:={release}\n'
                                    'PKG_PO_VERSION:=$(PKG_VERSION)\n')
                for _ in range(2):
                    subprocess.run([sys.executable, str(CI / 'prepare-passwall-luci.py')],
                                   cwd=root, check=True)
                result = makefile.read_text()
                self.assertIn(f'PKG_VERSION:={version}\n', result)
                self.assertIn(f'PKG_RELEASE:={release}\n', result)
                self.assertEqual(result.count('PKG_VERSION:=$(PKG_VERSION)-$(PKG_RELEASE)'), 1)


if __name__ == '__main__':
    unittest.main()
