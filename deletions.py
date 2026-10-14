#!/usr/bin/env python3
"""Credit commits for lines they removed that are still gone.

Blame only sees lines that exist, so a change that deletes upstream lines
(or a whole file) is invisible to it.  For every delta file with '-'
lines relative to BASE, walk the non-merge joyent commits that touched it
and count each commit's removed lines whose text is among the lines still
missing from JOYENT.  Writes data/deletions/<path with / as %> with lines
"<count> <sha>", like data/blame/.

This is a text match, so it over-credits when the same line text is
removed more than once along the way; it is used only to credit authors.
"""
import collections
import concurrent.futures
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = HERE + '/data'
ILLUMOS = os.environ.get('ILLUMOS', os.path.expanduser('~/Workspace/illumos'))
refs = dict(l.strip().split('=') for l in open(DATA + '/refs'))
BASE, JOYENT = refs['BASE'], refs['JOYENT']


def git(*a):
    return subprocess.run(['git', '-C', ILLUMOS] + list(a), capture_output=True,
                          text=True, errors='replace').stdout


def missing_lines(path):
    """Multiset of line texts in BASE's version that JOYENT lacks."""
    gone = collections.Counter()
    for l in git('diff', '--no-ext-diff', '--no-renames', '-U0', BASE, JOYENT,
                 '--', path).splitlines():
        if l.startswith('-') and not l.startswith('---'):
            gone[l[1:]] += 1
    return gone


def credit(path):
    gone = missing_lines(path)
    if not gone:
        return path, collections.Counter()
    got = collections.Counter()
    sha = None
    for l in git('log', '--no-merges', '--full-history', '--no-renames',
                 '--format=@@%H', '-p',
                 '-U0', '--no-ext-diff', BASE + '..' + JOYENT, '--',
                 path).splitlines():
        if l.startswith('@@') and not l.startswith('@@ '):
            sha = l[2:]
        elif l.startswith('-') and not l.startswith('---') and sha:
            if l[1:] in gone:
                got[sha] += 1
    return path, got


def main():
    os.makedirs(DATA + '/deletions', exist_ok=True)
    paths = []
    for l in open(DATA + '/delta.txt'):
        st, f = l.rstrip('\n').split('\t')
        if st in ('M', 'D'):
            paths.append(f)
    with concurrent.futures.ThreadPoolExecutor(10) as ex:
        for path, got in ex.map(credit, paths):
            with open(DATA + '/deletions/' + path.replace('/', '%'), 'w') as f:
                for sha, n in got.most_common():
                    f.write('%d %s\n' % (n, sha))


if __name__ == '__main__':
    main()
