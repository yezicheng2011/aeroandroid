"""The app has one complete English catalog and no language-dependent UI."""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CJK = re.compile('[　-〿㐀-鿿＀-￯]')
SWIFT = (ROOT / 'macos/Sources/AndroidSubsystem/L10n.swift').read_text(encoding='utf-8')


def catalog(name):
    """{key: text} of one `private static let NAME: [String: String] = [ ... ]` block."""
    body = re.search(rf'private static let {name}: \[String: String\] = \[\n(.*?)\n    \]', SWIFT, re.S).group(1)
    return dict(re.findall(r'^\s*"([^"]+)":\s*"((?:[^"\\]|\\.)*)",?\s*$', body, re.M))


class CatalogTests(unittest.TestCase):
    def test_english_catalog_covers_literal_ui_keys(self):
        en = catalog('en')
        self.assertGreater(len(en), 100)
        used = set()
        for path in (ROOT / 'macos/Sources/AndroidSubsystem').glob('*.swift'):
            used.update(re.findall(r'(?:L10n|model)\.t\("([^"\\]+)"', path.read_text()))
        # This prefix is completed using a backend error code at runtime.
        used.discard('err.backend.')
        self.assertEqual(sorted(used - en.keys()), [])

    def test_catalog_and_ui_are_english_only(self):
        self.assertFalse(CJK.search(SWIFT))
        self.assertNotIn('private static let zh:', SWIFT)
        self.assertNotIn('settings.lang.zh', SWIFT)
        self.assertIn('var text = en[key] ?? key', SWIFT)
        self.assertNotIn('UserDefaults', SWIFT)
        self.assertNotIn('Locale.preferredLanguages', SWIFT)
        ui = (ROOT / 'macos/Sources/AndroidSubsystem/AndroidSubsystem.swift').read_text()
        self.assertNotIn('setUiLang', ui)
        self.assertNotIn('settings.language', ui)

    def test_memory_policy_is_explained_without_claiming_live_resize(self):
        en = catalog('en')
        self.assertIn('at each startup', en['settings.memory_auto_hint'])
        self.assertIn('does not resize', en['settings.memory_auto_hint'])
        self.assertIn('{0}', en['settings.memory_active'])
        self.assertIn('{0}', en['settings.memory_estimate'])


class RepositoryIsEnglishTests(unittest.TestCase):
    ALLOWED_FILES = ('docs/original/', 'third_party/', 'tests/')     # archived README, vendored code, test data
    ALLOWED_TEXT = ('叶子诚',)                                            # the copyright holder's name

    def test_no_user_facing_file_contains_chinese(self):
        files = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True).stdout.decode().split('\0')
        offenders = []
        for name in files:
            if not name or name.startswith(self.ALLOWED_FILES):
                continue
            try:
                lines = (ROOT / name).read_text(encoding='utf-8').splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for number, line in enumerate(lines, 1):
                for allowed in self.ALLOWED_TEXT:
                    line = line.replace(allowed, '')
                if CJK.search(line):
                    offenders.append(f'{name}:{number}')
        self.assertEqual(offenders, [], 'Chinese text left in user-facing files')

    def test_no_file_name_is_chinese(self):
        files = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True).stdout.decode().split('\0')
        self.assertEqual([f for f in files if CJK.search(f) and not f.startswith(self.ALLOWED_FILES)], [])


if __name__ == '__main__':
    unittest.main()
