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
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise RuntimeError('请在 Apple Silicon Mac 上运行图形验收。')
    root = Path(os.environ.get('ANDROID_SUBSYSTEM_HOME', Path.home() / 'Library/Application Support/AndroidSubsystem'))
    app = Path.home() / 'Applications/Android Subsystem.app'
    if not app.exists(): raise RuntimeError('请先运行 Graphics-Install.command。')
    output = root / 'acceptance' / datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    output.mkdir(parents=True, mode=0o700)
    result = subprocess.run([sys.executable, str(PROJECT / 'backend/subsystem.py'), 'native-session',
                             json.dumps({'package': 'com.android.settings'})], capture_output=True, text=True)
    try: response = json.loads(result.stdout)
    except ValueError: raise RuntimeError('控制器没有返回有效结果：' + result.stderr[-2000:])
    if result.returncode or not response.get('ok'): raise RuntimeError(response.get('error', '无法启动图形服务'))
    # A session contains the local token. Keep it private and delete it after the test.
    with tempfile.TemporaryDirectory(prefix='surface-test-', dir=root) as private:
        session = Path(private) / 'session.json'
        session.write_text(json.dumps(response)); session.chmod(0o600)
        subprocess.run([sys.executable, str(PROJECT / 'tests/guest_smoke.py'), '--session', str(session),
                        '--output', str(output)], check=True)
    for package in ['com.android.settings', 'dev.dan.androidsubsystem']:
        subprocess.run(['/usr/bin/open', '-a', str(app), 'android-subsystem://launch?package=' + package], check=True)
    print('\n真实 Guest 抓帧与双显示器测试通过。像素图和结果：', output)
    print('两个原生窗口已请求打开。请检查窗口中实际出现对应界面，分别缩放、点击，并关闭其中一个。')
    print('这一步仍需要你观察；自动抓帧通过不等于 Metal 显示验收通过。')
    subprocess.run(['/usr/bin/open', str(output)], check=True)


if __name__ == '__main__':
    try: main()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print('图形验收未完成：', error, file=sys.stderr); sys.exit(1)
