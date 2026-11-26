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


WIDGET_PROVIDERS = [
    {'provider': 'com.example.first/com.example.first.ExampleWidget', 'package': 'com.example.first',
     'label': 'Example widget', 'app_label': 'Example', 'min_width_dp': 64, 'min_height_dp': 64,
     'min_resize_width_dp': 64, 'min_resize_height_dp': 64, 'max_resize_width_dp': 1280,
     'max_resize_height_dp': 1280, 'resize_mode': 3, 'has_configuration': True,
     'configuration_optional': False, 'reconfigurable': True},
    {'provider': 'com.example.clock/com.example.clock.ClockWidget', 'package': 'com.example.clock',
     'label': 'Clock', 'app_label': 'Clock', 'min_width_dp': 64, 'min_height_dp': 64,
     'min_resize_width_dp': 64, 'min_resize_height_dp': 64, 'max_resize_width_dp': 1280,
     'max_resize_height_dp': 1280, 'resize_mode': 3, 'has_configuration': False,
     'configuration_optional': False, 'reconfigurable': False}]


def canonical_provider(value):
    package, activity = value.split('/')
    return package + '/' + (package + activity if activity.startswith('.') else activity)


def widget_state(root):
    path = root / 'widget-state.json'
    return json.loads(path.read_text()) if path.exists() else {'next_id': 1, 'widgets': []}


def widget_call(root, method, params):
    state = widget_state(root)
    if method == 'widget-create':
        provider = next((item for item in WIDGET_PROVIDERS if
                         canonical_provider(item['provider']) == canonical_provider(params['provider'])), None)
        if provider is None:
            return {'error': 'This Android widget provider is not installed'}
        widget = {'id': state['next_id'], 'provider': provider['provider'], 'label': provider['label'],
                  'width_dp': params['width_dp'], 'height_dp': params['height_dp'], 'bound': False,
                  'configured': not provider['has_configuration'] or provider['configuration_optional'],
                  'needs_permission': True, 'active': False, 'configuring': False,
                  'provider_available': True, 'reconfigurable': provider['reconfigurable']}
        state['next_id'] += 1
        state['widgets'].append(widget)
        result = {'widget': widget}
    else:
        widget = next((item for item in state['widgets'] if item['id'] == params['id']), None)
        if widget is None:
            return {'error': 'This Android widget no longer exists'}
        if method == 'widget-resize':
            widget.update({key: params[key] for key in ('width_dp', 'height_dp')})
            result = {'widget': widget}
        else:
            state['widgets'].remove(widget)
            result = {'deleted': True, 'id': params['id']}
    pending = root / 'widget-state.tmp'
    pending.write_text(json.dumps(state))
    pending.replace(root / 'widget-state.json')
    return result


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
    state_path.write_text(json.dumps({'avd': avd, 'pid': os.getpid(), 'api': str(int(avd.split('_')[1]) + 20),
                                      'port': args[args.index('-port') + 1]}))
    while True: time.sleep(0.1)
elif name == 'adb' and args == ['devices']:
    # What the adb Terminal runs on opening, and what a person types there first: no -s.
    print('List of devices attached')
    if state_path.exists(): print('emulator-' + json.loads(state_path.read_text())['port'] + '\tdevice')
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
        elif command[:3] == ['cmd', 'role', 'get-role-holders']:
            print('dev.dan.androidsubsystem')
        elif command[:2] == ['pm', 'path']:
            # Like the real pm: no output and a failing exit code for a package that is not installed.
            if command[2] == 'dev.dan.androidsubsystem' and (root / 'no-companion').exists(): sys.exit(1)
            print('package:/data/app/' + command[2] + '/base.apk')
        elif command[0] == 'content' and (root / 'no-companion').exists():
            # Like the real `content`: the reason goes to stderr, stdout stays empty and the exit code stays 0.
            print('Error while accessing provider:dev.dan.androidsubsystem.bridge\n'
                  'java.lang.IllegalStateException: Could not find provider: dev.dan.androidsubsystem.bridge', file=sys.stderr)
        elif command[:2] == ['content', 'call'] and '--method' in command and command[command.index('--method') + 1] == 'storage-config':
            print('Result: Bundle[{configured=' + ('true' if command[command.index('--arg') + 1] else 'false') + '}]')
        elif command[:2] == ['content', 'call'] and '--method' in command and command[command.index('--method') + 1] in ('widget-create', 'widget-resize', 'widget-delete'):
            method = command[command.index('--method') + 1]
            data = widget_call(root, method, json.loads(command[command.index('--arg') + 1]))
            print('Result: Bundle[{payload=' + base64.b64encode(json.dumps(data).encode()).decode() + '}]')
        elif command[:2] == ['content', 'query']:
            endpoint = command[-1].rsplit('/', 1)[-1]
            if endpoint == 'apps': data = {'apps': [{'package': 'com.example.first', 'label': 'First'}, {'package': 'com.example.second', 'label': 'Second'}]}
            elif endpoint.startswith('icon?package='): data = {'icon': base64.b64encode(png512()).decode()}
            elif endpoint == 'notifications': data = {'notifications': [{'id': 'one', 'key': 'one', 'title': 'Hello', 'body': 'World', 'package': 'com.example.first', 'timestamp': 1}]}
            elif endpoint == 'widget-providers': data = {'providers': WIDGET_PROVIDERS}
            elif endpoint == 'widgets': data = {'widgets': widget_state(root)['widgets']}
            else: data = {'notification_access': True}
            print('Row: 0 payload=' + base64.b64encode(json.dumps(data).encode()).decode())
        elif command[0] == 'test': sys.exit(1)
        elif command[0] == 'find': print('/sdcard/Download/MacBridge/test.txt')
    elif args[0] in ['install', 'install-multiple', 'uninstall']:
        if args[0] != 'uninstall' and Path(args[-1]).read_bytes() == b'arm64 only':
            # Like the real adb: the reason goes to stderr and the exit code says it failed.
            print('adb: failed to install game.apk: Failure [INSTALL_FAILED_NO_MATCHING_ABIS: Failed to extract native libraries, res=-113]', file=sys.stderr)
            sys.exit(1)
        else:
            # Installing the bridge fixture is what makes its content provider answer.
            if args[0] == 'install' and Path(args[-1]).read_bytes() == b'ci bridge': (root / 'no-companion').unlink(missing_ok=True)
            print('Success')
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
