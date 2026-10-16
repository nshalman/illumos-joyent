#!/usr/bin/env python3
"""where.py WORD...: which hunks add lines mentioning WORD, and whose are they.

Looks through data/hunks.json for hunks whose added lines (JOYENT's side)
contain WORD as a word, and prints file, JOYENT line, the hunk's feature
and the matching line.  Used to decide hunk overrides.
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from hunks import dominant  # noqa: E402

DATA = HERE + '/data'
refs = dict(l.strip().split('=') for l in open(DATA + '/refs'))
ILLUMOS = os.environ.get('ILLUMOS', os.path.expanduser('~/Workspace/illumos'))


def main():
    words = sys.argv[1:]
    hunks = json.load(open(DATA + '/hunks.json'))
    cache = {}
    for w in words:
        rx = re.compile(r'(^|[^\w])' + re.escape(w) + r'($|[^\w])')
        for f, hs in sorted(hunks.items()):
            for h in hs:
                if not h[3]:
                    continue
                if f not in cache:
                    r = subprocess.run(['git', '-C', ILLUMOS, 'show',
                                        '%s:%s' % (refs['JOYENT'], f)],
                                       capture_output=True)
                    cache[f] = r.stdout.decode('utf-8', 'replace').split('\n')
                for i in range(h[2] - 1, h[2] - 1 + h[3]):
                    if i < len(cache[f]) and rx.search(cache[f][i]):
                        print('%-14s %-16s %s:%d  %s' % (
                            w[:14], dominant(h), f.replace('usr/src/', ''),
                            i + 1, cache[f][i].strip()[:80]))
                        break


if __name__ == '__main__':
    main()
