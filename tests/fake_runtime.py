#!/usr/bin/python3
"""Deterministic external-process fixture; never used by the actual application."""
import base64
import json
import struct
import zlib
import os
from pathlib import Path
import shlex
import signal
import sys
import time

def png512():
    chunk = lambda kind, body: struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
    rows = b''.join(b'\0' + b'\x20\x80\xc0\xff' * 512 for _ in range(512))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 512, 512, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b'')


name = Path(sys.argv[0]).name
root = Path(os.environ['TEST_RUNTIME_ROOT'])
state_path = root / 'device.json'
args = sys.argv[1:]
if name == 'avdmanager':
    avd = args[args.index('--name') + 1]
    path = Path(args[args.index('--path') + 1])
    path.mkdir(parents=True)
    (path / 'config.ini').write_text('hw.ramSize=1024\n')
    (Path(os.environ['ANDROID_AVD_HOME']) / (avd + '.ini')).write_text('path=' + str(path))
elif name == 'emulator':
    if '-accel-check' in args: print('Hypervisor test fixture'); sys.exit(0)
    if args == ['-webcam', 'list']:
        if (root / 'webcam').exists(): print("List of web cameras connected to the computer:\n Camera 'webcam0' is connected to device 'FaceTime HD Camera'.")
        sys.exit(0)
    avd = args[args.index('-avd') + 1]
    (root / 'emulator-argv.json').write_text(json.dumps(args))
    state_path.write_text(json.dumps({'avd': avd, 'pid': os.getpid(), 'api': str(int(avd.split('_')[1]) + 20)}))
    while True: time.sleep(0.1)
elif name == 'adb':
    serial = args[1]
    args = args[2:]  # -s SERIAL
    state = json.loads(state_path.read_text()) if state_path.exists() else None
    if args == ['get-state']:
        if state: print('device')
        else: print('offline', file=sys.stderr); sys.exit(1)
    elif not state: sys.exit(1)
    elif args == ['emu', 'avd', 'name']: print(state['avd'] + '\nOK')
    elif args == ['emu', 'kill']:
        state_path.unlink(); os.kill(state['pid'], signal.SIGTERM); print('OK')
    elif args[0] == 'forward':
        forward = root / 'forward.txt'
        if args[1] == '--list':
            if forward.exists(): print(forward.read_text())
        elif args[1] == '--remove': forward.unlink(missing_ok=True)
        else: forward.write_text(serial + ' tcp:15990 tcp:7900'); print('15990')
    elif args[0] == 'shell':
        command = shlex.split(args[1])
        with (root / 'shell-commands.jsonl').open('a') as f: f.write(json.dumps(command) + '\n')
        if command[0].startswith('CLASSPATH='):
            print('Mac Surface Bridge ready v1', flush=True)
            while True: time.sleep(0.1)
        elif command[:2] == ['getprop', 'sys.boot_completed']: print('1')
        elif command[:2] == ['getprop', 'ro.build.version.sdk']: print(state['api'])
        elif command[:2] == ['getprop', 'ro.product.cpu.abilist']: print('x86_64,x86')
        elif command[:2] == ['content', 'query']:
            endpoint = command[-1].rsplit('/', 1)[-1]
            if endpoint == 'apps': data = {'apps': [{'package': 'com.example.first', 'label': 'First'}, {'package': 'com.example.second', 'label': 'Second'}]}
            elif endpoint.startswith('icon?package='): data = {'icon': base64.b64encode(png512()).decode()}
            elif endpoint == 'notifications': data = {'notifications': [{'id': 'one', 'key': 'one', 'title': 'Hello', 'body': 'World', 'package': 'com.example.first', 'timestamp': 1}]}
            else: data = {'notification_access': True}
            print('Row: 0 payload=' + base64.b64encode(json.dumps(data).encode()).decode())
        elif command[0] == 'test': sys.exit(1)
        elif command[0] == 'find': print('/sdcard/Download/MacBridge/test.txt')
    elif args[0] in ['install', 'install-multiple', 'uninstall']:
        if args[0] != 'uninstall' and Path(args[-1]).read_bytes() == b'arm64 only': print('Failure [INSTALL_FAILED_NO_MATCHING_ABIS: Failed to extract native libraries, res=-113]')
        else: print('Success')
    elif args[0] == 'push': print('1 file pushed')
    elif args[0] == 'pull': (Path(args[2]) / Path(args[1]).name).write_text('android data')
elif name == 'scrcpy':
    if args == ['--help']:
        print('--new-display --start-app --display-ime-policy --flex-display --keep-active')
    elif '--list-apps' in args:
        print(' * First                     com.example.first')
    else:
        with (root / 'windows.jsonl').open('a') as f: f.write(json.dumps(args) + '\n')
        while True: time.sleep(0.1)
elif name == 'aapt2':
    print("package: name='com.example.fixture' versionCode='1'\napplication-label:'Fixture App'\napplication-label-zh-CN:'示例'\nlaunchable-activity: name='com.example.Main'")
elif name == 'sdkmanager': print('fake sdkmanager')
