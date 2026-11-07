"""Exercise the original SIP engine against a real local TCP peer on a host JVM."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def java_tool(name):
    java_home = os.environ.get('JAVA_HOME')
    if java_home:
        candidate = Path(java_home) / 'bin' / name
        if candidate.is_file():
            return str(candidate)
    return shutil.which(name)


class SipProtocolTests(unittest.TestCase):
    def run_java_checks(self, sources, main, success_text):
        javac, java = java_tool('javac'), java_tool('java')
        if not javac or not java:
            self.skipTest('A JDK is needed for the host-JVM SIP peer tests')
        with tempfile.TemporaryDirectory() as output:
            compile_result = subprocess.run(
                [javac, '-encoding', 'UTF-8', '--release', '8', '-d', output,
                 *[str(ROOT / source) for source in sources]],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(compile_result.returncode, 0, compile_result.stdout + compile_result.stderr)
            run = subprocess.run([java, '-cp', output, main],
                                 capture_output=True, text=True, timeout=90)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn(success_text, run.stdout)

    def test_registration_messages_and_call_signaling_over_real_tcp(self):
        self.run_java_checks([
            'guest/src/dev/dan/androidsubsystem/sip/SipClient.java',
            'tests/SipClientTests.java'], 'SipClientTests', 'SIP protocol tests passed')

    def test_g711_codecs_and_rtp_framing(self):
        self.run_java_checks([
            'guest/src/dev/dan/androidsubsystem/sip/G711.java',
            'guest/src/dev/dan/androidsubsystem/sip/RtpPacket.java',
            'tests/G711Tests.java'], 'G711Tests', 'G.711 and RTP framing checks passed')


if __name__ == '__main__':
    unittest.main()
