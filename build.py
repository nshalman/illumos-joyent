#!/usr/bin/env python3
"""Build the restructured branch from data/ and the classifier.

  build.py --messages DIR   only write the commit messages to DIR
  build.py --branch NAME    (re)create NAME at BASE in $ILLUMOS and commit
                            one bucket at a time, then verify that the
                            tree equals JOYENT.  NAME is reset each run.

The illumos working tree must be clean; it is returned to the branch it
was on afterwards.
"""
import argparse
import collections
import os
import re
import subprocess
import sys
import tempfile

import classify as C
from buckets import BUCKETS, FILE_NOTES

ILLUMOS = os.environ.get('ILLUMOS', os.path.expanduser('~/Workspace/illumos'))

# A ticket whose subject reads like this is listed as a feature; anything
# else counts as a fix.  A heuristic: it decides where a ticket appears in
# the message, not whether it appears.
FEATURE = re.compile(r'\b(want|wants|add|adds|added|support|supports|'
    r'implement|introduce|new|enable|provide|expose|allow|ship|port|'
    r'would like|need a way|needs? (a|an)\b|should (support|be able))\b', re.I)


def git(*args, **kw):
    return subprocess.run(['git', '-C', ILLUMOS] + list(args), check=True,
                          text=True, capture_output=True, **kw).stdout


class People:
    """Collapse author identities that share a name or an email."""

    def __init__(self, idents):
        self.parent = {}
        for i in idents:
            name, email = self.split(i)
            self.union(('n', name.lower()), ('e', email.lower()))
        self.best = {}
        for i in idents:   # idents arrive newest first: keep newest email
            root = self.find(('n', self.split(i)[0].lower()))
            self.best.setdefault(root, i)

    @staticmethod
    def split(ident):
        m = re.match(r'(.*?)\s*<([^>]*)>', ident)
        return (m.group(1), m.group(2)) if m else (ident, '')

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        self.parent[self.find(a)] = self.find(b)

    def canonical(self, ident):
        best = self.best[self.find(('n', self.split(ident)[0].lower()))]
        return MAILMAP.get(self.split(best)[1].lower(), best)


def load_mailmap():
    m = {}
    fn = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mailmap')
    for l in open(fn):
        l = l.split('#')[0].strip()
        r = re.match(r'(.+?<[^>]+>)\s*<([^>]+)>$', l)
        if r:
            m[r.group(2).lower()] = r.group(1)
    return m


MAILMAP = load_mailmap()


def load_contrib():
    out = collections.defaultdict(list)
    fn = C.DATA + '/contrib.tsv'
    if os.path.exists(fn):
        for l in open(fn):
            h, who = l.rstrip('\n').split('\t')
            out[h].append(who)
    return out


def messages():
    commits, delta, blame, assign, how, votes, tb = C.classify()
    names = [b for b, _, _ in BUCKETS]
    assert len(names) == len(set(names)), 'duplicate bucket in buckets.py'
    missing = set(assign.values()) - set(names)
    assert not missing, 'buckets.py lacks: %s' % sorted(missing)

    # blame at commit granularity, to credit authors
    raw = C.load_raw_blame()
    by_sha = {}
    for l in open(C.DATA + '/commits.tsv'):
        h, p, d, a, s = l.rstrip('\n').split('\t', 4)
        by_sha[h] = (a, len(p.split()) > 1)
    people = People([a for a, _ in by_sha.values()] +
                    [w for ws in load_contrib().values() for w in ws])
    contrib = load_contrib()

    subj = {}
    for h, (t, s, d) in sorted(commits.items(), key=lambda x: x[1][2]):
        subj.setdefault(t, s.split(' Reviewed by')[0].strip())

    status = dict((f, st) for st, f in delta)
    out = []
    for b, title, body in BUCKETS:
        files = sorted(f for f, x in assign.items() if x == b)
        if not files:
            continue
        tickets = collections.Counter()
        authors = collections.Counter()
        for f in files:
            tickets.update(blame[f])
            for h, n in raw.get(f, {}).items():
                if h == 'BOUNDARY' or h not in by_sha:
                    continue
                a, is_merge = by_sha[h]
                if not is_merge:
                    authors[people.canonical(a)] += n
                for w in contrib.get(h, []):
                    authors[people.canonical(w)] += n
        tickets.pop('MERGE', None)
        feats, fixes, other = [], [], 0
        for t in sorted(tickets, key=lambda t: (-tickets[t], t)):
            if t.startswith('untagged:'):
                other += 1
            elif FEATURE.search(subj.get(t, '')):
                feats.append(t)
            else:
                fixes.append(t)

        msg = ['SmartOS: ' + title, '']
        if body:
            msg += wrap(body) + ['']
        if feats:
            msg.append('Features:')
            for t in sorted(feats, key=ticket_key):
                msg.append('  ' + subj[t][:110])
            msg.append('')
        if fixes:
            msg += wrap('Also includes the final state of fixes from %d '
                        'tickets: %s.' % (len(fixes),
                        ', '.join(sorted(fixes, key=ticket_key))))
            msg.append('')
        if other:
            msg += wrap('Plus %d commits without a ticket ID.' % other) + ['']
        notes = [FILE_NOTES[f] for f in files if f in FILE_NOTES]
        if notes:
            msg.append('Notes:')
            for n in notes:
                msg += ['  ' + l for l in wrap(n, 70)]
            msg.append('')
        nd = sum(1 for f in files if status[f] == 'D')
        msg += wrap('%d files (%d removed).  Tickets are those whose lines '
                    'survive in these files; changes that only delete '
                    'lines are not attributed.' % (len(files), nd))
        if authors:
            msg.append('')
            for a, _ in authors.most_common():
                msg.append('Co-authored-by: ' + a)
        out.append((b, files, '\n'.join(msg) + '\n'))
    return out, status


def ticket_key(t):
    m = re.match(r'([A-Z]+)-(\d+)', t)
    return (m.group(1), int(m.group(2))) if m else ('~', int(t) if t.isdigit() else 0)


def wrap(text, width=72):
    lines, cur = [], ''
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + ' ' + w) if cur else w
    if cur:
        lines.append(cur)
    return lines


def build(branch):
    refs = dict(l.strip().split('=') for l in open(C.DATA + '/refs'))
    if git('status', '--porcelain', '--untracked-files=no').strip():
        sys.exit('illumos working tree is not clean')
    if git('rev-parse', refs['JOYENT']).strip() != refs['JOYENT']:
        sys.exit('bad JOYENT ref')
    out, status = messages()
    env = dict(os.environ, GIT_LITERAL_PATHSPECS='1')
    start = git('rev-parse', '--abbrev-ref', 'HEAD').strip()
    git('checkout', '-q', '-B', branch, refs['BASE'])
    for b, files, msg in out:
        with tempfile.NamedTemporaryFile('w', delete=False) as live, \
             tempfile.NamedTemporaryFile('w', delete=False) as dead, \
             tempfile.NamedTemporaryFile('w', delete=False) as m:
            live.write('\n'.join(f for f in files if status[f] != 'D') + '\n')
            dead.write('\n'.join(f for f in files if status[f] == 'D') + '\n')
            m.write(msg)
        if any(status[f] != 'D' for f in files):
            git('checkout', refs['JOYENT'], '--pathspec-from-file=' + live.name,
                env=env)
        if any(status[f] == 'D' for f in files):
            git('rm', '-q', '--pathspec-from-file=' + dead.name, env=env)
        git('commit', '-q', '-F', m.name)
        for fn in (live.name, dead.name, m.name):
            os.unlink(fn)
        print('%-18s %4d files  %s' % (b, len(files),
              git('rev-parse', '--short', 'HEAD').strip()))
    diff = git('diff', '--stat', refs['JOYENT'], branch)
    git('checkout', '-q', start)
    if diff.strip():
        print(diff)
        sys.exit('MISMATCH: %s tree differs from %s' % (branch, refs['JOYENT']))
    print('OK: %s tree is identical to %s' % (branch, refs['JOYENT'][:11]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--messages')
    ap.add_argument('--branch')
    a = ap.parse_args()
    if a.messages:
        os.makedirs(a.messages, exist_ok=True)
        out, _ = messages()
        for i, (b, files, msg) in enumerate(out):
            with open('%s/%02d-%s.txt' % (a.messages, i, b), 'w') as f:
                f.write(msg + '\n# files:\n' + ''.join('#   %s\n' % x for x in files))
        print('wrote %d messages to %s' % (len(out), a.messages))
    elif a.branch:
        build(a.branch)
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
