#!/usr/bin/env python3
"""stackplan.py RESULTS: plan stacked builds for the failing features.

For each feature that failed alone (RESULTS/buildfail.json, from
buildfail.py), take every feature it may need, transitively: the static
edges in data/deps.json, the providers buildfail.py measured, and the
Makefile dependencies in EXTRA.  A stacked build merges the feature with
all of them; if it passes, the edges are sufficient, and if it fails,
some dependency is not known yet.

Prints one line per failing feature, "NAME PROVIDER...", smallest stack
first, for buildcheck.sh stacks.  With --cycles, prints instead each set
of features that need each other (a cycle), largest first.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Dependencies through Makefile lines that name several features'
# directories at once, which neither analysis sees (FINDINGS, "Compile
# checks").
EXTRA = [
    ('lx', 'hyprlofs'),             # uts/intel/Makefile.intel FS_KMODS
    ('platform-config', 'bhyve'),   # lib/brand/Makefile i386_SUBDIRS
    ('platform-config', 'lx'),
    ('platform-config', 'zone-brands'),  # same line: bhyve, builder brands
]


def closure(n, edges):
    need, todo = set(), [n]
    while todo:
        for g in edges.get(todo.pop(), ()):
            if g != n and g not in need:
                need.add(g)
                todo.append(g)
    return need


def main():
    cycles = '--cycles' in sys.argv
    res = [a for a in sys.argv[1:] if a != '--cycles'][0]
    deps = json.load(open(os.path.join(HERE, 'data', 'deps.json')))
    fails = json.load(open(os.path.join(res, 'buildfail.json')))
    edges = {}
    for n, d in deps.items():
        edges.setdefault(n, set()).update(d)
    for n, d in fails.items():
        edges.setdefault(n, set()).update(d['providers'])
    for n, g in EXTRA:
        edges.setdefault(n, set()).add(g)
    if cycles:
        need = dict((n, closure(n, edges)) for n in edges)
        seen, out = set(), []
        for n in sorted(edges):
            if n in seen:
                continue
            scc = set([n]) | set(g for g in need[n] if n in need.get(g, ()))
            seen |= scc
            if len(scc) > 1:
                out.append(sorted(scc))
        for scc in sorted(out, key=lambda c: (-len(c), c)):
            print(' '.join(scc))
        return
    plan = []
    for n in fails:
        need = closure(n, edges)
        plan.append((len(need), n, sorted(need)))
    for _, n, need in sorted(plan):
        print(' '.join([n] + need))


if __name__ == '__main__':
    main()
