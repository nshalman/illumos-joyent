#!/usr/bin/env python3
"""Maintain illumos-joyent's features as branches on illumos-gate.

Every feature is a branch based on an illumos-gate commit.  This module
holds the operations the workflow is built from, all done with git
plumbing so no working tree is touched:

  rebase     move one feature from an old gate commit to a new one
  integrate  merge features, one after another, onto a gate commit
  route      split a change to the integrated tree among the features
             that own the lines it touches

See WORKFLOW.md on the meta/restructure branch for the design.
"""
import collections
import os
import re
import subprocess
import tempfile


class GitError(Exception):
    pass


class Git:
    """A repository, driven through plumbing commands."""

    def __init__(self, repo):
        self.repo = repo

    def run(self, *args, input=None, env=None, ok=(0,)):
        r = subprocess.run(['git', '-C', self.repo] + list(args), input=input,
                           capture_output=True, env=env)
        if r.returncode not in ok:
            raise GitError('git %s: exit %d: %s' % (
                ' '.join(args[:3]), r.returncode,
                r.stderr.decode(errors='replace').strip()))
        return r

    def out(self, *args, **kw):
        return self.run(*args, **kw).stdout.decode().strip()

    def rev(self, name):
        return self.out('rev-parse', '--verify', name + '^{commit}')

    def tree(self, rev):
        return self.out('rev-parse', '--verify', rev + '^{tree}')

    def blob(self, oid):
        return self.run('cat-file', 'blob', oid).stdout

    def hash_blob(self, data):
        return self.out('hash-object', '-w', '--stdin', input=data)

    def entries(self, treeish, paths):
        """{path: (mode, oid)} for the PATHS present in TREEISH."""
        found = {}
        paths = list(paths)
        for i in range(0, len(paths), 500):
            out = self.run('ls-tree', '-r', '-z', treeish, '--',
                           *paths[i:i + 500]).stdout.decode()
            for rec in out.split('\0'):
                if rec:
                    meta, path = rec.split('\t', 1)
                    mode, _, oid = meta.split()
                    found[path] = (mode, oid)
        return found

    def commit_tree(self, tree, parents, message, author=None):
        """Create a commit; AUTHOR is (name, email, date) or None."""
        env = dict(os.environ)
        if author:
            env.update(GIT_AUTHOR_NAME=author[0], GIT_AUTHOR_EMAIL=author[1],
                       GIT_AUTHOR_DATE=author[2])
        args = ['commit-tree', '--no-gpg-sign', tree]
        for p in parents:
            args += ['-p', p]
        return self.out(*args, '-F', '-', input=message.encode(), env=env)

    def author(self, commit):
        name, email, date = self.out(
            'log', '-1', '--date=raw', '--format=%an%x00%ae%x00%ad',
            commit).split('\0')
        return (name, email, date)

    def message(self, commit):
        return self.run('log', '-1', '--format=%B', commit).stdout.decode()


def merge_tree(g, ours, theirs, base=None, favor=None):
    """Merge THEIRS into OURS; return (tree, conflicted paths)."""
    args = ['merge-tree', '--write-tree', '--name-only', '-z',
            '--no-messages']
    if base:
        args.append('--merge-base=' + base)
    if favor:
        args += ['-X', favor]
    r = g.run(*args, ours, theirs, ok=(0, 1))
    parts = r.stdout.decode().split('\0')
    return parts[0].strip(), sorted(set(p for p in parts[1:] if p))


Rebase = collections.namedtuple('Rebase', 'tip conflicts emptied')


def rebase(g, old_base, tip, new_base):
    """Replay the commits OLD_BASE..TIP onto NEW_BASE.

    A commit that conflicts is still replayed, keeping the feature's side
    of each conflict, and is listed in `conflicts` as (commit, paths) so
    a person can check the result.  A commit that becomes empty is
    dropped and listed in `emptied`: gate may already have its change.
    """
    commits = g.out('rev-list', '--reverse', '--topo-order',
                    '%s..%s' % (old_base, tip)).split()
    if g.out('rev-list', '--merges', '%s..%s' % (old_base, tip)):
        raise GitError('%s..%s contains merges' % (old_base, tip))
    cur = new_base
    conflicts, emptied = [], []
    for c in commits:
        tree, paths = merge_tree(g, cur, c, base=c + '^')
        if paths:
            conflicts.append((c, paths))
            tree, _ = merge_tree(g, cur, c, base=c + '^', favor='theirs')
        if tree == g.tree(cur):
            emptied.append(c)
            continue
        cur = g.commit_tree(tree, [cur], g.message(c), g.author(c))
    return Rebase(cur, conflicts, emptied)


Integration = collections.namedtuple('Integration', 'commit conflicts')


def integrate(g, base, features):
    """Merge FEATURES, a list of (name, commit), onto BASE in order.

    A feature that conflicts with those merged before it is left out and
    listed in `conflicts` as (name, paths).
    """
    cur = base
    conflicts = []
    for name, commit in features:
        tree, paths = merge_tree(g, cur, commit)
        if paths:
            conflicts.append((name, paths))
            continue
        cur = g.commit_tree(tree, [cur, commit], 'Merge feature %s\n' % name)
    return Integration(cur, conflicts)


LINE = re.compile(rb'[^\n]*\n|[^\n]+$')
HUNK = re.compile(rb'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', re.M)


def split_lines(data):
    return LINE.findall(data)


def hunks(g, a, b):
    """Hunks of the diff between blobs A and B, without context.

    Each is (old_start, old_len, new_start, new_len), 1-based; a hunk
    with old_len 0 inserts after line old_start.  None if either side is
    binary.
    """
    r = g.run('diff', '-U0', '--no-ext-diff', '--no-color', '--no-textconv',
              a, b)
    if b'\nBinary files ' in b'\n' + r.stdout:
        return None
    out = []
    for m in HUNK.finditer(r.stdout):
        os_, ol, ns, nl = m.groups()
        out.append((int(os_), 1 if ol is None else int(ol),
                    int(ns), 1 if nl is None else int(nl)))
    return out


def added_lines(g, base, blob):
    """{line number in BLOB: text} for the lines BLOB adds over BASE."""
    lines = split_lines(g.blob(blob))
    if base is None:
        return dict(enumerate(lines, 1))
    out = {}
    for _, _, ns, nl in hunks(g, base, blob) or []:
        for n in range(ns, ns + nl):
            out[n] = lines[n - 1]
    return out


def owners_of_lines(g, gate, integ, features):
    """For each line INTEG adds over GATE, the FEATURES that add it.

    FEATURES maps name to that feature's blob.  A line several features
    add identically, like a copyright line, belongs to all of them.
    """
    texts = {n: set(added_lines(g, gate, b).values())
             for n, b in features.items()}
    return {i: set(n for n, t in texts.items() if text in t)
            for i, text in added_lines(g, gate, integ).items()}


def apply_hunks(old, new, selected):
    """OLD with only the SELECTED hunks of the diff OLD -> NEW applied."""
    out = list(old)
    for os_, ol, ns, nl in sorted(selected, reverse=True):
        at = os_ if ol == 0 else os_ - 1
        out[at:at + ol] = new[ns - 1:ns - 1 + nl]
    return b''.join(out)


Unrouted = collections.namedtuple('Unrouted', 'path reason')
Route = collections.namedtuple('Route', 'commits unrouted')


def route(g, gate, features, target, msg, author=None, decide=None):
    """Change FEATURES so their integration on GATE has tree TARGET.

    FEATURES maps name to commit.  Each path that differs goes to the
    features that touch it: to the only one, whole, or line by line to
    the features owning the lines each hunk changes or sits next to.
    DECIDE maps a path to the feature that takes all of its change; it
    covers what the rules cannot place: new files, and files no feature
    touches.  Returns the new commit for each changed feature, made on
    top of it with MSG and AUTHOR, and the paths left unrouted.
    """
    decide = decide or {}
    integ = integrate(g, gate, sorted(features.items()))
    if integ.conflicts:
        raise GitError('features do not integrate: %s' % integ.conflicts)
    itree = g.tree(integ.commit)
    diff = g.run('diff-tree', '-r', '-z', '--no-renames', '--name-only',
                 itree, target).stdout.decode()
    paths = [p for p in diff.split('\0') if p]
    if not paths:
        return Route({}, [])
    want = g.entries(target, paths)
    have = g.entries(itree, paths)
    base = g.entries(gate, paths)
    feat = {n: g.entries(c, paths) for n, c in features.items()}
    changes = collections.defaultdict(dict)
    unrouted = []
    for path in paths:
        touched = sorted(n for n in features
                         if feat[n].get(path) != base.get(path))
        if path in decide:
            owner = decide[path]
            ours = feat[owner].get(path)
            if ours is None or path not in have or path not in want:
                changes[owner][path] = want.get(path)
                continue
            merged = merge_file(g, ours[1], have[path][1], want[path][1])
            if merged is None:
                unrouted.append(Unrouted(path, 'conflict applying to %s'
                                         % owner))
            else:
                changes[owner][path] = (want[path][0], merged)
        elif not touched:
            unrouted.append(Unrouted(path, 'new file' if path not in have
                                     else 'no feature touches it'))
        elif len(touched) == 1:
            changes[touched[0]][path] = want.get(path)
        else:
            routed = route_lines(g, path, base.get(path), have.get(path),
                                 want.get(path),
                                 {n: feat[n][path] for n in touched
                                  if path in feat[n]})
            if isinstance(routed, Unrouted):
                unrouted.append(routed)
            else:
                for n, entry in routed.items():
                    changes[n][path] = entry
    commits = {}
    for n, edits in sorted(changes.items()):
        tree = edit_tree(g, features[n], edits)
        if tree != g.tree(features[n]):
            commits[n] = g.commit_tree(tree, [features[n]], msg, author)
    return Route(commits, unrouted)


def route_lines(g, path, base, have, want, features):
    """Split one shared file's change among the FEATURES owning its lines.

    BASE, HAVE and WANT are the (mode, oid) of the file on gate, in the
    integration and in the target; FEATURES maps name to (mode, oid).
    Returns {name: new (mode, oid)} or an Unrouted.
    """
    if have is None or want is None:
        return Unrouted(path, 'shared file added or deleted')
    hs = hunks(g, have[1], want[1])
    if hs is None:
        return Unrouted(path, 'shared binary file')
    owners = owners_of_lines(g, base and base[1], have[1],
                             {n: e[1] for n, e in features.items()})
    mine = collections.defaultdict(list)
    for h in hs:
        os_, ol, _, _ = h
        who = set()
        for i in range(os_, os_ + ol):
            who |= owners.get(i, set())
        if not who:
            before = os_ if ol == 0 else os_ - 1
            after = os_ + 1 if ol == 0 else os_ + ol
            who = owners.get(before, set()) | owners.get(after, set())
        if not who:
            return Unrouted(path, 'hunk at line %d has no owner' % os_)
        for n in who:
            mine[n].append(h)
    old = split_lines(g.blob(have[1]))
    new = split_lines(g.blob(want[1]))
    out = {}
    for n, hs in mine.items():
        theirs = g.hash_blob(apply_hunks(old, new, hs))
        merged = merge_file(g, features[n][1], have[1], theirs)
        if merged is None:
            return Unrouted(path, 'conflict applying to %s' % n)
        out[n] = (want[0], merged)
    return out


def merge_file(g, ours, base, theirs):
    """Three-way merge of blobs; the merged blob, or None on conflict."""
    r = g.run('merge-file', '-p', '--object-id', ours, base, theirs,
              ok=range(0, 128))
    if r.returncode != 0:
        return None
    return g.hash_blob(r.stdout)


def edit_tree(g, commit, edits):
    """COMMIT's tree with EDITS ({path: (mode, oid) or None}) applied."""
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, GIT_INDEX_FILE=os.path.join(tmp, 'index'))
        g.run('read-tree', commit, env=env)
        recs = []
        for path, entry in sorted(edits.items()):
            if entry is None:
                recs.append('0 %s\t%s' % ('0' * 40, path))
            else:
                recs.append('%s %s\t%s' % (entry[0], entry[1], path))
        g.run('update-index', '-z', '--index-info',
              input=('\0'.join(recs) + '\0').encode(), env=env)
        return g.out('write-tree', env=env)
