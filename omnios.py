#!/usr/bin/env python3
"""Attribution for presenting lx as OmniOS's lx plus joyent's changes.

The lx files that also exist in OmniOS are committed first as OmniOS has
them (the lx-omnios commit), then brought to joyent's versions by the lx
commit.  For those files this writes:

  data/omnios_files.txt      the files, one per line
  data/omnios_blame/<f>      blame of OmniOS's version, '+' lines vs BASE
                             (credits the lx-omnios commit)
  data/omnios_commits.tsv    the OmniOS commits those blames name
  data/blame_vs_omnios/<f>   blame of joyent's version, '+' lines vs
                             OmniOS's (credits the lx commit)

Expects data/refs to carry OMNIOS (written by collect.sh).
"""
import concurrent.futures
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = HERE + '/data'
ILLUMOS = os.environ.get('ILLUMOS', os.path.expanduser('~/Workspace/illumos'))
sys.path.insert(0, HERE)
import classify  # noqa: E402  (for the lx path rule)

refs = dict(l.strip().split('=') for l in open(DATA + '/refs'))
LX = [r for b, r in classify.RULES if b == 'lx'][0]


def git(*a):
    return subprocess.run(['git', '-C', ILLUMOS] + list(a), capture_output=True,
                          text=True, errors='replace').stdout


def main():
    omnios = set(git('ls-tree', '-r', '--name-only', refs['OMNIOS']).split('\n'))
    files = []
    for l in open(DATA + '/delta.txt'):
        st, f = l.rstrip('\n').split('\t')
        if st != 'D' and LX.search(f) and f in omnios:
            files.append(f)
    with open(DATA + '/omnios_files.txt', 'w') as fp:
        fp.write(''.join(f + '\n' for f in files))

    env = dict(os.environ, ILLUMOS=ILLUMOS, DATA=DATA, BASE=refs['BASE'],
               JOYENT=refs['JOYENT'])
    jobs = [('omnios_blame', dict(env, REV=refs['OMNIOS'], FROM=refs['BASE'])),
            ('blame_vs_omnios', dict(env, REV=refs['JOYENT'], FROM=refs['OMNIOS']))]
    for sub, e in jobs:
        os.makedirs(DATA + '/' + sub, exist_ok=True)
        e['OUT'] = DATA + '/' + sub
        with concurrent.futures.ThreadPoolExecutor(10) as ex:
            list(ex.map(lambda f: subprocess.run(
                [HERE + '/blame-file.sh', f], cwd=ILLUMOS, env=e), files))

    # Subjects and authors of the OmniOS commits named by those blames.
    shas = set()
    for fn in os.listdir(DATA + '/omnios_blame'):
        for l in open(DATA + '/omnios_blame/' + fn):
            h = l.split()[1]
            if h != 'BOUNDARY':
                shas.add(h)
    with open(DATA + '/omnios_commits.tsv', 'w') as fp:
        for h in sorted(shas):
            fp.write(git('log', '-1', '--format=%H%x09%P%x09%ad%x09%an <%ae>%x09%s',
                         '--date=short', h))


if __name__ == '__main__':
    main()
