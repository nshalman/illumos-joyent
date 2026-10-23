#!/usr/bin/env python3
"""Tests for intake.py: taking a new illumos-gate commit in.

  python3 test_intake.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ft  # noqa: E402
import intake  # noqa: E402
import resolve  # noqa: E402
from test_ft import GATE, FtTest, lines  # noqa: E402

A = GATE['a.c'].split()


class IntakeTest(FtTest):
    """Gate G0 -> G1 (clean) -> G2 (conflicts with f1) -> G3 (clean)."""

    def setUp(self):
        super().setUp()
        self.f1 = self.feature({'b.c': lines('b1', 'F1', 'b3')})
        self.f2 = self.feature({'a.c': lines(*A[:7], 'F2', *A[7:])})
        self.feats = {'f1': self.f1, 'f2': self.f2}
        self.g1 = self.gate_commit(self.gate, {'gate.c': lines('g1', 'G1',
                                                               'g3')})
        self.g2 = self.gate_commit(self.g1, {'b.c': lines('b1', 'GATE',
                                                          'b3')})
        self.g3 = self.gate_commit(self.g2, {'a.c': lines('A1', *A[1:])})

    def gate_commit(self, parent, changes):
        files = self.r.files(parent)
        files.update(changes)
        return self.r.commit(files, parent=parent, msg='gate')

    def test_clean_intake(self):
        res = intake.intake(self.g, self.feats, self.gate, self.g1)
        self.assertTrue(res.ok)
        self.assertEqual(res.conflicts, {})
        self.assertEqual(res.held, [])
        files = self.r.files(res.integration)
        self.assertEqual(files['gate.c'], lines('g1', 'G1', 'g3'))
        self.assertIn('F1', files['b.c'])
        for n in self.feats:
            self.assertEqual(self.r.git('rev-parse', res.features[n] + '^'),
                             self.g1)

    def test_conflict_is_not_ok(self):
        res = intake.intake(self.g, self.feats, self.gate, self.g2)
        self.assertFalse(res.ok)
        self.assertEqual(sorted(res.conflicts), ['f1'])

    def test_first_bad_gate_commit(self):
        self.assertEqual(intake.first_bad(self.g, self.feats, self.gate,
                                          self.g3), self.g2)
        self.assertIsNone(intake.first_bad(self.g, self.feats, self.gate,
                                           self.g1))

    def test_take_in_up_to_the_last_good_commit(self):
        res = intake.take_in(self.g, self.feats, self.gate, self.g3)
        self.assertEqual(res.reached, self.g1)
        self.assertEqual(res.bad, self.g2)
        self.assertEqual(res.stuck, ['f1'])
        self.assertTrue(res.taken.ok)
        self.assertEqual(res.taken.gate, self.g1)
        # The stuck feature's attempt at the bad commit, for a person.
        cand = res.candidates['f1']
        self.assertEqual(self.r.git('rev-parse', cand + '^'), self.g2)

    def test_take_in_all_the_way(self):
        res = intake.take_in(self.g, self.feats, self.gate, self.g1)
        self.assertEqual(res.reached, self.g1)
        self.assertIsNone(res.bad)
        self.assertEqual(res.stuck, [])

    def test_check_failure_is_bisected_too(self):
        # A gate commit that breaks the build, with no conflict.
        g1b = self.gate_commit(self.g1, {'gate.c': lines('g1', 'BREAK',
                                                         'g3')})
        g1c = self.gate_commit(g1b, {'a.c': lines('A1', *A[1:])})

        def check(integration):
            return 'BREAK' not in self.r.files(integration)['gate.c']
        res = intake.take_in(self.g, self.feats, self.gate, g1c, check=check)
        self.assertEqual(res.reached, self.g1)
        self.assertEqual(res.bad, g1b)
        self.assertEqual(res.stuck, [])
        self.assertTrue(res.check_failed)

    def test_nothing_taken_when_the_first_commit_is_bad(self):
        feats = intake.intake(self.g, self.feats, self.gate, self.g1).features
        res = intake.take_in(self.g, feats, self.g1, self.g2)
        self.assertEqual(res.reached, self.g1)
        self.assertEqual(res.bad, self.g2)
        self.assertIsNone(res.taken)

    def candidate(self, fixed):
        """f1's candidate at G2, as intake left it, or fixed by a person."""
        res = intake.take_in(self.g, self.feats, self.gate, self.g3)
        cand = res.candidates['f1']
        if fixed:
            files = self.r.files(cand)
            files['b.c'] = lines('b1', 'GATE F1', 'b3')
            cand = self.r.commit(files, parent=cand, msg='fix f1 at G2')
        self.r.git('update-ref',
                   'refs/heads/intake/%s/features/f1' % self.g2, cand)
        return cand

    def test_unfixed_candidate_is_not_picked_up(self):
        self.candidate(fixed=False)
        self.assertEqual(intake.fixed_candidates(
            self.g, self.feats, self.gate, self.g3, 'refs/heads/intake/'), {})

    def test_fixed_candidate_is_picked_up(self):
        cand = self.candidate(fixed=True)
        fixed = intake.fixed_candidates(self.g, self.feats, self.gate,
                                        self.g3, 'refs/heads/intake/')
        self.assertEqual(fixed, {'f1': (self.g2, cand)})
        res = intake.take_in(self.g, self.feats, self.gate, self.g3,
                             fixed=fixed)
        self.assertIsNone(res.bad)
        self.assertEqual(res.reached, self.g3)
        files = self.r.files(res.taken.features['f1'])
        self.assertEqual(files['b.c'], lines('b1', 'GATE F1', 'b3'))
        self.assertEqual(files['a.c'], lines('A1', *A[1:]))
        # The person's fix, rebased onto G3 as a commit of its own.
        tip = res.taken.features['f1']
        self.assertEqual(self.r.git('log', '-1', '--format=%s', tip),
                         'fix f1 at G2')
        self.assertEqual(self.r.git('merge-base', tip, self.g3), self.g3)

    def test_fixed_candidate_waits_for_its_gate_commit(self):
        cand = self.candidate(fixed=True)
        self.assertEqual(intake.fixed_candidates(
            self.g, self.feats, self.gate, self.g1, 'refs/heads/intake/'), {})
        fixed = {'f1': (self.g2, cand)}
        res = intake.intake(self.g, self.feats, self.gate, self.g1,
                            fixed=fixed)
        self.assertTrue(res.ok)
        self.assertEqual(self.r.files(res.features['f1'])['b.c'],
                         lines('b1', 'F1', 'b3'))

    def test_candidate_not_on_its_gate_commit_is_ignored(self):
        files = self.r.files(self.g3)
        files['b.c'] = lines('b1', 'GATE F1', 'b3')
        wrong = self.r.commit(files, parent=self.g3, msg='fix on G3')
        self.r.git('update-ref',
                   'refs/heads/intake/%s/features/f1' % self.g2, wrong)
        self.assertEqual(intake.fixed_candidates(
            self.g, self.feats, self.gate, self.g3, 'refs/heads/intake/'), {})

    def test_feature_gate_absorbs_retires(self):
        fix = {'gate.c': lines('g1', 'FIX', 'g3')}
        feats = dict(self.feats, fix=self.feature(fix))
        g1 = self.gate_commit(self.gate, fix)
        res = intake.intake(self.g, feats, self.gate, g1)
        self.assertEqual(res.retired, ['fix'])
        self.assertNotIn('fix', res.features)

    def test_resolver_is_used(self):
        head = ['/*', ' * Copyright 2010 Sun', ' */', 'x']
        gate = self.r.commit({'c.c': lines(*head)}, msg='gate')
        f = self.r.commit({'c.c': lines(*head[:2], ' * Copyright Joyent',
                                        *head[2:])}, parent=gate)
        g1 = self.r.commit({'c.c': lines(*head[:2], ' * Copyright Oxide',
                                         *head[2:])}, parent=gate)
        res = intake.intake(self.g, {'f': f}, gate, g1,
                            resolve=resolve.resolve_file)
        self.assertTrue(res.ok)
        self.assertEqual(res.resolved, {'f': [['c.c', ['copyright']]]})


class GateMergeTest(FtTest):

    def test_gate_merge_has_the_integration_tree(self):
        f = self.feature({'b.c': lines('b1', 'F', 'b3')})
        master = ft.integrate(self.g, self.gate, [('f', f)]).commit
        files = dict(GATE, **{'gate.c': lines('g1', 'G1', 'g3')})
        g1 = self.r.commit(files, parent=self.gate, msg='gate')
        res = intake.intake(self.g, {'f': f}, self.gate, g1)
        merge = intake.write_gate_merge(self.g, master, g1, res.integration)
        self.assertEqual(self.r.tree(merge), self.r.tree(res.integration))
        self.assertEqual(self.r.git('log', '-1', '--format=%P', merge).split(),
                         [master, g1])

    def test_gate_merge_must_descend_from_the_gate(self):
        f = self.feature({'b.c': lines('b1', 'F', 'b3')})
        master = ft.integrate(self.g, self.gate, [('f', f)]).commit
        other = self.r.commit(GATE, msg='unrelated')
        with self.assertRaises(intake.IntakeError):
            intake.write_gate_merge(self.g, master, other, master)


class CommandTest(FtTest):
    """intake.py end to end, on refs in a throwaway repository."""

    def run_intake(self, *args):
        import subprocess
        here = os.path.dirname(os.path.abspath(__file__))
        return subprocess.run(
            [sys.executable, os.path.join(here, 'intake.py'),
             '--repo', self.r.dir] + list(args),
            capture_output=True, text=True)

    def setUp(self):
        super().setUp()
        f1 = self.feature({'b.c': lines('b1', 'F1', 'b3')})
        f2 = self.feature({'a.c': lines(*A[:7], 'F2', *A[7:])})
        self.r.git('update-ref', 'refs/heads/features/f1', f1)
        self.r.git('update-ref', 'refs/heads/features/f2', f2)
        master = ft.integrate(self.g, self.gate,
                              [('f1', f1), ('f2', f2)]).commit
        self.r.git('update-ref', 'refs/heads/master', master)
        files = self.r.files(self.gate)
        files['gate.c'] = lines('g1', 'G1', 'g3')
        self.g1 = self.r.commit(files, parent=self.gate, msg='gate 1')
        files['b.c'] = lines('b1', 'GATE', 'b3')
        self.g2 = self.r.commit(files, parent=self.g1, msg='gate 2')

    def test_write_takes_gate_in_and_leaves_a_candidate(self):
        import tempfile
        old_master = self.r.git('rev-parse', 'master')
        with tempfile.TemporaryDirectory() as d:
            p = self.run_intake('--to', self.g2, '--write', '--report', d)
            issue = open(os.path.join(d, 'issues', 'f1.md')).read()
        self.assertIn('# Gate intake: f1 stuck at', issue)
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertIn('stuck     f1', p.stdout)
        master = self.r.git('rev-parse', 'master')
        self.assertEqual(self.r.git('log', '-1', '--format=%P', master)
                         .split(), [old_master, self.g1])
        for n in ('f1', 'f2'):
            self.assertEqual(self.r.git('rev-parse', 'features/%s^' % n),
                             self.g1)
        cand = 'refs/heads/intake/%s/features/f1' % self.g2
        self.assertEqual(self.r.git('rev-parse', cand + '^'), self.g2)
        out = ft.integrate(self.g, self.g1, sorted(
            intake.features_at(self.g, 'refs/heads/features/').items()))
        self.assertEqual(self.r.tree(out.commit), self.r.tree(master))

    def test_watched_ticket_landing_retires_and_marks_the_feature(self):
        import metadata
        fix = {'gate.c': lines('g1', 'FIX', 'g3')}
        f3 = self.feature(fix)
        self.r.git('update-ref', 'refs/heads/features/upstream-8391', f3)
        master = ft.integrate(self.g, self.r.git('rev-parse', 'master'),
                              [('upstream-8391', f3)]).commit
        self.r.git('update-ref', 'refs/heads/master', master)
        state = self.r.commit({'README.md': 'state\n'}, msg='state')
        self.r.git('update-ref', 'refs/heads/meta/state', state)
        metadata.save(self.g, 'refs/heads/meta/state', {
            'f1': {'Feature': 'f1'}, 'f2': {'Feature': 'f2'},
            'upstream-8391': metadata.stub('upstream-8391', 'x',
                                           tickets=['8391'])}, 'meta\n')
        files = self.r.files(self.gate)
        files.update(fix)
        g = self.r.commit(files, parent=self.gate, msg='8391 mr_sas lockup')
        p = self.run_intake('--to', g, '--write')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('upstream  8391 landed in', p.stdout)
        self.assertIn('upstream-8391 retired', p.stdout)
        meta = metadata.load(self.g, 'refs/heads/meta/state')
        self.assertEqual(meta['upstream-8391']['Upstream'], 'landed')
        self.assertEqual(meta['upstream-8391']['Retired'], g)
        self.assertEqual(meta['f1'], {'Feature': 'f1'})
        self.assertEqual(self.r.git('for-each-ref',
                                    'refs/heads/features/upstream-8391'), '')

    def test_watched_ticket_landing_without_retiring_asks_for_review(self):
        import metadata
        state = self.r.commit({'README.md': 'state\n'}, msg='state')
        self.r.git('update-ref', 'refs/heads/meta/state', state)
        metadata.save(self.g, 'refs/heads/meta/state', {
            'f1': {'Feature': 'f1', 'Upstream-Tickets': '9001'},
            'f2': {'Feature': 'f2'}}, 'meta\n')
        files = self.r.files(self.gate)
        files['gate.c'] = lines('g1', 'G1', 'g3')
        g = self.r.commit(files, parent=self.gate, msg='9001 part of f1')
        p = self.run_intake('--to', g)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('upstream  9001 landed in', p.stdout)
        self.assertIn('f1 still differs from gate: review', p.stdout)

    def test_write_picks_up_a_fixed_candidate_and_removes_it(self):
        self.run_intake('--to', self.g2, '--write')
        ref = 'refs/heads/intake/%s/features/f1' % self.g2
        files = self.r.files(ref)
        files['b.c'] = lines('b1', 'GATE F1', 'b3')
        fix = self.r.commit(files, parent=self.r.git('rev-parse', ref),
                            msg='fix f1 at gate 2')
        self.r.git('update-ref', ref, fix)
        p = self.run_intake('--to', self.g2, '--write')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('picked up f1 fixed at %s' % self.g2[:11], p.stdout)
        self.assertEqual(self.r.git('rev-parse', 'features/f1'), fix)
        self.assertEqual(self.r.git('for-each-ref', ref), '')
        master = self.r.git('rev-parse', 'master')
        self.assertEqual(self.r.files(master)['b.c'],
                         lines('b1', 'GATE F1', 'b3'))

    def test_features_at_can_leave_some_out(self):
        self.r.git('update-ref', 'refs/heads/features/tooling', self.gate)
        self.assertEqual(sorted(intake.features_at(
            self.g, 'refs/heads/features/', exclude=['tooling'])),
            ['f1', 'f2'])

    def test_refuses_when_features_do_not_give_master(self):
        files = self.r.files('master')
        files['gate.c'] = lines('not', 'dispatched')
        ahead = self.r.commit(files, parent=self.r.git('rev-parse',
                                                       'master'))
        self.r.git('update-ref', 'refs/heads/master', ahead)
        p = self.run_intake('--to', self.g1, '--write')
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('dispatch has not caught up', p.stderr)
        self.assertEqual(self.r.git('rev-parse', 'master'), ahead)


if __name__ == '__main__':
    unittest.main()
