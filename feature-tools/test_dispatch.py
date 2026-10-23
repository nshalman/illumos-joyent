#!/usr/bin/env python3
"""Tests for dispatch.py: routing landed commits into the features.

  python3 test_dispatch.py
"""
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dispatch  # noqa: E402
import ft  # noqa: E402
from test_ft import GATE, FtTest, lines  # noqa: E402

A = GATE['a.c'].split()


class Base(FtTest):
    """Master = gate + f1 + f2; commits land on it one at a time."""

    def setUp(self):
        super().setUp()
        self.f1 = self.feature({'b.c': lines('b1', 'F1', 'b3')})
        self.f2 = self.feature({'a.c': lines(*A[:7], 'F2', *A[7:])})
        self.feats = {'f1': self.f1, 'f2': self.f2}
        self.master = ft.integrate(self.g, self.gate,
                                   sorted(self.feats.items())).commit

    def land(self, changes, msg='OS-1 change', parent=None):
        parent = parent or self.master
        files = self.r.files(parent)
        files.update(changes)
        return self.r.commit(files, parent=parent, msg=msg, author='Dev')


class DispatchTest(Base):

    def test_dispatch_routes_and_matches(self):
        c = self.land({'b.c': lines('b1', 'F1 fixed', 'b3')})
        res = dispatch.dispatch(self.g, self.feats, self.gate, c)
        self.assertTrue(res.equal)
        self.assertEqual(res.routed, ['f1'])
        self.assertEqual(res.unrouted, [])
        self.assertEqual(self.r.git('log', '-1', '--format=%an|%s',
                                    res.features['f1']), 'Dev|OS-1 change')

    def test_trailer_places_what_rules_cannot(self):
        c = self.land({'new.c': lines('n')},
                      msg='OS-2 add new.c\n\nFeature: f2\n')
        res = dispatch.dispatch(self.g, self.feats, self.gate, c)
        self.assertTrue(res.equal)
        self.assertEqual(res.routed, ['f2'])

    def test_unplaceable_change_is_reported(self):
        c = self.land({'new.c': lines('n')})
        res = dispatch.dispatch(self.g, self.feats, self.gate, c)
        self.assertFalse(res.equal)
        self.assertEqual([u.path for u in res.unrouted], ['new.c'])

    def test_decisions_file_entries_apply(self):
        c = self.land({'new.c': lines('n')})
        res = dispatch.dispatch(self.g, self.feats, self.gate, c,
                                decide={'new.c': 'f1'})
        self.assertTrue(res.equal)
        self.assertEqual(res.routed, ['f1'])

    def test_placement_lists_paths_per_feature(self):
        c = self.land({'b.c': lines('b1', 'F1 fixed', 'b3'),
                       'a.c': lines(*A[:7], 'F2 fixed', *A[7:])})
        res = dispatch.dispatch(self.g, self.feats, self.gate, c)
        self.assertEqual(dispatch.placement(self.g, self.feats, res.features),
                         {'f1': ['b.c'], 'f2': ['a.c']})

    def test_record_on_the_dispatched_commit(self):
        c = self.land({'b.c': lines('b1', 'F1 fixed', 'b3')})
        res = dispatch.dispatch(self.g, self.feats, self.gate, c)
        rec = dispatch.write_record(self.g, c, c, res.integration, ['f1'])
        self.assertEqual(self.r.git('log', '-1', '--format=%P', rec).split(),
                         [c, res.integration])
        self.assertEqual(self.r.tree(rec), self.r.tree(c))
        self.assertIn('Dispatched-commit: %s' % c,
                      self.r.git('log', '-1', '--format=%B', rec))

    def test_record_refuses_a_mismatched_integration(self):
        c = self.land({'b.c': lines('b1', 'F1 fixed', 'b3')})
        with self.assertRaises(dispatch.DispatchError):
            dispatch.write_record(self.g, c, c, self.master, ['f1'])

    def test_record_when_master_has_moved(self):
        c = self.land({'b.c': lines('b1', 'F1 fixed', 'b3')})
        res = dispatch.dispatch(self.g, self.feats, self.gate, c)
        later = self.land({'gate.c': lines('g1', 'later', 'g3')}, parent=c)
        rec = dispatch.write_record(self.g, later, c, res.integration,
                                    ['f1'])
        self.assertEqual(self.r.git('log', '-1', '--format=%P', rec).split(),
                         [later, res.integration])
        self.assertEqual(self.r.tree(rec), self.r.tree(later))
        self.assertIn('Dispatched-commit: %s' % c,
                      self.r.git('log', '-1', '--format=%B', rec))

    def test_pending_commits(self):
        c1 = self.land({'b.c': lines('b1', 'F1 fixed', 'b3')})
        res = dispatch.dispatch(self.g, self.feats, self.gate, c1)
        rec = dispatch.write_record(self.g, c1, c1, res.integration, ['f1'])
        c2 = self.land({'a.c': lines(*A[:7], 'F2 x', *A[7:])}, parent=rec)
        c3 = self.land({'a.c': lines(*A[:7], 'F2 y', *A[7:])}, parent=c2)
        self.assertEqual(dispatch.pending(self.g, c3), [c2, c3])
        self.assertEqual(dispatch.pending(self.g, rec), [])


    def test_pending_stops_at_a_gate_intake(self):
        import intake
        files = dict(GATE, **{'gate.c': lines('g1', 'G1', 'g3')})
        g1 = self.r.commit(files, parent=self.gate, msg='gate 1')
        res = intake.intake(self.g, self.feats, self.gate, g1)
        merge = intake.write_gate_merge(self.g, self.master, g1,
                                        res.integration)
        self.assertIn('Gate-intake: %s' % g1,
                      self.r.git('log', '-1', '--format=%B', merge))
        c = self.land({'b.c': lines('b1', 'F1 x', 'b3')}, parent=merge)
        self.assertEqual(dispatch.pending(self.g, c), [c])

class CommandTest(Base):
    """dispatch.py end to end, on refs in a throwaway repository."""

    def setUp(self):
        super().setUp()
        for n, c in self.feats.items():
            self.r.git('update-ref', 'refs/heads/features/' + n, c)
        self.r.git('update-ref', 'refs/heads/master', self.master)

    def run_dispatch(self, *args):
        here = os.path.dirname(os.path.abspath(__file__))
        return subprocess.run(
            [sys.executable, os.path.join(here, 'dispatch.py')] +
            list(args) + ['--repo', self.r.dir],
            capture_output=True, text=True)

    def test_dry_run_reports_and_changes_nothing(self):
        head = self.land({'b.c': lines('b1', 'F1 fixed', 'b3')})
        p = self.run_dispatch('dry-run', '--head', head)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('f1: b.c', p.stdout)
        self.assertEqual(self.r.git('rev-parse', 'features/f1'), self.f1)

    def test_dry_run_asks_for_a_trailer(self):
        head = self.land({'new.c': lines('n')})
        p = self.run_dispatch('dry-run', '--head', head)
        self.assertEqual(p.returncode, 1)
        self.assertIn('new.c', p.stdout)
        self.assertIn('Feature:', p.stdout)

    def test_land_pending_commits(self):
        c1 = self.land({'b.c': lines('b1', 'F1 fixed', 'b3')})
        c2 = self.land({'a.c': lines(*A[:7], 'F2 fixed', *A[7:])}, parent=c1)
        self.r.git('update-ref', 'refs/heads/master', c2)
        p = self.run_dispatch('land', '--write')
        self.assertEqual(p.returncode, 0, p.stderr)
        master = self.r.git('rev-parse', 'master')
        self.assertEqual(dispatch.pending(self.g, master), [])
        self.assertEqual(self.r.tree(master), self.r.tree(c2))
        feats = {n: self.r.git('rev-parse', 'features/' + n)
                 for n in ('f1', 'f2')}
        out = ft.integrate(self.g, self.gate, sorted(feats.items()))
        self.assertEqual(self.r.tree(out.commit), self.r.tree(master))
        # Dispatch only adds commits: the features fast-forward.
        self.assertEqual(self.r.git('merge-base', '--is-ancestor', self.f1,
                                    feats['f1']), '')

    def test_land_stops_at_an_unplaceable_commit(self):
        import tempfile
        c1 = self.land({'new.c': lines('n')})
        self.r.git('update-ref', 'refs/heads/master', c1)
        with tempfile.TemporaryDirectory() as d:
            p = self.run_dispatch('land', '--write', '--report', d)
            issue = open(os.path.join(d, 'issues', c1[:11] + '.md')).read()
        self.assertEqual(p.returncode, 1)
        self.assertEqual(self.r.git('rev-parse', 'master'), c1)
        self.assertEqual(self.r.git('rev-parse', 'features/f1'), self.f1)
        self.assertIn('new.c', issue)
        self.assertIn('Dispatch failed', issue)


if __name__ == '__main__':
    unittest.main()
