#!/usr/bin/env python3
"""Tests for resolve.py and its use in ft.rebase().

The cases mirror conflicts master resolved by hand in 2026: see
replay/2026-10-21-small on the meta/state branch.

  python3 test_resolve.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ft  # noqa: E402
import resolve  # noqa: E402
from test_ft import FtTest, lines  # noqa: E402

HEAD = ['/*', ' * CDDL HEADER', ' */', '/*',
        ' * Copyright 2010 Sun Microsystems, Inc.  All rights reserved.']
TAIL = [' */', '', 'int x;']


class UnionTest(unittest.TestCase):

    def test_insertions_at_the_same_place_keep_the_feature_first(self):
        self.assertEqual(resolve.union([b'gate\n'], [], [b'feature\n']),
                         [b'feature\n', b'gate\n'])

    def test_feature_addition_survives_gate_replacement(self):
        # corenote.c: gate bumps a year; the feature added a line above.
        ours = [b'Oxide 2026\n']
        base = [b'Oxide 2024\n']
        theirs = [b'OmniOS 2021\n', b'Oxide 2024\n']
        self.assertEqual(resolve.union(ours, base, theirs),
                         [b'OmniOS 2021\n', b'Oxide 2026\n'])

    def test_feature_deletion_is_kept(self):
        self.assertEqual(resolve.union([b'a\n', b'b\n', b'c\n'],
                                       [b'a\n', b'b\n'], [b'a\n']),
                         [b'a\n', b'c\n'])

    def test_feature_addition_goes_after_its_neighbour(self):
        self.assertEqual(resolve.union([b'a\n', b'g\n', b'b\n'],
                                       [b'a\n', b'b\n'],
                                       [b'a\n', b'b\n', b'f\n']),
                         [b'a\n', b'g\n', b'b\n', b'f\n'])

    def test_identical_addition_appears_once(self):
        self.assertEqual(resolve.union([b'x\n', b'g\n'], [], [b'x\n']),
                         [b'x\n', b'g\n'])


class ResolveFileTest(FtTest):

    def blobs(self, *texts):
        return [self.r.git('hash-object', '-w', '--stdin',
                           input=t.encode()) for t in texts]

    def test_copyright_conflict(self):
        base = lines(*HEAD, *TAIL)
        ours = lines(*HEAD, ' * Copyright 2026 Oxide Computer Company', *TAIL)
        theirs = lines(*HEAD, ' * Copyright (c) 2011, Joyent, Inc.', *TAIL)
        b, o, t = self.blobs(base, ours, theirs)
        out = resolve.resolve_file(self.g, 'zonestatd.c', b, o, t)
        self.assertIsNotNone(out)
        blob, names = out
        self.assertEqual(self.g.blob(blob).decode(), lines(
            *HEAD, ' * Copyright (c) 2011, Joyent, Inc.',
            ' * Copyright 2026 Oxide Computer Company', *TAIL))
        self.assertEqual(names, ['copyright'])

    def test_hash_comment_copyright(self):
        head = ['#', '# Copyright 2010 Sun Microsystems, Inc.']
        b, o, t = self.blobs(lines(*head, '# Copyright 2024 Oxide', 'x'),
                             lines(*head, '# Copyright 2026 Oxide', 'x'),
                             lines(*head, '# Copyright 2021 OmniOS',
                                   '# Copyright 2024 Oxide', 'x'))
        blob, _ = resolve.resolve_file(self.g, 'corenote.msg', b, o, t)
        self.assertEqual(self.g.blob(blob).decode(), lines(
            *head, '# Copyright 2021 OmniOS', '# Copyright 2026 Oxide', 'x'))

    def test_makefile_list_conflict(self):
        head = ['PROGS = \\']
        tail = ['\taligned_alloc \\', '\tascftime', '', 'all:']
        b, o, t = self.blobs(lines(*head, *tail),
                             lines(*head, '\taio_cancel \\', *tail),
                             lines(*head, '\tenv-OS-4089 \\', *tail))
        blob, names = resolve.resolve_file(self.g, 'tests/Makefile', b, o, t)
        self.assertEqual(self.g.blob(blob).decode(), lines(
            *head, '\tenv-OS-4089 \\', '\taio_cancel \\', *tail))
        self.assertEqual(names, ['makefile-list'])

    def test_list_entries_only_in_makefiles(self):
        b, o, t = self.blobs(lines('x', 'y'), lines('x', '\tg \\', 'y'),
                             lines('x', '\tf \\', 'y'))
        self.assertIsNone(resolve.resolve_file(self.g, 'foo.c', b, o, t))

    def test_other_code_is_left_for_a_person(self):
        b, o, t = self.blobs(lines(*HEAD, 'int a;', *TAIL),
                             lines(*HEAD, 'int b;', *TAIL),
                             lines(*HEAD, 'int c;', *TAIL))
        self.assertIsNone(resolve.resolve_file(self.g, 'x.c', b, o, t))

    def test_one_unresolvable_region_fails_the_file(self):
        base = lines(*HEAD, *TAIL, 'a', 'b', 'c', 'int a;')
        ours = lines(*HEAD, ' * Copyright 2026 Oxide', *TAIL, 'a', 'b', 'c',
                     'int b;')
        theirs = lines(*HEAD, ' * Copyright 2011 Joyent', *TAIL, 'a', 'b',
                       'c', 'int c;')
        b, o, t = self.blobs(base, ours, theirs)
        self.assertIsNone(resolve.resolve_file(self.g, 'x.c', b, o, t))


class RebaseWithResolversTest(FtTest):

    def test_resolved_conflict_is_not_reported_as_a_conflict(self):
        gate_files = {'x.c': lines(*HEAD, *TAIL)}
        gate = self.r.commit(gate_files, msg='gate')
        feat = self.r.commit({'x.c': lines(*HEAD, ' * Copyright 2011 Joyent',
                                           *TAIL)}, parent=gate, msg='f')
        new_gate = self.r.commit({'x.c': lines(*HEAD, ' * Copyright 2026 Ox',
                                               *TAIL)}, parent=gate, msg='g2')
        res = ft.rebase(self.g, gate, feat, new_gate,
                        resolve=resolve.resolve_file)
        self.assertEqual(res.conflicts, [])
        self.assertEqual(res.resolved, [(feat, 'x.c', ['copyright'])])
        self.assertEqual(self.r.files(res.tip)['x.c'], lines(
            *HEAD, ' * Copyright 2011 Joyent', ' * Copyright 2026 Ox', *TAIL))

    def test_unresolvable_conflict_still_reported(self):
        gate = self.r.commit({'x.c': lines('a', 'b', 'c')}, msg='gate')
        feat = self.r.commit({'x.c': lines('a', 'F', 'c')}, parent=gate)
        new_gate = self.r.commit({'x.c': lines('a', 'G', 'c')}, parent=gate)
        res = ft.rebase(self.g, gate, feat, new_gate,
                        resolve=resolve.resolve_file)
        self.assertEqual(res.conflicts, [(feat, ['x.c'])])
        self.assertEqual(res.resolved, [])


if __name__ == '__main__':
    unittest.main()
