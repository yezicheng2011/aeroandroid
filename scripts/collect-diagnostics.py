#!/usr/bin/env python3
"""Save a bounded local report for M5 acceptance; does not upload anything."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

project = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, default=Path.home() / 'Desktop/AndroidSubsystem-Diagnostics.json')
args = parser.parse_args()
report = {'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'checks': {}, 'logs': {}}
for action in ['diagnostic', 'status']:
    run = subprocess.run([sys.executable, str(project / 'backend/subsystem.py'), action], capture_output=True, text=True, timeout=90)
    report['checks'][action] = json.loads(run.stdout) if run.stdout else {'error': run.stderr[-4000:]}
root = Path(os.environ.get('ANDROID_SUBSYSTEM_HOME', Path.home() / 'Library/Application Support/AndroidSubsystem'))
for file in (root / 'logs').glob('*.log'):
    # Read only the last 64 KB per log. Logs may contain app names and local paths.
    with file.open('rb') as f:
        f.seek(max(0, file.stat().st_size - 65536))
        report['logs'][file.name] = f.read().decode('utf-8', 'replace')
args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False))
args.output.chmod(0o600)
print('Saved locally:', args.output)
