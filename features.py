#!/usr/bin/env python3
"""Build one independent branch per feature, and a merge of all of them.

Each feature branch is BASE plus only that feature's hunks (from
data/hunks.json, written by hunks.py): added and deleted files whole,
modified files with just the feature's hunks applied.  A hunk belongs to
the feature that owns most of its lines.  Branches are written with git
plumbing (a private index), so the clone's working tree is untouched.

Then all feature branches are merged with `git merge-tree` and the
result must have JOYENT's tree.  The merge is recorded as a single
octopus merge commit on `features-merged`.

  features.py              build features/<name> branches and the merge
  features.py --delete     delete the features/* branches and the merge

Prints per-feature sizes and any merge conflicts.
"""
import collections
import json
import re
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build as B  # noqa: E402
import classify as C  # noqa: E402
from buckets import BUCKETS  # noqa: E402
from hunks import dominant  # noqa: E402

DATA = C.DATA
ILLUMOS = B.ILLUMOS
PREFIX = 'features/'
MERGED = 'features-merged'
refs = dict(l.strip().split('=') for l in open(DATA + '/refs'))
BASE, JOYENT = refs['BASE'], refs['JOYENT']


def run(*a, inp=None, env=None):
    r = subprocess.run(['git', '-C', ILLUMOS] + list(a), input=inp,
                       capture_output=True, env=env)
    return r


def out(*a, **kw):
    r = run(*a, **kw)
    if r.returncode != 0:
        sys.exit('git %s failed: %s' % (' '.join(a[:3]), r.stderr.decode()))
    return r.stdout.decode().strip()


def blob(rev, path):
    r = run('show', rev + ':' + path)
    return r.stdout if r.returncode == 0 else None


def modes(rev):
    m = {}
    for l in out('ls-tree', '-r', rev).split('\n'):
        meta, p = l.split('\t', 1)
        mode, _, sha = meta.split()
        m[p] = (mode, sha)
    return m


def apply_hunks(base, target, hs):
    """BASE bytes with only these -U0 hunks applied (new text from target)."""
    bl = base.split(b'\n')
    tl = target.split(b'\n')
    res = []
    pos = 0
    for os_, no, ns, nn in sorted(hs):
        start = os_ - 1 if no else os_
        res += bl[pos:start]
        res += tl[ns - 1:ns - 1 + nn]
        pos = start + no
    res += bl[pos:]
    return b'\n'.join(res)


COPYRIGHT = re.compile(rb'copyright|all rights reserved', re.I)
BLANK = re.compile(rb'^\s*(#|\*|//|/\*|\*/)?\s*$')


def copyright_only(h, base, target):
    """True if every line the hunk removes or adds is a copyright line or
    a blank comment line."""
    old = base.split(b'\n')[h[0] - 1:h[0] - 1 + h[1]] if h[1] else []
    new = target.split(b'\n')[h[2] - 1:h[2] - 1 + h[3]] if h[3] else []
    lines = old + new
    return bool(lines) and all(COPYRIGHT.search(l) or BLANK.match(l)
                               for l in lines) and \
        any(COPYRIGHT.search(l) for l in lines)


def plan():
    """{feature: {path: ('A'|'M', bytes) or ('D', None)}}, plus credit."""
    hunks = json.load(open(DATA + '/hunks.json'))
    status = {}
    for l in open(DATA + '/delta.txt'):
        st, f = l.rstrip('\n').split('\t')
        status[f] = st
    assign = json.load(open(DATA + '/assign.json'))
    feats = collections.defaultdict(dict)
    who = collections.defaultdict(collections.Counter)
    checked = 0
    split = {}      # multi-feature modified file -> {feature: hunks}
    replicated = 0
    for f, hs in hunks.items():
        if not hs:
            # binary or empty: no text hunks, so the whole file goes to
            # its whole-file bucket
            st = status[f]
            feats[assign[f]][f] = (st, None if st == 'D' else blob(JOYENT, f))
            continue
        by = collections.defaultdict(list)
        for h in hs:
            by[dominant(h)].append(h)
            for sha, n in h[5].items():
                who[dominant(h)][sha] += n
        st = status[f]
        if st in ('A', 'D'):
            assert len(by) == 1, f
            (feat,) = by
            feats[feat][f] = (st, blob(JOYENT, f) if st == 'A' else None)
            continue
        base, target = blob(BASE, f), blob(JOYENT, f)
        if len(by) == 1:
            (feat,) = by
            feats[feat][f] = ('M', target)
            continue
        allh = [h[:4] for h in hs]
        if apply_hunks(base, target, allh) != target:
            sys.exit('hunk reconstruction does not reproduce %s' % f)
        checked += 1
        # Every feature touching the file gets the copyright hunks too, so
        # each branch carries the header change; identical hunks merge
        # cleanly.
        cr = [h for h in hs if copyright_only(h, base, target)]
        for feat in by:
            for h in cr:
                if h not in by[feat]:
                    by[feat].append(h)
                    replicated += 1
        for feat, fh in by.items():
            feats[feat][f] = ('M', apply_hunks(base, target,
                                               [h[:4] for h in fh]))
        split[f] = by
    return feats, who, checked, split, replicated


def commit_feature(name, files, msg, jmodes):
    with tempfile.NamedTemporaryFile(delete=False) as idx:
        pass
    os.unlink(idx.name)     # keep the name; git creates the index
    env = dict(os.environ, GIT_INDEX_FILE=idx.name,
               GIT_AUTHOR_NAME=B.AUTHOR[0], GIT_AUTHOR_EMAIL=B.AUTHOR[1])
    out('read-tree', BASE, env=env)
    info = []
    for p, (st, data) in sorted(files.items()):
        if st == 'D':
            info.append('0 %s\t%s' % ('0' * 40, p))
            continue
        sha = out('hash-object', '-w', '--stdin', inp=data)
        info.append('%s %s\t%s' % (jmodes[p][0], sha, p))
    out('update-index', '--index-info', inp=('\n'.join(info) + '\n').encode(),
        env=env)
    tree = out('write-tree', env=env)
    os.unlink(idx.name)
    c = out('commit-tree', tree, '-p', BASE, inp=msg.encode(), env=env)
    out('update-ref', 'refs/heads/' + PREFIX + name, c)
    return c


def resolve(tree, paths, split, merged):
    """Replace conflicted paths in tree with BASE plus the hunks of the
    features merged so far."""
    with tempfile.NamedTemporaryFile(delete=False) as idx:
        pass
    os.unlink(idx.name)
    env = dict(os.environ, GIT_INDEX_FILE=idx.name)
    out('read-tree', tree, env=env)
    jmodes = modes(JOYENT)
    info = []
    for p in sorted(set(paths)):
        base, target = blob(BASE, p), blob(JOYENT, p)
        hs = sorted(set(tuple(h[:4]) for feat, fh in split[p].items()
                        if feat in merged for h in fh))
        sha = out('hash-object', '-w', '--stdin',
                  inp=apply_hunks(base, target, hs))
        info.append('%s %s\t%s' % (jmodes[p][0], sha, p))
    out('update-index', '--index-info',
        inp=('\n'.join(info) + '\n').encode(), env=env)
    t = out('write-tree', env=env)
    os.unlink(idx.name)
    return t


def delete():
    for r in out('for-each-ref', '--format=%(refname)',
                 'refs/heads/' + PREFIX).split('\n'):
        if r:
            out('update-ref', '-d', r)
    run('update-ref', '-d', 'refs/heads/' + MERGED)
    print('deleted %s* and %s' % (PREFIX, MERGED))


def main():
    if '--delete' in sys.argv:
        return delete()
    feats, who, checked, split, replicated = plan()
    titles = dict((n, (t, d)) for n, t, d in BUCKETS)
    order = [n for n, _, _ in BUCKETS if n in feats]
    assert set(order) == set(feats), set(feats) - set(order)

    # credit, as build.py: tickets and co-authors from the commits that
    # wrote (or removed) each feature's lines
    commits, delta, blame, assign, how, votes, tb = C.classify()
    by_sha = {}
    for l in open(DATA + '/commits.tsv'):
        h, p, d, a, s = l.rstrip('\n').split('\t', 4)
        by_sha[h] = (a, len(p.split()) > 1)
    contrib = B.load_contrib()
    people = B.People([a for a, _ in by_sha.values()] +
                      [w for ws in contrib.values() for w in ws])
    subj = {}
    for h, (t, s, d) in sorted(commits.items(), key=lambda x: x[1][2]):
        subj.setdefault(t, s.split(' Reviewed by')[0].strip())
    status = dict((f, st) for st, f in delta)

    jmodes = modes(JOYENT)
    heads = []
    print('%-22s %5s %8s' % ('feature', 'files', 'shas'))
    for name in order:
        tickets, authors = collections.Counter(), collections.Counter()
        for sha, n in who[name].items():
            if sha not in by_sha:
                continue
            t = commits[sha][0]
            if t != 'MERGE':
                tickets[t] += n
            a, is_merge = by_sha[sha]
            if not is_merge:
                authors[people.canonical(a)] += n
            for w in contrib.get(sha, []):
                authors[people.canonical(w)] += n
        files = sorted(feats[name])
        title, body = titles[name]
        msg = B.write_message(
            name, title, body, files, tickets, authors, subj, status, blame,
            {}, {}, credit_note='This commit applies to illumos-gate on its '
            'own; files shared with other features carry only this '
            "feature's hunks.")
        heads.append((name, commit_feature(name, feats[name], msg, jmodes)))
        print('%-22s %5d %8d' % (name, len(files), len(who[name])))

    # merge them all, as git would, and check the result.  A conflict is
    # resolved to the known answer: BASE plus the hunks of every feature
    # merged so far.
    cur = BASE
    conflicts = []
    merged = set()
    for name, c in heads:
        merged.add(name)
        r = run('merge-tree', '--write-tree', '--name-only',
                '--merge-base=' + BASE, cur, c)
        lines = r.stdout.decode().split('\n')
        tree = lines[0]
        if r.returncode == 1:
            paths = []
            for l in lines[1:]:
                if not l:
                    break       # conflicted paths end at the blank line
                paths.append(l)
            conflicts.append((name, paths))
            tree = resolve(tree, paths, split, merged)
        elif r.returncode != 0:
            sys.exit('merge-tree failed for %s: %s' % (name,
                                                      r.stderr.decode()))
        cur = out('commit-tree', tree, '-p', cur, '-p', c,
                  inp=b'merge ' + name.encode())
    tree = out('rev-parse', cur + '^{tree}')
    ok = tree == out('rev-parse', JOYENT + '^{tree}')
    parents = sum((['-p', c] for _, c in heads), [])
    msg = ('Merge %d independent SmartOS feature branches\n\n' % len(heads) +
           '\n'.join(B.wrap('Each parent applies to illumos-gate %s on its '
                            'own.  The merged tree is identical to '
                            'illumos-joyent %s.' % (BASE[:11], JOYENT[:11])))
           + '\n')
    if conflicts:
        msg += ('\nMerging in this order, these conflicted and were '
                'resolved to the combined hunks:\n')
        for name, paths in conflicts:
            msg += ''.join('  %s: %s\n' % (name, p) for p in paths)
    env = dict(os.environ, GIT_AUTHOR_NAME=B.AUTHOR[0],
               GIT_AUTHOR_EMAIL=B.AUTHOR[1])
    octo = out('commit-tree', tree, *parents, inp=msg.encode(), env=env)
    out('update-ref', 'refs/heads/' + MERGED, octo)
    print('%d feature branches; %d multi-feature files split by hunk; '
          '%d copyright hunks replicated' % (len(heads), checked, replicated))
    print('merge conflicts: %d' % len(conflicts))
    for name, paths in conflicts:
        print('  %s: %s' % (name, ', '.join(paths)))
    print('merged tree %s JOYENT (%s)' % ('==' if ok else '!=', MERGED))
    if not ok:
        sys.exit(1)
    write_log(heads, msg)


def write_log(heads, merge_msg):
    """Write features-log.txt: each feature branch's message and --stat
    against BASE, then the merge commit's message; no hashes or dates, so
    the file changes only when a branch's content or message does."""
    path = os.path.join(HERE, 'features-log.txt')
    with open(path, 'w') as f:
        f.write('Independent feature branches (features/<name>), each based '
                'on illumos-gate\n%s and applicable on its own, then the '
                'octopus merge of all of\nthem (%s), whose tree is identical '
                'to illumos-joyent %s.\nRegenerated by features.py.\n'
                % (BASE[:11], MERGED, JOYENT[:11]))
        for i, (name, c) in enumerate(heads, 1):
            body = out('log', '-1', '--format=%B', c)
            stat = run('diff', '--no-color', '--no-ext-diff',
                       '--stat=100,72', BASE, c).stdout.decode().rstrip('\n')
            f.write('\n%s\n[%d/%d] %s%s\n\n%s\n\n%s\n' % (
                '=' * 72, i, len(heads), PREFIX, name, body, stat))
        f.write('\n%s\n%s: %s' % ('=' * 72, MERGED, merge_msg))
    print('wrote %s (%d branches)' % (path, len(heads)))


if __name__ == '__main__':
    main()
