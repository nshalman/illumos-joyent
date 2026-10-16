#!/usr/bin/env python3
"""stackplan.py RESULTS: plan stacked builds for the failing features.

For each feature that failed alone (RESULTS/buildfail.json, from
buildfail.py), take every feature it may need, transitively: the static
edges in data/deps.json plus the providers buildfail.py measured.  A
stacked build merges the feature with all of them; if it passes, the
edges are sufficient, and if it fails, some dependency is not known yet.

Prints one line per failing feature, "NAME PROVIDER...", smallest stack
first, for buildcheck.sh stacks.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    res = sys.argv[1]
    deps = json.load(open(os.path.join(HERE, 'data', 'deps.json')))
    fails = json.load(open(os.path.join(res, 'buildfail.json')))
    edges = {}
    for n, d in deps.items():
        edges.setdefault(n, set()).update(d)
    for n, d in fails.items():
        edges.setdefault(n, set()).update(d['providers'])
    plan = []
    for n in fails:
        need, todo = set(), [n]
        while todo:
            for g in edges.get(todo.pop(), ()):
                if g != n and g not in need:
                    need.add(g)
                    todo.append(g)
        plan.append((len(need), n, sorted(need)))
    for _, n, need in sorted(plan):
        print(' '.join([n] + need))


if __name__ == '__main__':
    main()
