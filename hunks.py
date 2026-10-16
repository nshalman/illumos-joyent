#!/usr/bin/env python3
"""Exploration: how separable is the delta at hunk level?

For every changed file, split `git diff -U0 BASE JOYENT` into hunks and
give each changed line a feature (a bucket): '+' lines by the home of the
ticket that wrote them (per-line blame), '-' lines by the commit that
removed them (text match, as deletions.py).  Lines with no attributable
home fall back to the file's whole-file bucket.  Reports how many hunks
and lines are single-feature, then, for files touched by several
features, builds each feature's version of the file (BASE plus only its
hunks; a mixed hunk goes to its dominant feature) and three-way merges
them with `git merge-file` to see whether the result is JOYENT's file.

Before that, hunks are moved so each feature's files compile: hunks in
one C function (or within GAP lines outside functions) go together; an
include-only hunk from a feature with no other change in the file
follows the file's other changes; a Makefile hunk of
bare list entries is split per entry, each going to the feature that
owns the file or subdirectory it names, and a mapfile hunk of symbols
per symbol, each going to the feature adding its definition; then HUNK_OVERRIDES apply.

  hunks.py            summary
  hunks.py -v         also list files with mixed hunks or merge conflicts

Writes data/hunks.json: per file, a list of hunks
[old_start, old_len, new_start, new_len, {feature: lines}, {sha: lines}]
for features.py.
"""
import collections
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import classify as C  # noqa: E402
from overrides import HUNK_OVERRIDES  # noqa: E402

DATA = C.DATA
ILLUMOS = os.environ.get('ILLUMOS', os.path.expanduser('~/Workspace/illumos'))
refs = dict(l.strip().split('=') for l in open(DATA + '/refs'))
BASE, JOYENT = refs['BASE'], refs['JOYENT']

# Whole-file buckets that are not features; their lines are re-homed by
# ticket, falling back to the file's bucket only when nothing else fits.
NON_FEATURE = ('integration', 'integration-pkg', 'integration-drivers',
               'integration-checks', 'integration-manifest',
               'copyright-residue', 'misc')


def git(*a, inp=None):
    return subprocess.run(['git', '-C', ILLUMOS] + list(a), input=inp,
                          capture_output=True, text=True,
                          errors='replace').stdout


def show(rev, path):
    r = subprocess.run(['git', '-C', ILLUMOS, 'show', rev + ':' + path],
                       capture_output=True)
    return r.stdout if r.returncode == 0 else None


def hunks_of(path):
    """[(old_start, old_lines[], new_start, new_lines[])] for -U0 diff."""
    out = []
    cur = None
    for l in git('diff', '--no-ext-diff', '--no-renames', '-U0', BASE, JOYENT,
                 '--', path).splitlines():
        m = re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', l)
        if m:
            cur = [int(m.group(1)), [], int(m.group(3)), []]
            out.append(cur)
        elif cur and l.startswith('-') and not l.startswith('---'):
            cur[1].append(l[1:])
        elif cur and l.startswith('+') and not l.startswith('+++'):
            cur[3].append(l[1:])
    return out


def line_blame(path):
    """{new line number: sha} for JOYENT's version (BOUNDARY as 'B')."""
    res = {}
    sha = None
    for l in git('blame', '--line-porcelain', BASE + '..' + JOYENT, '--',
                 path).splitlines():
        m = re.match(r'([0-9a-f]{40}) \d+ (\d+)', l)
        if m:
            sha, ln = m.group(1), int(m.group(2))
        elif l.startswith('boundary'):
            sha = 'B'
        elif l.startswith('\t'):
            res[ln] = sha
    return res


def removers(path, gone):
    """{removed line text: [shas that removed it]} (non-merge commits)."""
    res = collections.defaultdict(list)
    sha = None
    for l in git('log', '--no-merges', '--full-history', '--no-renames',
                 '--format=@@%H', '-p', '-U0', '--no-ext-diff',
                 BASE + '..' + JOYENT, '--', path).splitlines():
        if l.startswith('@@') and not l.startswith('@@ '):
            sha = l[2:]
        elif l.startswith('-') and not l.startswith('---') and sha:
            if l[1:] in gone:
                res[l[1:]].append(sha)
    return res


FUNC_START = re.compile(rb'^[A-Za-z_][^;{}]*\(')
GAP = 3     # hunks this close outside functions belong together


def function_spans(base):
    """[(first, last)] 1-based BASE line ranges of C function bodies: a
    column-0 line with '(' followed within 12 lines by a column-0 '{',
    through the next column-0 '}'."""
    lines = base.split(b'\n')
    spans = []
    i = 0
    while i < len(lines):
        if FUNC_START.match(lines[i]):
            for j in range(i + 1, min(i + 13, len(lines))):
                if lines[j].startswith(b'{'):
                    for k in range(j + 1, len(lines)):
                        if lines[k].startswith(b'}'):
                            spans.append((i + 1, k + 1))
                            i = k
                            break
                    break
                if lines[j].startswith(b'}') or lines[j].rstrip().endswith(b';'):
                    break
        i += 1
    return spans


def cohere(res, base, is_c):
    """Give hunks that belong together one feature: hunks inside the same
    C function body, or hunks at most GAP lines apart outside functions.
    A group goes to the feature owning most of its lines.  Splitting such
    hunks between features leaves files that do not compile."""
    spans = function_spans(base) if is_c else []

    def span_of(h):
        lo = h[0] if h[1] else h[0] + 1     # pure insert goes after line h[0]
        hi = h[0] + h[1] - 1 if h[1] else lo
        for a, b in spans:
            if lo <= b and hi >= a:
                return (a, b)
        return None

    groups, cur, key, end = [], None, None, None
    for h in sorted(res, key=lambda h: h[0]):
        k = span_of(h)
        start = h[0]
        if cur is not None and ((k is not None and k == key) or
                                (k is None and key is None and
                                 start - end <= GAP)):
            cur.append(h)
        else:
            cur = [h]
            groups.append(cur)
        key, end = k, h[0] + h[1]
    for g in groups:
        if len(g) < 2:
            continue
        tot = collections.Counter()
        for h in g:
            tot.update(h[4])
        feat = sorted(tot.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        for h in g:
            h[4] = {feat: sum(h[4].values())}


INCLUDE = re.compile(r'^\s*#\s*include\b')
LIST_LINE = re.compile(r'^\s*([A-Za-z0-9_.+/-]+)\s*\\?\s*$')
SYM_LINE = re.compile(r'^\s*([A-Za-z_]\w*)\s*(\{[^}]*\})?\s*;\s*$')
# a C function definition in illumos style: the name starts the line
C_DEF = re.compile(r'^([A-Za-z_]\w*)\(')


def split_lists(f, hs):
    """Yield (old_start, old, new_start, new, kind).  A hunk that only
    adds or only removes list entries is split into one-line hunks, so
    each entry can go to the feature it belongs to: in a Makefile,
    subdirectory entries (kind 'list:ENTRY'); in a mapfile, exported
    symbols (kind 'sym:NAME')."""
    base = os.path.basename(f)
    if base.startswith('Makefile'):
        rx, tag = LIST_LINE, 'list:'
    elif base.startswith('mapfile'):
        rx, tag = SYM_LINE, 'sym:'
    else:
        rx = None
    for os_, old, ns, new in hs:
        lines = new if not old else old if not new else None
        if rx and lines and all(rx.match(l) for l in lines):
            for i, l in enumerate(lines):
                e = rx.match(l).group(1)
                if new:
                    yield os_, [], ns + i, [l], (tag + e, os_)
                else:
                    yield os_ + i, [l], ns, [], (tag + e, os_)
        else:
            yield os_, old, ns, new, None


def assign_list_entries(per_file):
    """Give each Makefile list entry to the feature owning most changed
    lines in the file or under the subdirectory it names, and each mapfile
    symbol to the feature adding its definition."""
    owner = collections.defaultdict(collections.Counter)
    for f, hs in per_file.items():
        for h in hs:
            if h[7] is None or h[7] in ('include', 'override'):
                owner[f].update(h[4])
    # who adds each C function's definition
    defs = collections.defaultdict(collections.Counter)
    for f, hs in per_file.items():
        if not f.endswith('.c'):
            continue
        for h in hs:
            for l in h[6][h[1]:]:
                m = C_DEF.match(l)
                if m:
                    defs[m.group(1)].update({dominant(h): 1})
    for f, hs in per_file.items():
        d = os.path.dirname(f)
        for h in hs:
            kind = h[7] or ''
            if kind.startswith('sym:'):
                c = defs.get(kind[4:])
            elif kind.startswith('list:'):
                sub = d + '/' + kind[5:]
                c = collections.Counter()
                for dd, cc in owner.items():
                    if dd == sub or dd.startswith(sub + '/'):
                        c.update(cc)
            else:
                continue
            if not c:
                c = h[8]
            feat = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
            h[4] = {feat: sum(h[4].values())}


def dominant(h):
    """The feature owning most of a hunk's lines (ties: alphabetical)."""
    return sorted(h[4].items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def main():
    verbose = '-v' in sys.argv
    commits, delta, blame, assign, how, votes, tb = C.classify()
    status = dict((f, st) for st, f in delta)

    # Ticket homes, as build.py: the feature bucket holding >= 60% of the
    # ticket's lines outside non-feature buckets, and at least as many as
    # it has in non-feature buckets.
    home = collections.defaultdict(collections.Counter)
    nonfeat = collections.Counter()
    for f, b in assign.items():
        for t, n in blame[f].items():
            if b in NON_FEATURE:
                nonfeat[t] += n
            else:
                home[t][b] += n
    home = dict((t, c.most_common(1)[0][0]) for t, c in home.items()
                if t != 'MERGE' and
                c.most_common(1)[0][1] >= 0.6 * sum(c.values()) and
                c.most_common(1)[0][1] >= nonfeat[t])

    def feature(sha, f):
        if sha in commits:
            t = commits[sha][0]
            if t in home:
                return home[t]
        b = assign[f]
        return b

    def analyse(f):
        hs = hunks_of(f)
        lb = line_blame(f) if status[f] != 'D' else {}
        gone = set(l for h in hs for l in h[1])
        rm = removers(f, gone) if gone else {}
        res = []
        for os_, old, ns, new, kind in split_lists(f, hs):
            c = collections.Counter()
            who = collections.Counter()     # sha -> lines, for credit
            for i in range(len(new)):
                sha = lb.get(ns + i)
                c[feature(sha, f)] += 1
                if sha and sha != 'B':
                    who[sha] += 1
            for l in old:
                shas = rm.get(l)
                c[feature(shas[0] if shas else None, f)] += 1
                if shas:
                    who[shas[0]] += 1
            if kind is None and all(INCLUDE.match(l) or not l.strip()
                                    for l in old + new) and \
                    any(INCLUDE.match(l) for l in old + new):
                kind = 'include'
            res.append([os_, len(old), ns, len(new), dict(c), dict(who),
                        old + new, kind])
        # a list entry nothing owns keeps the vote of the hunk it came from
        parent = collections.defaultdict(collections.Counter)
        for h in res:
            if isinstance(h[7], tuple):
                parent[h[7][1]].update(h[4])
        for h in res:
            if isinstance(h[7], tuple):
                h.append(dict(parent[h[7][1]]))
                h[7] = h[7][0]
        plain = [h for h in res if h[7] is None]
        if status[f] == 'M' and len(plain) > 1:
            cohere(plain, show(BASE, f) or b'', f.endswith('.c'))
        # an include-only hunk from a feature with no other change here
        # serves the file's other changes
        others = collections.Counter()
        for h in plain:
            others.update(h[4])
        for h in res:
            if h[7] == 'include' and others and dominant(h) not in others:
                feat = sorted(others.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
                h[4] = {feat: sum(h[4].values())}
        for h in res:
            for p, rx, feat in HUNK_OVERRIDES:
                if p == f and any(re.search(rx, l) for l in h[6]):
                    h[4] = {feat: sum(h[4].values())}
                    h[7] = 'override'
        return f, res

    with concurrent.futures.ThreadPoolExecutor(10) as ex:
        per_file = dict(ex.map(analyse, [f for st, f in delta]))
    assign_list_entries(per_file)
    per_file = dict((f, [tuple(h[:6]) for h in hs])
                    for f, hs in per_file.items())
    json.dump(per_file, open(DATA + '/hunks.json', 'w'))

    # Separability
    nh = mixed = 0
    lines = mlines = 0
    files_multi = []
    for f, hs in per_file.items():
        feats = set()
        for h in hs:
            n = sum(h[4].values())
            nh += 1
            lines += n
            feats.update(h[4])
            if len(h[4]) > 1:
                mixed += 1
                mlines += n
        if len(feats) > 1:
            files_multi.append(f)
    print('%d files, %d hunks, %d changed lines' % (len(per_file), nh, lines))
    print('mixed-feature hunks: %d (%.1f%%), %d lines (%.1f%%)'
          % (mixed, 100.0 * mixed / nh, mlines, 100.0 * mlines / lines))
    print('files touched by more than one feature: %d' % len(files_multi))

    # Merge-back simulation for multi-feature files
    conflicts = collections.Counter()
    bad = []
    for f in files_multi:
        if status[f] in ('A', 'D'):
            continue   # an added or deleted file cannot be split by hunk
        base = (show(BASE, f) or b'').decode('utf-8', 'replace')
        target = (show(JOYENT, f) or b'').decode('utf-8', 'replace')
        bl = base.split('\n')
        byfeat = collections.defaultdict(list)
        for h in per_file[f]:
            dom = dominant(h)
            byfeat[dom].append(h)
        tl = target.split('\n')

        def version(hs):
            # BASE with only these hunks applied (old ranges are BASE
            # line numbers; -U0 old_start for pure inserts is the line
            # after which to insert).
            out = []
            pos = 0
            for os_, no, ns, nn in sorted((h[:4] for h in hs), key=lambda h: h[0]):
                start = os_ - 1 if no else os_
                out += bl[pos:start]
                out += tl[ns - 1:ns - 1 + nn] if nn else []
                pos = start + no
            out += bl[pos:]
            return '\n'.join(out)

        with tempfile.TemporaryDirectory() as d:
            cur, anc = os.path.join(d, 'cur'), os.path.join(d, 'base')
            open(cur, 'w').write(base)
            open(anc, 'w').write(base)
            nconf = 0
            for feat, hs in sorted(byfeat.items()):
                other = os.path.join(d, 'f')
                open(other, 'w').write(version(hs))
                r = subprocess.run(['git', 'merge-file', '-q', cur, anc, other])
                if r.returncode != 0:
                    nconf += max(r.returncode, 1)
                    # resolve to the target text for those regions:
                    # restart from a clean union by taking target lines
                    open(cur, 'w').write(version(
                        [h for fe, hh in byfeat.items()
                         if fe <= feat for h in hh]))
            result = open(cur).read()
        if nconf:
            conflicts[f] = nconf
        if result != target:
            bad.append(f)
    print('multi-feature modified files merged: %d; with conflicts: %d '
          '(%d conflict regions); result != JOYENT: %d'
          % (sum(1 for f in files_multi if status[f] == 'M'), len(conflicts),
             sum(conflicts.values()), len(bad)))
    if verbose:
        for f in sorted(conflicts):
            print('  conflict %3d %s' % (conflicts[f], f))
        for f in bad:
            print('  MISMATCH %s' % f)


if __name__ == '__main__':
    main()
