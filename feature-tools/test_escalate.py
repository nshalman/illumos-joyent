#!/usr/bin/env python3
"""Tests for escalate.py.

  python3 test_escalate.py
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import escalate  # noqa: E402


class EscalateTest(unittest.TestCase):

    def test_issue_is_written_as_a_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = escalate.write_issue(d, 'lx', 'Gate intake: lx stuck',
                                        'Body text.\n')
            self.assertEqual(os.path.basename(path), 'lx.md')
            self.assertEqual(open(path).read(),
                             '# Gate intake: lx stuck\n\nBody text.\n')

    def test_issue_opened_with_gh_only_when_asked(self):
        calls = []

        class Done:
            returncode = 0
            stdout = 'https://github.com/o/r/issues/1\n'

        def run(args, **kw):
            calls.append((args, kw.get('input')))
            return Done()
        with tempfile.TemporaryDirectory() as d:
            escalate.escalate(d, 'lx', 'T', 'B\n', repo=None, run=run)
            self.assertEqual(calls, [])
            url = escalate.escalate(d, 'lx', 'T', 'B\n', repo='o/r', run=run)
        self.assertEqual(url, 'https://github.com/o/r/issues/1')
        self.assertEqual(calls, [(['gh', 'issue', 'create', '--repo', 'o/r',
                                   '--title', 'T', '--body-file', '-'],
                                  'B\n')])


if __name__ == '__main__':
    unittest.main()
