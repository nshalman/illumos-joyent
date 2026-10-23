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


class CutTest(FtTest):
    """Master = gate + features; a release is cut, then fixed."""

    def setUp(self):
        super().setUp()
        self.f1 = self.feature({'b.c': lines('b1', 'b2', 'b3', 'F1')})
        self.f2 = self.feature({'a.c': lines('F2', *GATE['a.c'].split())})
        self.feats = {'f1': self.f1, 'f2': self.f2}
        self.master = ft.integrate(self.g, self.gate,
                                   sorted(self.feats.items())).commit

    def commit_on(self, parent, changes, msg):
        files = self.r.files(parent)
        files.update(changes)
        return self.r.commit(files, parent=parent, msg=msg)

    def test_cut_is_the_integration_and_matches_master(self):
        rel = release.cut(self.g, self.feats, self.gate, self.master)
        self.assertEqual(self.r.tree(rel), self.r.tree(self.master))
        self.assertEqual(release.features_of(self.g, rel, self.gate),
                         self.feats)

    def test_cut_refuses_when_features_lag_master(self):
        ahead = self.commit_on(self.master, {'b.c': lines('x')}, 'OS-1')
        with self.assertRaises(release.ReleaseError):
            release.cut(self.g, self.feats, self.gate, ahead)

    def test_fix_landed_on_master_first_passes(self):
        rel = release.cut(self.g, self.feats, self.gate, self.master)
        fix = {'b.c': lines('b1', 'b2', 'b3', 'F1 fixed')}
        on_master = self.commit_on(self.master, fix, 'OS-2 fix')
        on_release = self.commit_on(rel, fix, 'OS-2 fix (cherry picked)')
        res = release.merge_check(self.g, on_release, on_master, self.gate)
        self.assertTrue(res.ok)
        self.assertEqual(res.missing, [])

    def test_fix_only_on_the_release_is_reported(self):
        rel = release.cut(self.g, self.feats, self.gate, self.master)
        only = self.commit_on(rel, {'b.c': lines('b1', 'b2', 'b3', 'R')},
                              'OS-3 release-only fix')
        res = release.merge_check(self.g, only, self.master, self.gate)
        self.assertFalse(res.ok)
        self.assertEqual(res.missing, [(only, 'fix not on master')])

    def test_gate_backport_is_told_apart(self):
        rel = release.cut(self.g, self.feats, self.gate, self.master)
        files = dict(GATE, **{'gate.c': lines('g1', 'FIXED', 'g3')})
        gate_fix = self.r.commit(files, parent=self.gate, msg='12345 fix')
        back = self.commit_on(rel, {'gate.c': lines('g1', 'FIXED', 'g3')},
                              '12345 fix')
        res = release.merge_check(self.g, back, self.master, gate_fix)
        self.assertFalse(res.ok)
        self.assertEqual(res.missing,
                         [(back, 'gate backport not yet in master')])


    def test_command_cut_and_check(self):
        import subprocess
        here = os.path.dirname(os.path.abspath(__file__))
        for n, c in self.feats.items():
            self.r.git('update-ref', 'refs/heads/features/' + n, c)
        self.r.git('update-ref', 'refs/heads/master', self.master)

        def run(*args):
            return subprocess.run(
                [sys.executable, os.path.join(here, 'release.py')] +
                list(args) + ['--repo', self.r.dir],
                capture_output=True, text=True)
        p = run('cut', '--name', 'release-1', '--write')
        self.assertEqual(p.returncode, 0, p.stderr)
        rel = self.r.git('rev-parse', 'release-1')
        self.assertEqual(self.r.tree(rel), self.r.tree(self.master))
        p = run('check', '--release', 'release-1', '--gate-ref', self.gate)
        self.assertEqual(p.returncode, 0, p.stderr)
        only = self.commit_on(rel, {'b.c': lines('b1', 'b2', 'b3', 'R')},
                              'OS-3 release-only fix')
        self.r.git('update-ref', 'refs/heads/release-1', only)
        p = run('check', '--release', 'release-1', '--gate-ref', self.gate)
        self.assertEqual(p.returncode, 1)
        self.assertIn('fix not on master', p.stdout)

if __name__ == '__main__':
    unittest.main()
