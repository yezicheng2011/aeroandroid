#!/usr/bin/env python3
"""Choose the Android download source from this machine's public country.

Mainland China (country code CN) uses the mirrors already configured in
build.sh. Every other country uses the official source. If the country cannot
be determined, the official source is used.

Copyright 2026 daniel.ye — Apache-2.0
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request

GOOGLE_BASE = 'https://dl.google.com/android/repository/'
DEFAULT_SDK_MIRROR = 'https://mirrors.cloud.tencent.com/AndroidSDK/'
DEFAULT_GH_MIRROR = 'https://gh-proxy.com/'

# Public lookups that return an ISO country code. The first success wins.
# Cloudflare's trace document contains a loc=XX line. ipinfo.io/country is the
# code alone. ip-api.com returns JSON. No API key is sent or required.
LOOKUPS = (
    'https://www.cloudflare.com/cdn-cgi/trace',
    'https://1.1.1.1/cdn-cgi/trace',
    'https://ipinfo.io/country',
    'http://ip-api.com/json/?fields=countryCode',
)

CODE = re.compile(r'^[A-Z]{2}$')


def sdk_mirror():
    value = os.environ.get('SDK_MIRROR', DEFAULT_SDK_MIRROR)
    return value if value.endswith('/') else value + '/'


def gh_mirror():
    value = os.environ.get('GH_MIRROR', DEFAULT_GH_MIRROR)
    return value if value.endswith('/') else value + '/'


def rewrite(url, mirror):
    """Same rewrite rules as build.sh mirror_url(). A non-cn mirror returns url."""
    if mirror != 'cn':
        return url
    if url.startswith(GOOGLE_BASE):
        return sdk_mirror() + url[len(GOOGLE_BASE):]
    if url.startswith('https://github.com/') or url.startswith('https://raw.githubusercontent.com/'):
        return gh_mirror() + url
    return url


def parse_country(body):
    """Return an ISO country code, or None when the body is not one."""
    text = body.strip()
    if len(text) == 2 and CODE.fullmatch(text.upper()):
        return text.upper()
    for line in text.splitlines():
        if line.startswith('loc='):
            code = line.split('=', 1)[1].strip().upper()
            if CODE.fullmatch(code):
                return code
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict):
        for key in ('countryCode', 'country_code', 'country'):
            value = data.get(key)
            if isinstance(value, str) and CODE.fullmatch(value.strip().upper()):
                return value.strip().upper()
    return None


def default_fetch(url, timeout=4):
    request = urllib.request.Request(url, headers={'User-Agent': 'aeroandroid'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(64 * 1024)
    return raw.decode('utf-8', 'replace')


def choose_mirror(explicit='auto', fetch=None):
    """Return 'cn' or 'global'. explicit 'cn' or 'global' skips the lookup."""
    if explicit in ('cn', 'global'):
        return explicit
    if explicit != 'auto':
        raise ValueError('mirror must be cn, global or auto')
    fetch = fetch or default_fetch
    for url in LOOKUPS:
        try:
            code = parse_country(fetch(url))
        except Exception:
            continue
        if code:
            return 'cn' if code == 'CN' else 'global'
    return 'global'


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv in (['-h'], ['--help']):
        print('Usage: mirror.py [--choose]\nPrints cn or global. auto reads the public country; failure prints global.')
        return 0
    if argv not in ([], ['--choose']):
        print('Usage: mirror.py [--choose]', file=sys.stderr)
        return 2
    try:
        print(choose_mirror(os.environ.get('AEROANDROID_MIRROR', 'auto')))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
