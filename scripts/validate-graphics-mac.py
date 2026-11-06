#!/usr/bin/env python3
"""Capture two real Guest surfaces, then open them in native Mac windows."""
import datetime
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1]


def main():
    if platform.system() != 'Darwin':
        raise RuntimeError('Run the graphics acceptance on a Mac.')
    root = Path(os.environ.get('ANDROID_SUBSYSTEM_HOME', Path.home() / 'Library/Application Support/AndroidSubsystem'))
    app = Path.home() / 'Applications/Android Subsystem.app'
    if not app.exists(): raise RuntimeError('Run Graphics-Install.command first.')
    output = root / 'acceptance' / datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    output.mkdir(parents=True, mode=0o700)
    result = subprocess.run([sys.executable, str(PROJECT / 'backend/subsystem.py'), 'native-session',
                             json.dumps({'package': 'com.android.settings'})], capture_output=True, text=True)
    try: response = json.loads(result.stdout)
    except ValueError: raise RuntimeError('The controller did not return a valid result: ' + result.stderr[-2000:])
    if result.returncode or not response.get('ok'): raise RuntimeError(response.get('error', 'Could not start the graphics service'))
    # A session contains the local token. Keep it private and delete it after the test.
    with tempfile.TemporaryDirectory(prefix='surface-test-', dir=root) as private:
        session = Path(private) / 'session.json'
        session.write_text(json.dumps(response)); session.chmod(0o600)
        subprocess.run([sys.executable, str(PROJECT / 'tests/guest_smoke.py'), '--session', str(session),
                        '--output', str(output)], check=True)
    for package in ['com.android.settings', 'dev.dan.androidsubsystem']:
        subprocess.run(['/usr/bin/open', '-a', str(app), 'android-subsystem://launch?package=' + package], check=True)
    print('\nReal Guest frame capture and the two-display test passed. Pixel images and results:', output)
    print('Two native windows were asked to open. Check that each window shows the matching screen, then resize, click, and close one of them.')
    print('You still need to look: captured frames passing does not mean the Metal display passed acceptance.')
    subprocess.run(['/usr/bin/open', str(output)], check=True)


if __name__ == '__main__':
    try: main()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print('Graphics acceptance did not finish:', error, file=sys.stderr); sys.exit(1)
