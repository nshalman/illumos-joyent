#!/usr/bin/env python3
"""Tests for ft.py, run against small throwaway git repositories.

  python3 test_ft.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ft  # noqa: E402

ENV = dict(os.environ,
           GIT_AUTHOR_NAME='Author', GIT_AUTHOR_EMAIL='author@example.com',
           GIT_COMMITTER_NAME='Committer',
           GIT_COMMITTER_EMAIL='committer@example.com',
           GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1')


class Repo:
    """A scratch repository with helpers to commit whole trees."""

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix='ft-test-')
        self.git('init', '-q', '-b', 'main')

    def close(self):
        shutil.rmtree(self.dir)

    def git(self, *a, input=None):
        r = subprocess.run(['git', '-C', self.dir] + list(a), env=ENV,
                           input=input, capture_output=True, check=True)
        return r.stdout.decode().strip()

    def commit(self, files, parent=None, msg='commit', author=None):
        """Commit a tree holding exactly FILES ({path: text}) on PARENT."""
        idx = os.path.join(self.dir, '.git', 'ft-test-index')
        if os.path.exists(idx):
            os.remove(idx)
        env = dict(ENV, GIT_INDEX_FILE=idx)
        for path, text in files.items():
            blob = subprocess.run(
                ['git', '-C', self.dir, 'hash-object', '-w', '--stdin'],
                input=text.encode(), env=env, capture_output=True,
                check=True).stdout.decode().strip()
            subprocess.run(['git', '-C', self.dir, 'update-index', '--add',
                            '--cacheinfo', '100644,%s,%s' % (blob, path)],
                           env=env, check=True)
        tree = subprocess.run(['git', '-C', self.dir, 'write-tree'], env=env,
                              capture_output=True,
                              check=True).stdout.decode().strip()
        args = ['commit-tree', tree, '-m', msg]
        if parent:
            args += ['-p', parent]
        cenv = dict(ENV)
        if author:
            cenv['GIT_AUTHOR_NAME'] = author
        return subprocess.run(['git', '-C', self.dir] + args, env=cenv,
                              capture_output=True,
                              check=True).stdout.decode().strip()

    def files(self, rev):
        out = {}
        for path in self.git('ls-tree', '-r', '--name-only', rev).split():
            out[path] = self.git('show', '%s:%s' % (rev, path)) + '\n'
        return out

    def tree(self, rev):
        return self.git('rev-parse', rev + '^{tree}')


def lines(*a):
    return ''.join(x + '\n' for x in a)


GATE = {
    'a.c': lines('a1', 'a2', 'a3', 'a4', 'a5', 'a6', 'a7', 'a8', 'a9'),
    'b.c': lines('b1', 'b2', 'b3'),
    'gate.c': lines('g1', 'g2', 'g3'),
}


class FtTest(unittest.TestCase):

    def setUp(self):
        self.r = Repo()
        self.g = ft.Git(self.r.dir)
        self.gate = self.r.commit(GATE, msg='gate')

    def tearDown(self):
        self.r.close()

    def feature(self, changes, msg='feature', parent=None):
        files = dict(GATE)
        files.update(changes)
        return self.r.commit(files, parent=parent or self.gate, msg=msg)


class RebaseTest(FtTest):

    def test_clean_rebase_keeps_message_and_author(self):
        f = self.r.commit(dict(GATE, **{'b.c': lines('b1', 'B2', 'b3')}),
                          parent=self.gate, msg='OS-1 fix b', author='Dev')
        new_gate = self.r.commit(dict(GATE, **{'gate.c': lines('g1', 'G2',
                                                               'g3')}),
                                 parent=self.gate, msg='gate 2')
        res = ft.rebase(self.g, self.gate, f, new_gate)
        self.assertEqual(res.conflicts, [])
        self.assertEqual(self.r.files(res.tip)['b.c'], lines('b1', 'B2', 'b3'))
        self.assertEqual(self.r.files(res.tip)['gate.c'],
                         lines('g1', 'G2', 'g3'))
        self.assertEqual(self.r.git('log', '-1', '--format=%an|%s', res.tip),
                         'Dev|OS-1 fix b')
        self.assertEqual(self.r.git('rev-parse', res.tip + '^'), new_gate)

    def test_rebase_replays_every_commit(self):
        f1 = self.feature({'b.c': lines('b1', 'B2', 'b3')}, msg='one')
        f2 = self.r.commit(dict(GATE, **{'b.c': lines('b1', 'B2', 'B3')}),
                           parent=f1, msg='two')
        new_gate = self.r.commit(dict(GATE, **{'a.c': lines('A1', *GATE[
            'a.c'].split()[1:])}), parent=self.gate, msg='gate 2')
        res = ft.rebase(self.g, self.gate, f2, new_gate)
        self.assertEqual(self.r.git('log', '--format=%s',
                                    '%s..%s' % (new_gate, res.tip)),
                         'two\none')

    def test_conflict_is_reported_and_feature_side_kept(self):
        f = self.feature({'b.c': lines('b1', 'FEATURE', 'b3')})
        new_gate = self.r.commit(dict(GATE, **{'b.c': lines('b1', 'GATE',
                                                            'b3')}),
                                 parent=self.gate, msg='gate 2')
        res = ft.rebase(self.g, self.gate, f, new_gate)
        self.assertEqual(res.conflicts, [(f, ['b.c'])])
        self.assertEqual(self.r.files(res.tip)['b.c'],
                         lines('b1', 'FEATURE', 'b3'))


class IntegrateTest(FtTest):

    def test_merge_chain_combines_features(self):
        f1 = self.feature({'a.c': lines('a1', 'X', *GATE['a.c'].split()[2:])})
        f2 = self.feature({'b.c': lines('b1', 'b2', 'b3', 'Y')})
        res = ft.integrate(self.g, self.gate, [('f1', f1), ('f2', f2)])
        self.assertEqual(res.conflicts, [])
        files = self.r.files(res.commit)
        self.assertIn('X', files['a.c'])
        self.assertIn('Y', files['b.c'])
        parents = self.r.git('log', '-1', '--format=%P', res.commit).split()
        self.assertEqual(parents[1], f2)

    def test_identical_copyright_change_merges_cleanly(self):
        f1 = self.feature({'a.c': lines('COPYRIGHT', *GATE['a.c'].split()[1:]),
                           'b.c': lines('b1', 'b2', 'b3', 'Y')})
        f2 = self.feature({'a.c': lines('COPYRIGHT', *GATE['a.c'].split()[1:8],
                                        'Z')})
        res = ft.integrate(self.g, self.gate, [('f1', f1), ('f2', f2)])
        self.assertEqual(res.conflicts, [])
        self.assertEqual(self.r.files(res.commit)['a.c'],
                         lines('COPYRIGHT', *GATE['a.c'].split()[1:8], 'Z'))

    def test_conflicting_features_are_reported(self):
        f1 = self.feature({'b.c': lines('b1', 'ONE', 'b3')})
        f2 = self.feature({'b.c': lines('b1', 'TWO', 'b3')})
        res = ft.integrate(self.g, self.gate, [('f1', f1), ('f2', f2)])
        self.assertEqual(res.conflicts, [('f2', ['b.c'])])


class LineMapTest(FtTest):

    def blob(self, *a):
        return self.r.git('hash-object', '-w', '--stdin', input=lines(*a)
                          .encode())

    def test_insert_delete_and_change(self):
        a = self.blob('1', '2', '3', '4', '5', '6')
        b = self.blob('1', 'new', '2', '4', 'FIVE', '6', '7')
        # 1->1, 2->3, 3 deleted, 4->4, 5 changed, 6->6
        self.assertEqual(ft.line_map(self.g, a, b),
                         {1: 1, 2: 3, 4: 4, 6: 6})

    def test_identical(self):
        a = self.blob('x', 'y')
        self.assertEqual(ft.line_map(self.g, a, a), {1: 1, 2: 2})


class RouteTest(FtTest):
    """route() must make the integration equal the target tree."""

    def setUp(self):
        super().setUp()
        a = GATE['a.c'].split()
        # f1 owns lines after a2, f2 owns lines after a7; both touch the
        # first line (a replicated copyright line).
        self.f1 = self.feature({
            'a.c': lines('C', 'a2', 'F1a', 'F1b', *a[2:]),
            'b.c': lines('b1', 'b2', 'b3', 'F1 only')})
        self.f2 = self.feature({
            'a.c': lines('C', *a[1:7], 'F2a', 'F2b', *a[7:])})
        self.feats = {'f1': self.f1, 'f2': self.f2}
        self.integ = ft.integrate(self.g, self.gate, sorted(
            self.feats.items())).commit

    def target(self, changes):
        files = self.r.files(self.integ)
        files.update(changes)
        return self.r.commit(files, msg='target')

    def route_and_check(self, target):
        res = ft.route(self.g, self.gate, self.feats, self.r.tree(target),
                       msg='routed')
        new = dict(self.feats, **res.commits)
        out = ft.integrate(self.g, self.gate, sorted(new.items()))
        self.assertEqual(out.conflicts, [])
        self.assertEqual(self.r.tree(out.commit), self.r.tree(target))
        return res

    def test_single_owner_file_goes_to_its_feature(self):
        res = self.route_and_check(self.target(
            {'b.c': lines('b1', 'b2', 'b3', 'F1 fixed')}))
        self.assertEqual(sorted(res.commits), ['f1'])
        self.assertEqual(res.unrouted, [])

    def test_shared_file_change_goes_to_the_owner_of_the_lines(self):
        files = self.r.files(self.integ)
        text = files['a.c'].replace('F2b\n', 'F2b fixed\n')
        res = self.route_and_check(self.target({'a.c': text}))
        self.assertEqual(sorted(res.commits), ['f2'])
        self.assertEqual(self.r.files(res.commits['f2'])['a.c'],
                         self.r.files(self.f2)['a.c'].replace('F2b\n',
                                                              'F2b fixed\n'))

    def test_insertion_next_to_feature_lines_goes_to_that_feature(self):
        text = self.r.files(self.integ)['a.c'].replace('F1b\n', 'F1b\nF1c\n')
        res = self.route_and_check(self.target({'a.c': text}))
        self.assertEqual(sorted(res.commits), ['f1'])

    def test_replicated_line_change_goes_to_every_owner(self):
        text = self.r.files(self.integ)['a.c'].replace('C\n', 'C2\n', 1)
        res = self.route_and_check(self.target({'a.c': text}))
        self.assertEqual(sorted(res.commits), ['f1', 'f2'])

    def test_commit_carries_message_and_author(self):
        res = ft.route(self.g, self.gate, self.feats, self.r.tree(
            self.target({'b.c': lines('b1', 'b2', 'b3', 'x')})),
            msg='OS-2 fix',
            author=('Dev', 'dev@example.com', '1700000000 +0000'))
        self.assertEqual(self.r.git('log', '-1', '--format=%an|%s',
                                    res.commits['f1']), 'Dev|OS-2 fix')
        self.assertEqual(self.r.git('rev-parse', res.commits['f1'] + '^'),
                         self.f1)

    def test_change_to_untouched_gate_file_is_unrouted(self):
        target = self.target({'gate.c': lines('g1', 'CHANGED', 'g3')})
        res = ft.route(self.g, self.gate, self.feats, self.r.tree(target),
                       msg='routed')
        self.assertEqual(res.commits, {})
        self.assertEqual([u.path for u in res.unrouted], ['gate.c'])

    def test_moved_feature_line_follows_its_feature(self):
        # Gate moved code into a file no feature touches, and the
        # feature's line went with it (fm-topo's LDLIBS in 17974).
        target = self.target({'gate.c': lines('g1', 'g2', 'F1 only', 'g3')})
        res = self.route_and_check(target)
        self.assertEqual(sorted(res.commits), ['f1'])
        self.assertEqual(res.unrouted, [])

    def test_lines_matching_several_features_stay_unrouted(self):
        target = self.target({'gate.c': lines('g1', 'C', 'g3')})
        res = ft.route(self.g, self.gate, self.feats, self.r.tree(target),
                       msg='routed')
        self.assertEqual([u.path for u in res.unrouted], ['gate.c'])

    def test_new_file_is_unrouted(self):
        target = self.target({'new.c': lines('n')})
        res = ft.route(self.g, self.gate, self.feats, self.r.tree(target),
                       msg='routed')
        self.assertEqual([u.path for u in res.unrouted], ['new.c'])

    def test_decision_routes_an_unrouted_path(self):
        target = self.target({'new.c': lines('n'),
                              'gate.c': lines('g1', 'CHANGED', 'g3')})
        res = ft.route(self.g, self.gate, self.feats, self.r.tree(target),
                       msg='routed', decide={'new.c': 'f2', 'gate.c': 'f1'})
        self.assertEqual(res.unrouted, [])
        self.assertEqual(self.r.files(res.commits['f2'])['new.c'], lines('n'))
        self.assertEqual(self.r.files(res.commits['f1'])['gate.c'],
                         lines('g1', 'CHANGED', 'g3'))

    def header_file(self):
        """x.c, with features f1 and f2 owning lines far from its header."""
        body = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j']
        head = ['/*', ' * Copyright 2010 Sun', ' */']
        gate = self.r.commit(dict(GATE, **{'x.c': lines(*head, *body)}),
                             msg='gate')
        f1 = self.r.commit(dict(GATE, **{'x.c': lines(
            *head, *body[:4], 'E1', *body[5:])}), parent=gate)
        f2 = self.r.commit(dict(GATE, **{'x.c': lines(
            *head, *body[:9], 'J2')}), parent=gate)
        return gate, {'f1': f1, 'f2': f2}, head, body

    def test_copyright_line_goes_with_the_rest_of_the_file(self):
        # OS-8748 added an OmniOS copyright line beside gate's own, and
        # changed f1's code in the same file.
        gate, feats, head, body = self.header_file()
        target = self.r.commit(dict(GATE, **{'x.c': lines(
            *head[:2], ' * Copyright 2026 OmniOS', head[2], *body[:4],
            'E1 fixed', *body[5:9], 'J2')}), msg='target')
        res = ft.route(self.g, gate, feats, self.r.tree(target), msg='m')
        self.assertEqual(res.unrouted, [])
        self.assertEqual(sorted(res.commits), ['f1'])
        out = ft.integrate(self.g, gate, sorted(dict(feats,
                                                     **res.commits).items()))
        self.assertEqual(self.r.tree(out.commit), self.r.tree(target))

    def test_other_ownerless_hunks_stay_unrouted(self):
        gate, feats, head, body = self.header_file()
        target = self.r.commit(dict(GATE, **{'x.c': lines(
            *head, 'A', *body[1:4], 'E1 fixed', *body[5:9], 'J2')}),
            msg='target')
        res = ft.route(self.g, gate, feats, self.r.tree(target), msg='m')
        self.assertEqual([u.path for u in res.unrouted], ['x.c'])

    def test_ownership_is_by_position_not_by_text(self):
        # 57dd2952050: master removed brand-ops' 'int error;' in exec.c;
        # lx adds an identical line elsewhere in the file and must not
        # be counted as an owner.
        body = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k']
        gate = self.r.commit(dict(GATE, **{'y.c': lines(*body)}), msg='gate')
        f1 = self.r.commit(dict(GATE, **{'y.c': lines(
            'a', 'int error;', *body[1:])}), parent=gate)
        f2 = self.r.commit(dict(GATE, **{'y.c': lines(
            *body[:8], 'F2 start', 'int error;', 'F2 end', *body[8:])}),
            parent=gate)
        feats = {'f1': f1, 'f2': f2}
        target = self.r.commit(dict(GATE, **{'y.c': lines(
            'a', 'int error;', *body[1:8], 'F2 start', 'F2 end',
            *body[8:])}), msg='target')
        res = ft.route(self.g, gate, feats, self.r.tree(target), msg='m')
        self.assertEqual(res.unrouted, [])
        self.assertEqual(sorted(res.commits), ['f2'])

    def test_decision_can_start_a_new_feature(self):
        # A fix carried ahead of gate (18158) starts its own feature.
        target = self.target({'gate.c': lines('g1', 'FIX', 'g3')})
        res = ft.route(self.g, self.gate, self.feats, self.r.tree(target),
                       msg='18158 fix', decide={'gate.c': 'upstream-18158'})
        self.assertEqual(sorted(res.commits), ['upstream-18158'])
        new = res.commits['upstream-18158']
        self.assertEqual(self.r.git('rev-parse', new + '^'), self.gate)
        out = ft.integrate(self.g, self.gate,
                           sorted(dict(self.feats, **res.commits).items()))
        self.assertEqual(self.r.tree(out.commit), self.r.tree(target))

    def test_decision_does_not_override_owners(self):
        # 0821a720ccf: a decision for a file features now touch must not
        # send the whole change to the decided feature.
        text = self.r.files(self.integ)['a.c'].replace('F2b\n', 'F2b x\n')
        target = self.target({'a.c': text})
        res = ft.route(self.g, self.gate, self.feats, self.r.tree(target),
                       msg='m', decide={'a.c': 'f1'})
        self.assertEqual(sorted(res.commits), ['f2'])

    def test_deleting_a_single_owner_file(self):
        f3 = self.feature({'only3.c': lines('x')})
        self.feats['f3'] = f3
        self.integ = ft.integrate(self.g, self.gate, sorted(
            self.feats.items())).commit
        files = self.r.files(self.integ)
        del files['only3.c']
        res = self.route_and_check(self.r.commit(files, msg='target'))
        self.assertEqual(sorted(res.commits), ['f3'])


if __name__ == '__main__':
    unittest.main()
