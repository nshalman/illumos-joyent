#!/usr/bin/env python3
"""Tests for replay.py, on a small made-up master history.

  python3 test_replay.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ft  # noqa: E402
import manifest  # noqa: E402
import replay  # noqa: E402
import resolve  # noqa: E402
from test_ft import GATE, FtTest, lines  # noqa: E402

A = GATE['a.c'].split()


class ReplayTest(FtTest):
    """Master: gate merges and joyent commits on top of two features."""

    def setUp(self):
        super().setUp()
        self.f1 = self.feature({'a.c': lines('a1', 'a2', 'F1a', 'F1b', *A[2:]),
                                'b.c': lines('b1', 'b2', 'b3', 'F1 only')})
        self.f2 = self.feature({'a.c': lines(*A[:7], 'F2a', *A[7:])})
        self.feats = {'f1': self.f1, 'f2': self.f2}
        self.m0 = ft.integrate(self.g, self.gate,
                               sorted(self.feats.items())).commit

    def gate_merge(self, master, old_gate, changes, resolved=None):
        """Merge a new gate commit (OLD_GATE plus CHANGES) into MASTER.

        RESOLVED gives master's files after the merge; by default,
        MASTER's files with CHANGES laid over them.
        """
        files = self.r.files(old_gate)
        files.update(changes)
        new_gate = self.r.commit(files, parent=old_gate, msg='gate')
        out = self.r.files(master)
        out.update(resolved if resolved is not None else changes)
        tree = self.r.tree(self.r.commit(out, msg='tree'))
        merge = self.g.commit_tree(tree, [master, new_gate],
                                   '[illumos-gate merge]\n')
        return merge, new_gate

    def joyent(self, master, changes, msg='OS-9 change'):
        out = self.r.files(master)
        out.update(changes)
        return self.r.commit(out, parent=master, msg=msg, author='Dev')

    def test_replays_clean_history(self):
        m1, g1 = self.gate_merge(self.m0, self.gate,
                                 {'gate.c': lines('g1', 'G2', 'g3')})
        m2 = self.joyent(m1, {'b.c': lines('b1', 'b2', 'b3', 'F1 fixed')})
        res = replay.replay(self.g, self.feats, self.gate, self.m0, m2)
        self.assertEqual([s.kind for s in res.steps], ['gate', 'joyent'])
        self.assertTrue(all(s.equal for s in res.steps))
        self.assertEqual(res.steps[0].conflicts, {})
        self.assertEqual(res.steps[0].routed, [])
        self.assertEqual(res.steps[1].routed, ['f1'])
        self.assertEqual(res.gate, g1)
        self.assertEqual(self.r.git('log', '-1', '--format=%an|%s',
                                    res.features['f1']), 'Dev|OS-9 change')
        self.assertEqual(self.r.git('rev-parse', res.features['f1'] + '~2'),
                         g1)

    def test_conflict_resolved_as_master_did(self):
        # Gate changes a2, right next to f1's lines: the rebase conflicts,
        # and master's merge took both sides.
        resolved = {'a.c': lines('a1', 'A2', 'F1a', 'F1b', *A[2:7], 'F2a',
                                 *A[7:])}
        m1, g1 = self.gate_merge(
            self.m0, self.gate,
            {'a.c': lines('a1', 'A2', *A[2:])}, resolved=resolved)
        res = replay.replay(self.g, self.feats, self.gate, self.m0, m1)
        step = res.steps[0]
        self.assertTrue(step.equal)
        self.assertEqual(sorted(step.conflicts), ['f1'])
        self.assertEqual(step.routed, ['f1'])
        self.assertEqual(self.r.files(res.features['f1'])['a.c'],
                         lines('a1', 'A2', 'F1a', 'F1b', *A[2:]))

    def test_semantic_fix_in_a_clean_merge_is_routed(self):
        # The merge is clean, but master also changed f2's line in it.
        resolved = {'gate.c': lines('g1', 'G2', 'g3'),
                    'a.c': lines(*A[:2], 'F1a', 'F1b', *A[2:7], 'F2a fixed',
                                 *A[7:])}
        m1, _ = self.gate_merge(self.m0, self.gate,
                                {'gate.c': lines('g1', 'G2', 'g3')},
                                resolved=resolved)
        res = replay.replay(self.g, self.feats, self.gate, self.m0, m1)
        self.assertEqual(res.steps[0].conflicts, {})
        self.assertEqual(res.steps[0].routed, ['f2'])
        self.assertTrue(res.steps[0].equal)

    def test_stops_at_a_change_it_cannot_route(self):
        m1 = self.joyent(self.m0, {'new.c': lines('n')})
        m2 = self.joyent(m1, {'b.c': lines('b1', 'b2', 'b3', 'x')})
        res = replay.replay(self.g, self.feats, self.gate, self.m0, m2)
        self.assertEqual(len(res.steps), 1)
        self.assertEqual([u.path for u in res.steps[0].unrouted], ['new.c'])
        self.assertFalse(res.steps[0].equal)

    def test_decisions_route_what_rules_cannot(self):
        m1 = self.joyent(self.m0, {'new.c': lines('n')})
        res = replay.replay(self.g, self.feats, self.gate, self.m0, m1,
                            decide={'new.c': 'f2'})
        self.assertTrue(res.steps[0].equal)
        self.assertEqual(res.steps[0].routed, ['f2'])

    def history(self, gate_files, feat_files, new_gate_files, merged_files):
        """Master on one feature F, then one gate merge into it."""
        gate = self.r.commit(gate_files, msg='gate')
        feat = self.r.commit(feat_files, parent=gate, msg='feature')
        m0 = ft.integrate(self.g, gate, [('f', feat)]).commit
        new_gate = self.r.commit(new_gate_files, parent=gate, msg='gate 2')
        tree = self.r.tree(self.r.commit(merged_files, msg='tree'))
        m1 = self.g.commit_tree(tree, [m0, new_gate], '[illumos-gate merge]\n')
        return gate, {'f': feat}, m0, m1

    def test_resolver_takes_a_copyright_conflict(self):
        head = ['/*', ' * Copyright 2010 Sun', ' */', 'a', 'b', 'c']
        gate, feats, m0, m1 = self.history(
            {'c.c': lines(*head[:2], *head[2:])},
            {'c.c': lines(*head[:2], ' * Copyright 2011 Joyent', *head[2:])},
            {'c.c': lines(*head[:2], ' * Copyright 2026 Oxide', *head[2:])},
            {'c.c': lines(*head[:2], ' * Copyright 2011 Joyent',
                          ' * Copyright 2026 Oxide', *head[2:])})
        res = replay.replay(self.g, feats, gate, m0, m1,
                            resolve=resolve.resolve_file)
        step = res.steps[0]
        self.assertTrue(step.equal)
        self.assertEqual(step.conflicts, {})
        self.assertEqual(step.resolved, {'f': [['c.c', ['copyright']]]})
        self.assertEqual(step.routed, [])

    def test_manifest_follows_gate(self):
        pkg = 'usr/src/pkg/manifests/SUNWcs.man1.inc'
        old = 'file path=usr/share/man/man1/a.1\n'
        new = old + 'file path=usr/share/man/man1/b.1\n'
        mf = 'f usr/share/man/man1/a.1 0444 root bin\n'
        gate, feats, m0, m1 = self.history(
            {pkg: old}, {pkg: old, 'manifest': mf}, {pkg: new},
            {pkg: new, 'manifest': mf + 'f usr/share/man/man1/b.1 0444 '
             'root bin\n'})
        res = replay.replay(self.g, feats, gate, m0, m1,
                            sync=manifest.sync_feature)
        step = res.steps[0]
        self.assertTrue(step.equal)
        self.assertEqual(step.synced, {'f': {'added': 1}})
        self.assertEqual(step.routed, [])

    def test_start_must_match(self):
        other = self.joyent(self.m0, {'b.c': lines('x')})
        with self.assertRaises(replay.ReplayError):
            replay.replay(self.g, self.feats, self.gate, other, other)


if __name__ == '__main__':
    unittest.main()
