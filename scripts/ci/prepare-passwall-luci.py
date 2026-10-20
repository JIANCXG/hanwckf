#!/usr/bin/env python3
"""Give old LuCI the full upstream version without hardcoding a release."""
from pathlib import Path
import re

path = Path('feeds/passwall_luci/luci-app-passwall/Makefile')
text = path.read_text(encoding='utf-8')
marker = '# OpenWrt 21.02 LuCI expects the release inside PKG_VERSION.\n'
if marker not in text:
    if not re.search(r'^PKG_VERSION:=\S+', text, re.M):
        raise SystemExit('PassWall PKG_VERSION declaration changed; review compatibility.')
    if not re.search(r'^PKG_RELEASE:=\S+', text, re.M):
        raise SystemExit('PassWall PKG_RELEASE declaration changed; review compatibility.')
    text, count = re.subn(
        r'^(PKG_PO_VERSION:=.*)$',
        marker + 'PKG_VERSION:=$(PKG_VERSION)-$(PKG_RELEASE)\n\\1',
        text, flags=re.M,
    )
    if count != 1:
        raise SystemExit('PassWall PKG_PO_VERSION declaration changed; review compatibility.')
    path.write_text(text, encoding='utf-8', newline='\n')
