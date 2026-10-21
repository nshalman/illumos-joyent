#!/usr/bin/env python3
"""Mechanical conflict resolvers: tier 3 of the escalation ladder.

A rebase conflict is resolved here only when every line in each
conflicting region is of a kind that can be merged as a set:

  copyright      copyright lines, in any comment style
  makefile-list  "<tab>name \\" entries of a Makefile list

The merge keeps gate's lines, drops lines the feature deleted, and puts
each line the feature added after its nearest preceding neighbour in
the feature's version (at the start of the region if it has none).
Master's own resolutions in 2026 follow this rule; see
replay/2026-10-21-small on the meta/state branch.

Anything else is left for a person.
"""
import os
import re

import ft

MARK = 40
COPYRIGHT = re.compile(rb'^\W*Copyright\b', re.I)
LIST_ENTRY = re.compile(rb'^\s+[^\s\\#=:]+\s*\\\r?\n?$')


def makefile(path):
    name = os.path.basename(path)
    return name.startswith('Makefile') or name.endswith('.mk')


RESOLVERS = [
    ('copyright', lambda path, line: bool(COPYRIGHT.match(line))),
    ('makefile-list',
     lambda path, line: makefile(path) and bool(LIST_ENTRY.match(line))),
]


def union(ours, base, theirs):
    """Merge one conflict region's lines as described above."""
    out = [l for l in ours if l in theirs or l not in base]
    for i, line in enumerate(theirs):
        if line in base or line in out:
            continue
        at = 0
        for prev in reversed(theirs[:i]):
            if prev in out:
                at = out.index(prev) + 1
                break
        out.insert(at, line)
    return out


def resolve_file(g, path, base, ours, theirs):
    """Resolve a conflicted file from its three blobs.

    Returns (merged blob, names of the resolvers used), or None if any
    region is beyond the resolvers.
    """
    r = g.run('merge-file', '-p', '--diff3', '--object-id',
              '--marker-size=%d' % MARK, ours, base, theirs,
              ok=range(0, 128))
    out, used = [], []
    region = None
    for line in ft.split_lines(r.stdout):
        if line.startswith(b'<' * MARK):
            region = {'ours': [], 'base': [], 'theirs': []}
            part = 'ours'
        elif region is not None and line.startswith(b'|' * MARK):
            part = 'base'
        elif region is not None and line.startswith(b'=' * MARK):
            part = 'theirs'
        elif region is not None and line.startswith(b'>' * MARK):
            lines = region['ours'] + region['base'] + region['theirs']
            name = next((n for n, ok in RESOLVERS
                         if all(ok(path, l) for l in lines)), None)
            if name is None:
                return None
            if name not in used:
                used.append(name)
            out.extend(union(region['ours'], region['base'],
                             region['theirs']))
            region = None
        elif region is not None:
            region[part].append(line)
        else:
            out.append(line)
    if region is not None:
        return None
    return g.hash_blob(b''.join(out)), used
