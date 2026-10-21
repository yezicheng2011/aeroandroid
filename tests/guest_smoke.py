#!/usr/bin/env python3
"""Real Guest graphics/control smoke test. It does not test Metal or VM zero-copy.

Normal M5 usage: supply an authenticated session JSON saved from native-session.
Server validation supplies port + private token file for its isolated test Guest.
No token is copied into the report.
"""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import struct
import time
import zlib

MAX_FRAME = 20 + 2560 * 2560 * 4

class Session:
    def __init__(self, config, package):
        self.timeout = config.get('test_timeout', 180)
        self.socket = socket.create_connection(('127.0.0.1', config['port']), timeout=self.timeout)
        self.socket.settimeout(self.timeout)
        self.config = {k:v for k,v in config.items() if k != 'test_timeout'}
        self.send({**self.config, 'package': package, 'type': 'hello', 'version': 1})
        self.display = None
    def send(self, payload):
        data = json.dumps(payload).encode()
        self.socket.sendall(struct.pack('>BI', 16, len(data)) + data)
    def exact(self, size):
        out = bytearray()
        while len(out) < size:
            part = self.socket.recv(size - len(out))
            if not part: raise RuntimeError('Guest closed the graphics connection')
            out.extend(part)
        return bytes(out)
    def frame(self, width=None, height=None, visible=False):
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            kind, count = struct.unpack('>BI', self.exact(5))
            if count > MAX_FRAME or count < 1: raise RuntimeError('Bad packet length')
            data = self.exact(count)
            if kind == 3:
                event = json.loads(data)
                if event.get('event') == 'error': raise RuntimeError(event.get('message'))
                if event.get('event') == 'ready': self.display = event['display']
            elif kind == 1:
                w, h, stride, timestamp = struct.unpack('>IIIQ', data[:20])
                if stride != w * 4 or len(data) != 20 + stride * h: raise RuntimeError('Bad frame geometry')
                if self.display is not None and (width is None or width == w) and (height is None or height == h):
                    pixels = data[20:]
                    sample_step = max(1, w * h // 4096) * 4
                    colors = len({pixels[i:i+4] for i in range(0, len(pixels), sample_step)})
                    if visible and colors < 8: continue
                    return {'width': w, 'height': h, 'stride': stride, 'timestamp': timestamp,
                            'sha256': hashlib.sha256(pixels).hexdigest(), 'sampled_colors': colors, 'payload': data}
        raise RuntimeError('No matching frame received')
    def close(self):
        try: self.send({'type': 'close'})
        except OSError: pass
        finally: self.socket.close()


def save_frame(output, name, frame):
    payload = frame['payload']
    (output / (name + '.bin')).write_bytes(struct.pack('>BI', 1, len(payload)) + payload)
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    w, h, stride = frame['width'], frame['height'], frame['stride']
    pixels = payload[20:]
    rows = b''.join(b'\0' + pixels[y*stride:(y+1)*stride] for y in range(h))
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b'')
    (output / (name + '.png')).write_bytes(png)


def run(config, output, first_package='com.android.settings'):
    results = {}
    results['packages'] = [first_package, 'dev.dan.androidsubsystem']
    first = Session(config, first_package)
    second = None
    try:
        frame = first.frame(visible=True); results['settings_frame'] = {k:v for k,v in frame.items() if k != 'payload'}
        save_frame(output, 'settings-frame', frame)
        # The companion is a different application with a real launcher Activity.
        second = Session(config, 'dev.dan.androidsubsystem')
        frame = second.frame(visible=True); results['companion_frame'] = {k:v for k,v in frame.items() if k != 'payload'}
        save_frame(output, 'companion-frame', frame)
        if results['settings_frame']['sha256'] == results['companion_frame']['sha256']:
            raise RuntimeError('Both applications returned the same pixels')
        if first.display is None or second.display is None:
            # Some frames can arrive before ready; trigger resize to drain ready metadata.
            first.send({'type':'resize','width':640,'height':480}); first.frame(640,480)
            second.send({'type':'resize','width':640,'height':480}); second.frame(640,480)
        if first.display == second.display or first.display is None or second.display is None:
            raise RuntimeError('Applications did not get distinct Guest displays')
        results['distinct_displays'] = [first.display, second.display]
        first.send({'type':'resize','width':960,'height':640,'dpi':200})
        results['resize_frame'] = {k:v for k,v in first.frame(960,640).items() if k != 'payload'}
        # Input acceptance is observed by absence of a protocol error and a subsequent frame.
        # It does not prove that a specific button/caret was targeted; that is a Mac acceptance check.
        first.send({'type':'pointer','action':0,'x':30,'y':30})
        first.send({'type':'pointer','action':1,'x':30,'y':30})
        first.send({'type':'key','code':4,'action':0}); first.send({'type':'key','code':4,'action':1})
        first.send({'type':'resize','width':800,'height':600,'dpi':160}); first.frame(800,600)
        results['input_injection_accepted'] = True
        first.close(); first = None
        second.send({'type':'resize','width':800,'height':600,'dpi':160}); second.frame(800,600)
        results['one_display_survives_other_close'] = True
        results['metal_tested'] = False; results['zero_copy_tested'] = False
        (output / 'guest-smoke.json').write_text(json.dumps(results, indent=2))
        print(json.dumps(results, indent=2))
    finally:
        if first is not None: first.close()
        if second is not None: second.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--session', type=Path)
    parser.add_argument('--port', type=int)
    parser.add_argument('--token-file', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=180)
    parser.add_argument('--first-package', default='com.android.settings')
    args = parser.parse_args()
    if args.session:
        response = json.loads(args.session.read_text()); config = response.get('data', response)
    else:
        if not args.port or not args.token_file: parser.error('Provide session or port + token-file')
        config = {'port':args.port,'token':args.token_file.read_text(),'width':800,'height':600,'dpi':160,'fps':15}
    args.output.mkdir(parents=True, exist_ok=True)
    config['test_timeout'] = max(10, args.timeout)
    run(config, args.output, args.first_package)

if __name__ == '__main__': main()
