#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check that every generated multiplayer header shadows the upstream header in active Ninja objects.

The nx2 core now has native socket hardening (AcceptsProxyPacket). In that case
socket_proxy.h and bsd.h intentionally remain upstream headers; the CMake overlay
generates replacements for them only for older cores. Validate the generated set
actually present in this build rather than assuming the older-core layout.
"""
import pathlib
import subprocess
import sys

build = pathlib.Path(sys.argv[1])
overlay = build / 'headless' / 'multiplayer'
generated = {
    'network/packet.h': overlay / 'network/packet.h',
    'network/room_member.h': overlay / 'network/room_member.h',
    'core/internal_network/sockets.h':
        overlay / 'socket-headers/core/internal_network/sockets.h',
    'core/internal_network/socket_proxy.h':
        overlay / 'socket-headers/core/internal_network/socket_proxy.h',
    'core/hle/service/sockets/bsd.h':
        overlay / 'socket-headers/core/hle/service/sockets/bsd.h',
}

def ninja(*args):
    return subprocess.run(['ninja', '-C', str(build), '-t', *args],
                          capture_output=True, text=True, check=True).stdout

active = {line.split(': ', 1)[0] for line in ninja('targets', 'all').splitlines()}
expected = {}
for header, path in generated.items():
    if path.exists():
        expected[header] = path.resolve().as_posix()
    elif header in ('network/packet.h', 'network/room_member.h',
                    'core/internal_network/sockets.h'):
        sys.exit(f'Multiplayer generated header is missing: {path}')

seen = dict.fromkeys(expected, 0)
wrong, target = [], None
for line in ninja('deps').splitlines():
    if line and not line.startswith(' '):
        target = line.split(': ', 1)[0]
        continue
    if target not in active:
        continue
    path = line.strip().replace('\\\\', '/')
    for header, generated_path in expected.items():
        if path.endswith('/' + header):
            if path == generated_path:
                seen[header] += 1
            else:
                wrong.append(f'{target}: {path} (expected {generated_path})')

missing = [header for header, count in seen.items() if not count]
if wrong or missing:
    print('\\n'.join(wrong[:20]))
    sys.exit(f'Multiplayer headers: {len(wrong)} unexpected upstream dependencies, missing generated dependencies {missing}')
print(f'Multiplayer generated headers: {seen} PASS')
