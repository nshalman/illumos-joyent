#!/usr/bin/env python3
"""List delta files whose differences from BASE are only copyright lines,
blank comment lines, or whitespace: residue of reverted or upstreamed
changes.  Usage: copyright_only.py  (reads data/refs)"""
import os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
refs = dict(l.strip().split('=') for l in open(HERE + '/data/refs'))
ILLUMOS = os.environ.get('ILLUMOS', os.path.expanduser('~/Workspace/illumos'))
diff = subprocess.run(['git', '-C', ILLUMOS, 'diff', '--no-ext-diff', '-U0',
    '--no-renames', refs['BASE'], refs['JOYENT']], capture_output=True,
    text=True, errors='replace').stdout
NOISE = re.compile(r'copyright|all rights reserved|^\s*(#|\*|//|/\*|\*/)?\s*$', re.I)
cur, lines = None, {}
for l in diff.splitlines():
    if l.startswith('diff --git'):
        cur = l.split(' b/')[-1]
        lines[cur] = []
    elif l.startswith(('+++', '---')):
        continue
    elif l[:1] in '+-' and cur:
        lines[cur].append(l[1:])
for f, ls in sorted(lines.items()):
    if ls and all(NOISE.search(x) for x in ls):
        print(f)
