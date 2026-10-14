#!/usr/bin/env python3
"""merge_lines.py PATH [CONTEXT]

Print the lines of PATH (as of JOYENT) that differ from BASE and were
written in a merge commit (i.e. during conflict resolution), with CONTEXT
lines around each run (default 5).  Each line is prefixed with its line
number and the short sha of the commit blame credits ('^' for upstream).
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
refs = dict(l.strip().split('=') for l in open(HERE + '/data/refs'))
ILLUMOS = os.environ.get('ILLUMOS', os.path.expanduser('~/Workspace/illumos'))
merges = set()
for l in open(HERE + '/data/commits.tsv'):
    h, p = l.split('\t')[:2]
    if len(p.split()) > 1:
        merges.add(h)


def git(*a):
    return subprocess.run(['git', '-C', ILLUMOS] + list(a), capture_output=True,
                          text=True, errors='replace', check=True).stdout


def main():
    path = sys.argv[1]
    ctx = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    plus = set()
    for l in git('diff', '--no-ext-diff', '-U0', refs['BASE'], refs['JOYENT'],
                 '--', path).splitlines():
        m = re.match(r'@@ -\S+ \+(\d+)(?:,(\d+))?', l)
        if m:
            s, n = int(m.group(1)), int(m.group(2) or 1)
            plus.update(range(s, s + n))
    rows = []   # (lineno, sha, text)
    sha = None
    for l in git('blame', '--line-porcelain', refs['BASE'] + '..' +
                 refs['JOYENT'], '--', path).splitlines():
        m = re.match(r'([0-9a-f]{40}) \d+ (\d+)', l)
        if m:
            sha, ln = m.group(1), int(m.group(2))
        elif l.startswith('boundary'):
            sha = '^' + sha[:10]
        elif l.startswith('\t'):
            rows.append((ln, sha, l[1:]))
    hot = [i for i, (ln, s, _) in enumerate(rows) if ln in plus and s in merges]
    show = set()
    for i in hot:
        show.update(range(max(0, i - ctx), min(len(rows), i + ctx + 1)))
    last = None
    for i in sorted(show):
        if last is not None and i != last + 1:
            print('   ...')
        ln, s, t = rows[i]
        mark = 'M' if i in hot else ('+' if ln in plus else ' ')
        print('%5d %s %-11s %s' % (ln, mark, s[:11], t))
        last = i
    print('# %d merge-written lines; M = written in a merge, + = other joyent '
          'change, blank = same as upstream' % len(hot))


if __name__ == '__main__':
    main()
