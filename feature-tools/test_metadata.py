#!/usr/bin/env python3
"""Tests for metadata.py: the features' metadata on meta/state.

  python3 test_metadata.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ft  # noqa: E402
import metadata  # noqa: E402
from test_ft import GATE, FtTest, lines  # noqa: E402

LX = """Feature: lx
Description: The lx brand: Linux binary compatibility in a zone.
 A second line of description.
Owner: someone@example.com
Depends: brand-ops, hyprlofs
Upstream: keep
"""


class ParseTest(unittest.TestCase):

    def test_parse_and_format_round_trip(self):
        m = metadata.parse(LX)
        self.assertEqual(m['Feature'], 'lx')
        self.assertEqual(m['Description'],
                         'The lx brand: Linux binary compatibility in a '
                         'zone.\nA second line of description.')
        self.assertEqual(metadata.depends(m), ['brand-ops', 'hyprlofs'])
        self.assertEqual(metadata.render(m), LX)

    def test_lists_may_be_empty(self):
        m = metadata.parse('Feature: x\nDepends:\n')
        self.assertEqual(metadata.depends(m), [])
        self.assertEqual(metadata.tickets(m), [])

    def test_stub(self):
        m = metadata.stub('upstream-8391', 'Carried until gate lands 8391.',
                          tickets=['8391'])
        self.assertEqual(m['Upstream'], 'upstream')
        self.assertEqual(metadata.tickets(m), ['8391'])
        self.assertEqual(metadata.parse(metadata.render(m)), m)


class OrderTest(unittest.TestCase):

    def meta(self, deps):
        return {n: {'Feature': n, 'Depends': ', '.join(d)}
                for n, d in deps.items()}

    def test_dependencies_come_first(self):
        meta = self.meta({'lx': ['brand-ops', 'hyprlofs'], 'brand-ops': [],
                          'hyprlofs': ['brand-ops'], 'zfs': []})
        self.assertEqual(metadata.order(meta, ['zfs', 'lx', 'hyprlofs',
                                               'brand-ops']),
                         ['brand-ops', 'hyprlofs', 'lx', 'zfs'])

    def test_a_cycle_is_kept_together_by_name(self):
        meta = self.meta({'boot': ['dboot'], 'dboot': ['boot'], 'a': []})
        self.assertEqual(metadata.order(meta, ['dboot', 'boot', 'a']),
                         ['a', 'boot', 'dboot'])

    def test_cycles(self):
        meta = self.meta({'boot': ['dboot'], 'dboot': ['boot'],
                          'vnd': ['datalink'], 'datalink': ['vnd'], 'a': []})
        self.assertEqual(metadata.cycles(meta),
                         [['boot', 'dboot'], ['datalink', 'vnd']])


class CheckTest(unittest.TestCase):

    def test_problems(self):
        meta = {'lx': {'Feature': 'lx', 'Depends': 'brand-ops, gone'},
                'brand-ops': {'Feature': 'brand-ops', 'Depends': ''},
                'old': {'Feature': 'old', 'Upstream': 'landed'},
                'stray': {'Feature': 'stray'}}
        problems = metadata.check(meta, ['lx', 'brand-ops', 'nometa'])
        self.assertEqual(problems, [
            'feature nometa has no metadata',
            'feature lx depends on gone, which is not a feature',
            'metadata for stray, but no such feature branch'])


class RetireTest(unittest.TestCase):

    def test_retired_features_are_marked_landed(self):
        meta = {'upstream-8391': metadata.stub('upstream-8391', 'x',
                                               tickets=['8391']),
                'lx': {'Feature': 'lx'}}
        out = metadata.retire(meta, ['upstream-8391', 'gone'], 'abc123')
        self.assertEqual(list(out), ['upstream-8391'])
        self.assertEqual(out['upstream-8391']['Upstream'], 'landed')
        self.assertEqual(out['upstream-8391']['Retired'], 'abc123')
        self.assertEqual(meta['upstream-8391']['Upstream'], 'upstream')

class WatchTest(FtTest):

    def test_ticket_landing_in_gate_is_flagged(self):
        meta = {'upstream-8391': metadata.stub('upstream-8391', 'x',
                                               tickets=['8391']),
                'lx': {'Feature': 'lx'}}
        g1 = self.r.commit(dict(GATE, **{'gate.c': lines('x')}),
                           parent=self.gate, msg='8391 mr_sas lockup')
        g2 = self.r.commit(dict(GATE, **{'gate.c': lines('y')}), parent=g1,
                           msg='18391 something else')
        self.assertEqual(metadata.watch(self.g, meta, self.gate, g2),
                         [('upstream-8391', '8391', g1)])


class StateTest(FtTest):

    def test_load_and_save_on_a_state_branch(self):
        state = self.r.commit({'README.md': 'state\n'}, msg='state')
        self.r.git('update-ref', 'refs/heads/meta/state', state)
        metadata.save(self.g, 'refs/heads/meta/state',
                      {'lx': metadata.parse(LX)}, 'Add lx\n')
        meta = metadata.load(self.g, 'refs/heads/meta/state')
        self.assertEqual(list(meta), ['lx'])
        self.assertEqual(meta['lx']['Owner'], 'someone@example.com')
        files = self.r.files('refs/heads/meta/state')
        self.assertEqual(files['features/lx'], LX)
        self.assertEqual(files['README.md'], 'state\n')


    def test_merge_chains_follow_the_metadata(self):
        self.assertFalse(metadata.use_order(self.g, 'refs/heads/meta/state'))
        feats = {'brand-ops': 'B', 'lx': 'L', 'aaa': 'A'}
        self.assertEqual([n for n, _ in ft.chain(feats)],
                         ['aaa', 'brand-ops', 'lx'])
        state = self.r.commit({'README.md': 'state\n'}, msg='state')
        self.r.git('update-ref', 'refs/heads/meta/state', state)
        metadata.save(self.g, 'refs/heads/meta/state',
                      {'lx': {'Feature': 'lx', 'Depends': ''},
                       'aaa': {'Feature': 'aaa', 'Depends': 'lx'}}, 'm\n')
        try:
            self.assertTrue(metadata.use_order(self.g,
                                               'refs/heads/meta/state'))
            self.assertEqual([n for n, _ in ft.chain(feats)],
                             ['brand-ops', 'lx', 'aaa'])
        finally:
            ft.set_order(None)

if __name__ == '__main__':
    unittest.main()
