"""The app is English by default, so English must be complete and nothing user-facing may be left in Chinese."""
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
    def test_english_has_every_string_chinese_has_and_the_reverse(self):
        en, zh = catalog('en'), catalog('zh')
        self.assertGreater(len(en), 100)
        self.assertEqual(sorted(set(zh) - set(en)), [], 'missing from English: these would show Chinese or a raw key')
        self.assertEqual(sorted(set(en) - set(zh)), [])

    def test_english_text_contains_no_chinese_except_the_name_of_the_language_itself(self):
        offenders = {key: text for key, text in catalog('en').items() if CJK.search(text) and key != 'settings.lang.zh'}
        self.assertEqual(offenders, {})

    def test_placeholders_match_between_languages(self):
        en, zh = catalog('en'), catalog('zh')
        for key in en:
            self.assertEqual(sorted(re.findall(r'\{\d\}', en[key])), sorted(re.findall(r'\{\d\}', zh[key])), key)

    def test_english_is_the_default_and_the_fallback(self):
        self.assertRegex(SWIFT, r'\?\? ""\) \?\? \.en')                  # no saved choice (or an old "system") -> English
        self.assertIn('preference() == .zh ? .zh : .en', SWIFT)            # the system language is never consulted
        self.assertIn('messages[.en]![key] ?? key', SWIFT)                 # a missing string falls back to English
        self.assertNotIn('Locale.preferredLanguages', SWIFT)


class RepositoryIsEnglishTests(unittest.TestCase):
    ALLOWED_FILES = ('macos/Sources/AndroidSubsystem/L10n.swift',        # the optional Chinese catalog
                     'docs/original/', 'third_party/', 'tests/')           # archived README, vendored code, test data
    ALLOWED_TEXT = ('叶子诚', '中文')                                            # the copyright holder's name

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
