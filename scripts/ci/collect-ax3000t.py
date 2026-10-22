#!/usr/bin/env python3
"""Require all four firmware variants, validate capacity, and collect release files."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tarfile


def check_capacity(device, payload):
    def physical(size):
        return ((size + 126975) // 126976) * 131072

    def fits(sizes, capacity):
        # Reserve metadata/volume tables and the nominal 2% bad-block allowance.
        reserved = (4 + (capacity // 131072 + 49) // 50) * 131072
        return sum(physical(size) for size in sizes) + reserved < capacity

    if device.endswith('-stock'):
        # The DTS/upgrade script puts the kernel in 34 MiB ubi_kernel and
        # rootfs in a DIFFERENT 78 MiB ubi partition. IMAGE_SIZE is not rootfs size.
        valid = (fits([payload['kernel']], 34 * 1024 * 1024)
                 and fits([payload['root']], 78 * 1024 * 1024))
    else:
        valid = fits(payload.values(), 112 * 1024 * 1024)
    if not valid:
        raise SystemExit(f'{device}: firmware exceeds partition capacity; refusing release')


root = Path(__file__).resolve().parents[2]
images = root / 'bin/targets/mediatek/mt7981'
destination = root / 'firmware'
destination.mkdir(exist_ok=True)
devices = (
    'xiaomi_mi-router-ax3000t',
    'xiaomi_mi-router-ax3000t-stock',
    'xiaomi_mi-router-ax3000t-an8855',
    'xiaomi_mi-router-ax3000t-an8855-stock',
)
profiles = json.loads((images / 'profiles.json').read_text())['profiles']
dnsmasq_recipe = (root / 'package/network/services/dnsmasq/Makefile').read_text()
dnsmasq_version = re.search(r'^PKG_UPSTREAM_VERSION:=(\S+)$', dnsmasq_recipe, re.M).group(1)
dnsmasq_release = re.search(r'^PKG_RELEASE:=(\d+)$', dnsmasq_recipe, re.M).group(1)
# The 21.02 package version format is <version>-<release>, without the newer r prefix.
expected_dnsmasq = f'{dnsmasq_version}-{dnsmasq_release}'
collected = []
for device in devices:
    profile = profiles[device]
    upgrades = [item for item in profile['images'] if item['type'] == 'sysupgrade']
    if len(upgrades) != 1:
        raise SystemExit(f'Expected one sysupgrade image for {device}')
    image = images / upgrades[0]['name']
    if not image.is_file():
        raise SystemExit(f'Missing firmware: {image}')
    # Sysupgrade tar metadata/padding is not flashed; inspect kernel/root payloads.
    with tarfile.open(image) as archive:
        payload = [entry for entry in archive.getmembers()
                   if entry.isfile() and entry.name.rsplit('/', 1)[-1] in ('kernel', 'root')]
        if len(payload) != 2:
            raise SystemExit(f'Kernel/root payload missing in {image.name}')
        check_capacity(device, {entry.name.rsplit('/', 1)[-1]: entry.size for entry in payload})
    manifest = images / f"{image.name.rsplit('-squashfs-', 1)[0]}.manifest"
    # Per-device manifests can have a different filesystem suffix on older builds.
    if not manifest.exists():
        manifests = list(images.glob(f'*{device}.manifest'))
        if not manifests:
            # 21.02 multi-profile builds with identical packages use one manifest.
            manifests = list(images.glob('*.manifest'))
        if len(manifests) != 1:
            raise SystemExit(f'Cannot identify package manifest for {device}')
        manifest = manifests[0]
    for package in ('luci-app-passwall', 'luci-app-upnp', 'luci-i18n-upnp-zh-cn', 'miniupnpd'):
        if f'{package} - ' not in manifest.read_text():
            raise SystemExit(f'{package} missing from {device}')
    packages = dict(line.split(' - ', 1) for line in manifest.read_text().splitlines() if ' - ' in line)
    if packages.get('dnsmasq-full') != expected_dnsmasq:
        raise SystemExit(f'dnsmasq-full version mismatch for {device}: expected {expected_dnsmasq}, '
                         f"found {packages.get('dnsmasq-full', '<missing>')}")
    for item in profile['images']:
        source = images / item['name']
        if not source.is_file():
            raise SystemExit(f'Missing image: {source}')
        if item.get('sha256') != hashlib.sha256(source.read_bytes()).hexdigest():
            raise SystemExit(f'Image checksum does not match profiles.json: {source}')
        shutil.copy2(source, destination / source.name)
        collected.append(source.name)
    shutil.copy2(manifest, destination / manifest.name)

for name in ('profiles.json', 'config.buildinfo', 'feeds.buildinfo', 'version.buildinfo'):
    source = images / name
    if source.exists():
        shutil.copy2(source, destination / name)
shutil.copy2(root / '.config', destination / 'ax3000t.config')
info = {name: os.environ[name] for name in (
    'PASSWALL_LUCI', 'PASSWALL_PACKAGES', 'SOURCE_COMMIT', 'BUILD_FINGERPRINT')}
info['devices'] = devices
info['images'] = collected
(destination / 'build-info.json').write_text(json.dumps(info, indent=2) + '\n')
checksums = []
for path in sorted(destination.iterdir()):
    if path.is_file() and path.name != 'sha256sums':
        checksums.append(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}')
(destination / 'sha256sums').write_text('\n'.join(checksums) + '\n')
print(f'Validated all four variants; collected {len(collected)} firmware images.')
