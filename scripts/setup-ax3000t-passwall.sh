#!/bin/sh
# Run from a Linux x86_64 build host. This prepares sources; it does not build firmware.
set -eu
cd "$(dirname "$0")/.."
ROOT=$(pwd)
COMPAT="$ROOT/config/ax3000t-passwall"
if [ -e feeds.conf ] && ! cmp -s feeds.conf feeds.conf.default; then
    echo 'feeds.conf differs from the pinned defaults; save it and remove it before setup.' >&2
    exit 1
fi
cp feeds.conf.default feeds.conf
./scripts/feeds update -a
for feed in packages passwall_luci passwall_packages; do
    patch="$COMPAT/$feed.patch"
    if git -C "feeds/$feed" apply --reverse --check "$patch" 2>/dev/null; then
        echo "$feed compatibility patch already applied"
    else
        git -C "feeds/$feed" apply --check "$patch"
        git -C "feeds/$feed" apply "$patch"
    fi
done
mkdir -p feeds/packages/lang/rust
cp -R "$COMPAT/rust/." feeds/packages/lang/rust/
# Remove only conflicting generated links so the new feeds take precedence.
for package in feeds/passwall_packages/*/Makefile feeds/passwall_luci/luci-app-passwall/Makefile; do
    [ -f "$package" ] || continue
    name=$(basename "$(dirname "$package")")
    for link in package/feeds/*/"$name"; do
        [ ! -L "$link" ] || rm "$link"
    done
done
./scripts/feeds install -a
if [ -f .config ]; then
    cp .config .config.before-passwall
fi
cp "$COMPAT/ax3000t.config" .config
make defconfig
echo 'AX3000T PassWall configuration is ready. No firmware build was started.'
