#!/usr/bin/env python3
"""baseline.py WS BASE JOYENT: write baseline.txt's files into WS.

WS is an illumos checkout at BASE.  For each baseline.txt entry, write
JOYENT's version of the file, or, when a fourth column `remove:REGEX` is
given, BASE's version with only those joyent hunks that purely delete
lines all matching REGEX.  The caller commits the result.
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def git(ws, *a):
    r = subprocess.run(['git', '-C', ws] + list(a), capture_output=True)
    if r.returncode != 0:
        sys.exit('git %s: %s' % (' '.join(a), r.stderr.decode()))
    return r.stdout


def main():
    ws, base, joyent = sys.argv[1:4]
    for entry in open(os.path.join(HERE, 'baseline.txt')):
        if entry.startswith('#') or not entry.strip():
            continue
        cols = entry.rstrip('\n').split('\t')
        path, fb = cols[0], cols[1]
        flt = cols[3] if len(cols) > 3 else ''
        if not flt:
            data = git(ws, 'show', '%s:%s' % (joyent, path))
            how = 'whole file'
        elif flt.startswith('remove:'):
            rx = re.compile(flt[len('remove:'):].encode())
            data, n = remove_hunks(ws, base, joyent, path, rx)
            how = '%d removal hunk(s)' % n
        else:
            sys.exit('unknown filter %r for %s' % (flt, path))
        with open(os.path.join(ws, path), 'wb') as f:
            f.write(data)
        print('  %s (fallback %s, %s)' % (path, fb, how))


def remove_hunks(ws, base, joyent, path, rx):
    lines = git(ws, 'show', '%s:%s' % (base, path)).split(b'\n')
    diff = git(ws, 'diff', '--no-ext-diff', '-U0', base, joyent, '--', path)
    hunks, cur = [], None
    for l in diff.split(b'\n'):
        m = re.match(rb'@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@', l)
        if m:
            cur = {'start': int(m.group(1)), 'old': [], 'adds': False}
            hunks.append(cur)
        elif cur is None:
            continue
        elif l.startswith(b'+') and not l.startswith(b'+++'):
            cur['adds'] = True
        elif l.startswith(b'-') and not l.startswith(b'---'):
            cur['old'].append(l[1:])
    drop = set()
    for h in hunks:
        if h['adds'] or not h['old']:
            continue
        if all(rx.search(l) for l in h['old']):
            drop.update(range(h['start'], h['start'] + len(h['old'])))
    if not drop:
        sys.exit('no removal hunks of %s match %s' % (path, rx.pattern))
    kept = [l for i, l in enumerate(lines, 1) if i not in drop]
    n = sum(1 for h in hunks if not h['adds'] and h['old'] and
            all(rx.search(l) for l in h['old']))
    return b'\n'.join(kept), n


if __name__ == '__main__':
    main()
