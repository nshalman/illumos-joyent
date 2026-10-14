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

# The restructured commits are authored by Claude (the committer stays
# whoever runs the build); the people whose code it is are credited
# with Co-authored-by trailers.
AUTHOR = ('Claude', 'noreply@anthropic.com')

# Automation identities, never credited as co-authors.
BOTS = {'releng@joyent.com'}

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
            continue
        # name-only form: "Proper Name <commit@email>" keeps the email
        r = re.match(r'(.+?)\s*<([^>]+)>$', l)
        if r:
            m[r.group(2).lower()] = '%s <%s>' % (r.group(1), r.group(2))
    return m


MAILMAP = load_mailmap()


def load_deletions():
    out = {}
    d = C.DATA + '/deletions'
    if os.path.isdir(d):
        for fn in os.listdir(d):
            c = collections.Counter()
            for l in open(os.path.join(d, fn)):
                n, h = l.split()
                c[h] += int(n)
            out[fn.replace('%', '/')] = c
    return out


def load_counts(sub):
    """data/<sub>/<path with % for /> -> {path: Counter(sha: lines)}."""
    out = {}
    d = os.path.join(C.DATA, sub)
    if os.path.isdir(d):
        for fn in os.listdir(d):
            c = collections.Counter()
            for l in open(os.path.join(d, fn)):
                n, h = l.split()
                c[h] += int(n)
            out[fn.replace('%', '/')] = c
    return out


def load_omnios():
    """(staged files, OmniOS commits {sha: (author, subject)}) or None."""
    refs = dict(l.strip().split('=') for l in open(C.DATA + '/refs'))
    fn = C.DATA + '/omnios_files.txt'
    if 'OMNIOS' not in refs or not os.path.exists(fn):
        return None
    commits = {}
    for l in open(C.DATA + '/omnios_commits.tsv'):
        h, p, d, a, s = l.rstrip('\n').split('\t', 4)
        commits[h] = (a, s)
    return refs['OMNIOS'], open(fn).read().split(), commits


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

    # blame at commit granularity, to credit authors, plus credit for
    # removed lines (deletions.py), which blame cannot see
    raw = C.load_raw_blame()
    dele = load_deletions()
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
    titles = dict((n, t) for n, t, _ in BUCKETS)

    # Each ticket's home: the commit holding most of its surviving lines
    # outside the shared buckets.  Used to explain the shared files.
    home = collections.defaultdict(collections.Counter)
    shared = collections.Counter()
    for f, b in assign.items():
        for t, n in blame[f].items():
            if b in SHARED:
                shared[t] += n
            else:
                home[t][b] += n
    # A ticket has a home only if one commit holds at least 60% of its
    # non-shared lines (sweeps fail this, as in classify.py's vote) and
    # at least as many lines as the shared files do (a ticket that is
    # mostly manifest edits is listed by name, not under a stray file).
    home = dict((t, c.most_common(1)[0][0]) for t, c in home.items()
                if t != 'MERGE' and
                c.most_common(1)[0][1] >= 0.6 * sum(c.values()) and
                c.most_common(1)[0][1] >= shared[t])

    # The lx files OmniOS also has are first committed as OmniOS has them
    # (lx-omnios), then brought to joyent's versions by the lx commit.
    om = load_omnios()
    staged = set()
    if om:
        omnios_ref, ofiles, ocommits = om
        staged = set(ofiles) & set(f for f, x in assign.items() if x == 'lx')
        oblame = load_counts('omnios_blame')
        vblame = load_counts('blame_vs_omnios')
        people = People([a for a, _ in by_sha.values()] +
                        [a for a, _ in ocommits.values()] +
                        [w for ws in contrib.values() for w in ws])

    def ticket_of(subject):
        m = C.TICKET.match(subject)
        return m.group(1) if m else None

    def joyent_credit(f, shas, tickets, authors, with_deletions=True):
        for h, n in shas.items():
            if h == 'BOUNDARY' or h not in by_sha:
                continue
            a, is_merge = by_sha[h]
            t = commits[h][0]
            if t != 'MERGE':
                tickets[t] += n
            if not is_merge:
                authors[people.canonical(a)] += n
            for w in contrib.get(h, []):
                authors[people.canonical(w)] += n
        if with_deletions:
            for h, n in dele.get(f, {}).items():
                if h in by_sha and not by_sha[h][1]:
                    authors[people.canonical(by_sha[h][0])] += n

    out = []
    for b, title, body in BUCKETS:
        files = sorted(f for f, x in assign.items() if x == b)
        if not files:
            continue
        if b == 'lx-omnios':
            continue    # written together with lx, below
        if b == 'lx' and staged:
            tickets, authors = collections.Counter(), collections.Counter()
            osubj = {}
            for f in sorted(staged):
                for h, n in oblame.get(f, {}).items():
                    if h not in ocommits:
                        continue
                    a, s = ocommits[h]
                    t = ticket_of(s) or 'untagged:' + h[:11]
                    tickets[t] += n
                    osubj.setdefault(t, s.split(' Reviewed by')[0].strip())
                    authors[people.canonical(a)] += n
            ot, obody = [(t, x) for n, t, x in BUCKETS if n == 'lx-omnios'][0]
            obody += '  Source: omniosorg/illumos-omnios %s.' % omnios_ref[:12]
            out.append(('lx-omnios', sorted(staged), write_message(
                'lx-omnios', ot, obody, sorted(staged), tickets, authors,
                dict(subj, **osubj), status, blame, home, titles,
                credit_note='Tickets and co-authors are from OmniOS\'s '
                'history of these files.'), omnios_ref))
        tickets, authors = collections.Counter(), collections.Counter()
        for f in files:
            if f in staged:
                joyent_credit(f, vblame.get(f, {}), tickets, authors, False)
            else:
                joyent_credit(f, raw.get(f, {}), tickets, authors)
        note = ('Tickets are those whose lines survive in these files.  '
                'Co-authors also include the authors of removed lines.')
        if b == 'lx' and staged:
            note = ('For the %d files that start from OmniOS\'s version, '
                    'tickets and co-authors cover only the lines that differ '
                    'from it.  ' % len(staged)) + note
        out.append((b, files, write_message(
            b, title, body, files, tickets, authors, subj, status, blame,
            home, titles, credit_note=note), None))
    return out, status


def write_message(b, title, body, files, tickets, authors, subj, status,
                  blame, home, titles, credit_note):
    tickets = collections.Counter(tickets)
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
    if b.startswith('integration'):
        msg += by_feature(files, blame, home, titles, subj) + ['']
    notes = [FILE_NOTES[f] for f in files if f in FILE_NOTES]
    if notes:
        msg.append('Notes:')
        for n in notes:
            msg += ['  ' + l for l in wrap(n, 70)]
        msg.append('')
    nd = sum(1 for f in files if status[f] == 'D')
    msg += wrap('%d files (%d removed).  %s' % (len(files), nd, credit_note))
    if authors:
        msg.append('')
        for a, _ in authors.most_common():
            if People.split(a)[1].lower() not in BOTS:
                msg.append('Co-authored-by: ' + a)
    # git strips trailing whitespace from messages; match it
    return '\n'.join(l.rstrip() for l in msg) + '\n'


# Buckets whose files are shared by many features.  They never count as
# a ticket's home; the integration commits' messages get a per-feature
# breakdown.
SHARED = ('integration', 'integration-build', 'integration-pkg',
          'integration-drivers', 'integration-checks', 'integration-manifest',
          'copyright-residue', 'misc')


def by_feature(files, blame, home, titles, subj, per=6, ntix=10):
    """Group the files' added lines by the home commit of their ticket;
    lines from tickets with no single home are listed per ticket."""
    g = collections.defaultdict(collections.Counter)
    for f in files:
        for t, n in blame[f].items():
            if t in home:
                key = ('bucket', home[t])
            elif t == 'MERGE':
                key = ('merge', None)
            else:
                key = ('ticket', t)
            g[key][f] += n

    def files_line(c):
        items = ['%s +%d' % (f.replace('usr/src/', ''), n)
                 for f, n in c.most_common(per)]
        if len(c) > per:
            items.append('and %d more files' % (len(c) - per))
        return ['    ' + l for l in wrap(', '.join(items), 68)]

    size = lambda k: sum(g[k].values())
    lines = wrap('Changes by feature: lines added here, grouped by the commit '
                 'that holds the rest of the ticket that wrote them.')
    for k in sorted((k for k in g if k[0] == 'bucket'), key=lambda k: -size(k)):
        lines.append('  %s (+%d):' % (titles.get(k[1], k[1]), size(k)))
        lines += files_line(g[k])
    tix = sorted((k for k in g if k[0] == 'ticket'), key=lambda k: -size(k))
    if tix:
        lines.append('')
        lines += wrap('Tickets that span many commits (sweeps) or have no '
                      'other home:')
        for k in tix[:ntix]:
            lines += ['  ' + l for l in wrap('%s (+%d)' % (
                subj.get(k[1], k[1])[:80], size(k)), 70)]
            lines += files_line(g[k])
        rest = tix[ntix:]
        if rest:
            n = sum(size(k) for k in rest)
            lines += ['  ' + l for l in wrap('%d more tickets (+%d): %s' % (
                len(rest), n, ', '.join(k[1] for k in rest)), 70)]
    if ('merge', None) in g:
        lines.append('')
        lines.append('  Written during merge conflict resolution (+%d):'
                     % size(('merge', None)))
        lines += files_line(g[('merge', None)])
    return lines


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
    for b, files, msg, src in out:
        # src: the ref this commit's file contents come from (JOYENT
        # unless the commit is staged from another tree, like lx-omnios)
        src = src or refs['JOYENT']
        with tempfile.NamedTemporaryFile('w', delete=False) as live, \
             tempfile.NamedTemporaryFile('w', delete=False) as dead, \
             tempfile.NamedTemporaryFile('w', delete=False) as m:
            live.write('\n'.join(f for f in files if status[f] != 'D') + '\n')
            dead.write('\n'.join(f for f in files if status[f] == 'D') + '\n')
            m.write(msg)
        if any(status[f] != 'D' for f in files):
            git('checkout', src, '--pathspec-from-file=' + live.name, env=env)
        if any(status[f] == 'D' for f in files):
            git('rm', '-q', '--pathspec-from-file=' + dead.name, env=env)
        git('commit', '-q', '-F', m.name, env=dict(os.environ,
            GIT_AUTHOR_NAME=AUTHOR[0], GIT_AUTHOR_EMAIL=AUTHOR[1]))
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
        for old in os.listdir(a.messages):
            if old.endswith('.txt'):
                os.unlink(os.path.join(a.messages, old))
        out, _ = messages()
        for i, (b, files, msg, src) in enumerate(out):
            with open('%s/%02d-%s.txt' % (a.messages, i, b), 'w') as f:
                f.write(msg + '\n# files:\n' + ''.join('#   %s\n' % x for x in files))
        print('wrote %d messages to %s' % (len(out), a.messages))
    elif a.branch:
        build(a.branch)
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
