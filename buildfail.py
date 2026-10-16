#!/usr/bin/env python3
"""buildfail.py RESULTS: explain feature build failures by provider.

RESULTS holds feature-<name>/ directories from buildcheck.sh (result,
mail_msg, setup.log).  For each failing feature, pull the identifiers
and headers the compiler or linker complained about out of the error
lines, and name the other feature branches whose added lines define
them (same definition rules as deps.py).  Prints, per feature, the
measured providers and the complaints no feature explains.

Writes RESULTS/buildfail.json.
"""
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import deps as D  # noqa: E402

PATTERNS = [
    re.compile(r"'([A-Za-z_]\w*)' undeclared"),
    re.compile(r"implicit declaration of function '([A-Za-z_]\w*)'"),
    re.compile(r"unknown type name '([A-Za-z_]\w*)'"),
    re.compile(r"has no member named '([A-Za-z_]\w*)'"),
    re.compile(r"storage size of '([A-Za-z_]\w*)' isn't known"),
    re.compile(r"conflicting types for '([A-Za-z_]\w*)'"),
    re.compile(r"too (?:many|few) arguments to function '([A-Za-z_]\w*)'"),
    re.compile(r"^([A-Za-z_]\w*)\s+\S+\.o\b"),         # ld Undefined table
]
HEADER = re.compile(r'fatal error: ([\w/.-]+\.h): No such file')


def complaints(d):
    ids, hdrs, other = collections.Counter(), collections.Counter(), []
    text = ''
    for fn in ('mail_msg', 'setup.log'):
        p = os.path.join(d, fn)
        if os.path.exists(p):
            text += open(p, errors='replace').read()
    for l in text.split('\n'):
        if 'error' not in l and not re.match(r'^[A-Za-z_]\w*\s+\S+\.o\b', l):
            continue
        m = HEADER.search(l)
        if m:
            hdrs[m.group(1)] += 1
            continue
        hit = False
        for r in PATTERNS:
            for x in r.findall(l):
                ids[x] += 1
                hit = True
        if not hit and ': error:' in l:
            other.append(l.strip())
    return ids, hdrs, other


def main():
    res = sys.argv[1]
    names = sorted(n[len('feature-'):] for n in os.listdir(res)
                   if n.startswith('feature-'))
    failing = [n for n in names if 'status=0' not in
               open(os.path.join(res, 'feature-' + n, 'result')).read()]
    # who defines what, and which headers each feature adds
    defs, adds = {}, {}
    for n in names:
        d = set()
        for path, ls in D.added_lines(D.F.PREFIX + n).items():
            for l in ls:
                s = D.strip(l)
                for r in D.DEFS:
                    m = r.search(s)
                    if m:
                        d.add(m.group(1))
        defs[n] = d
        adds[n] = set(D.F.out('diff', '--name-only', '--diff-filter=A',
                              D.F.BASE, D.F.PREFIX + n).split('\n'))
    out = {}
    for n in failing:
        ids, hdrs, other = complaints(os.path.join(res, 'feature-' + n))
        prov = collections.defaultdict(set)
        unexplained = []
        for x in ids:
            by = [g for g in names if g != n and x in defs[g]]
            for g in by:
                prov[g].add(x)
            if not by:
                unexplained.append(x)
        for h in hdrs:
            by = [g for g in names if g != n and
                  any(p.endswith('/' + h) or p.endswith(h) for p in adds[g])]
            for g in by:
                prov[g].add(h)
            if not by:
                unexplained.append(h)
        out[n] = {'providers': {g: sorted(x) for g, x in prov.items()},
                  'unexplained': sorted(unexplained),
                  'other_errors': other[:5]}
        es = sorted(prov.items(), key=lambda kv: -len(kv[1]))
        print('%-16s needs %s' % (n, ', '.join('%s(%d)' % (g, len(x))
                                                 for g, x in es) or '-'))
        if unexplained:
            print('%16s unexplained: %s' % ('', ' '.join(sorted(unexplained)[:10])))
        if not ids and not hdrs and other:
            print('%16s other: %s' % ('', other[0][:110]))
    json.dump(out, open(os.path.join(res, 'buildfail.json'), 'w'), indent=1,
              sort_keys=True)


if __name__ == '__main__':
    main()
