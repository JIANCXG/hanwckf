import contextlib
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
        self.assertEqual(updated.count('a' * 40), 2)
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
                 '100644 blob ccc\t.github/ax3000t-passwall-last-success.json']
        with patch.object(updater, 'git', return_value='\n'.join(lines)):
            first = updater.fingerprint('effective feeds\n')
        lines[1] = '100644 blob ddd\tfeeds.conf.default'
        lines[2] = '100644 blob eee\t.github/ax3000t-passwall-last-success.json'
        with patch.object(updater, 'git', return_value='\n'.join(lines)):
            self.assertEqual(first, updater.fingerprint('effective feeds\n'))


class CollectorTests(unittest.TestCase):
    def fixture(self, root, omitted=None, stock_root_size=1024):
        script = root / 'scripts/ci/collect-ax3000t.py'
        script.parent.mkdir(parents=True)
        shutil.copyfile(CI / script.name, script)
        (root / '.config').write_text('CONFIG_PACKAGE_luci-app-passwall=y\n')
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
        (images / 'immortalwrt-mediatek-mt7981.manifest').write_text('luci-app-passwall - 26.10.16-2\n')
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
