#!/usr/bin/env python3
"""Tests for release.py: rebuilding a release from gate and features.

  python3 test_release.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ft  # noqa: E402
import release  # noqa: E402
from test_ft import GATE, FtTest, lines  # noqa: E402


class RecutTest(FtTest):
    """A release forked from master, carrying fixes of its own."""

    def setUp(self):
        super().setUp()
        self.f1 = self.feature({'b.c': lines('b1', 'b2', 'b3', 'F1')})
        self.f2 = self.feature({'a.c': lines('F2', *GATE['a.c'].split())})
        self.feats = {'f1': self.f1, 'f2': self.f2}
        self.fork = ft.integrate(self.g, self.gate,
                                 sorted(self.feats.items())).commit
        # Gate later fixes gate.c; the release takes that fix early.
        self.gate_fix = self.r.commit(
            dict(GATE, **{'gate.c': lines('g1', 'FIXED', 'g3')}),
            parent=self.gate, msg='12345 fix gate.c')

    def release_commit(self, parent, changes, msg):
        files = self.r.files(parent)
        files.update(changes)
        return self.r.commit(files, parent=parent, msg=msg)

    def test_backport_and_joyent_fix(self):
        r1 = self.release_commit(self.fork,
                                 {'gate.c': lines('g1', 'FIXED', 'g3')},
                                 '12345 fix gate.c')
        r2 = self.release_commit(r1, {'b.c': lines('b1', 'b2', 'b3', 'F1x')},
                                 'OS-1 fix f1')
        res = release.recut(self.g, self.feats, self.gate, self.fork, r2,
                            self.gate_fix)
        self.assertEqual(res.backports, [r1])
        self.assertEqual(res.routed, {r2: ['f1']})
        self.assertEqual(res.unrouted, [])
        self.assertEqual(self.r.tree(res.commit), self.r.tree(r2))
        self.assertTrue(res.equal)
        # The gate side is the gate commit plus the backport.
        self.assertEqual(self.r.files(res.gate)['gate.c'],
                         lines('g1', 'FIXED', 'g3'))
        self.assertEqual(self.r.git('rev-parse', res.gate + '^'), self.gate)

    def test_release_without_commits_is_the_integration(self):
        res = release.recut(self.g, self.feats, self.gate, self.fork,
                            self.fork, self.gate_fix)
        self.assertEqual(res.backports, [])
        self.assertTrue(res.equal)

    def test_commit_not_on_gate_is_not_a_backport(self):
        r1 = self.release_commit(self.fork,
                                 {'gate.c': lines('g1', 'OTHER', 'g3')},
                                 'local change to gate.c')
        res = release.recut(self.g, self.feats, self.gate, self.fork, r1,
                            self.gate_fix)
        self.assertEqual(res.backports, [])
        self.assertEqual([u.path for u in res.unrouted], ['gate.c'])
        self.assertFalse(res.equal)

    def test_features_from_integration(self):
        self.assertEqual(release.features_of(self.g, self.fork, self.gate),
                         self.feats)


if __name__ == '__main__':
    unittest.main()
