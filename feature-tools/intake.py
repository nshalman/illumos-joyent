#!/usr/bin/env python3
"""Gate intake: take a new illumos-gate commit in.

Every feature is rebased onto the gate commit, through the conflict
resolvers (resolve.py) and the manifest sync (manifest.py); the features
are merged in a chain onto it; and, once that integration is checked,
it becomes master's gate-merge commit.  A feature gate has absorbed
completely is retired.

When the target cannot be reached cleanly, because a feature conflicts,
features no longer merge, or the check fails, the first bad gate commit
is found by bisecting, gate is taken in up to the commit before it, and
the features stuck at the bad commit are left on candidate branches for
a person.

  intake.py --repo DIR --to GATE-COMMIT [--prefix refs/heads/features/]
            [--master refs/heads/master] [--gate-ref illumos/master]
            [--check COMMAND] [--no-resolvers] [--report DIR] [--write]
            [--candidates refs/heads/intake/] [--push REMOTE]
            [--open-issues OWNER/REPO] [--exclude FEATURE]...

Without --write nothing changes: the outcome is printed, and with
--report written as files.  --check runs COMMAND with the integration
commit in $INTEGRATION; nonzero means the integration is not good (a
build, or tests).  --write updates the feature refs, adds the
gate-merge commit to master, and creates the candidate branches;
--push then pushes them to REMOTE, the rebased features with
--force-with-lease.  Each stuck feature is escalated as an issue,
written under the report directory and opened on GitHub only with
--open-issues.
"""
import argparse
import collections
import json
import os
import subprocess
import sys

import escalate
import ft
import manifest
import resolve as resolvers


class IntakeError(Exception):
    pass


Intake = collections.namedtuple(
    'Intake', 'gate features conflicts resolved synced emptied retired held '
    'integration ok')
TakeIn = collections.namedtuple(
    'TakeIn', 'taken reached bad stuck candidates check_failed')


def ancestor(g, a, b):
    return g.run('merge-base', '--is-ancestor', a, b,
                 ok=(0, 1)).returncode == 0


def intake(g, features, old_gate, new_gate, resolve=None, sync=None):
    """Rebase FEATURES from OLD_GATE onto NEW_GATE and integrate them.

    RESOLVE is passed to ft.rebase(); SYNC(g, old, new, feature) returns
    (new commit or None, report), as manifest.sync_feature does.  The
    result is ok when no conflict is left and the features merge.
    """
    if not ancestor(g, old_gate, new_gate):
        raise IntakeError('%s does not descend from %s' % (new_gate,
                                                          old_gate))
    feats, conflicts, resolved, synced, emptied = {}, {}, {}, {}, {}
    for n in sorted(features):
        r = ft.rebase(g, old_gate, features[n], new_gate, resolve=resolve)
        tip = r.tip
        if r.conflicts:
            conflicts[n] = sorted(set(p for _, ps in r.conflicts
                                      for p in ps))
        if r.resolved:
            resolved[n] = [[p, names] for _, p, names in r.resolved]
        if r.emptied:
            emptied[n] = r.emptied
        if sync:
            commit, report = sync(g, old_gate, new_gate, tip)
            if commit:
                tip = commit
                synced[n] = {k: len(v) for k, v in report.items()
                             if v and k in ('added', 'changed', 'removed')}
        feats[n] = tip
    retired = sorted(n for n in feats if g.tree(feats[n]) == g.tree(new_gate))
    for n in retired:
        del feats[n]
    integ = ft.integrate(g, new_gate, sorted(feats.items()))
    ok = not conflicts and not integ.conflicts
    return Intake(new_gate, feats, conflicts, resolved, synced, emptied,
                  retired, integ.conflicts, integ.commit, ok)


def gate_commits(g, old_gate, new_gate):
    return g.out('rev-list', '--first-parent', '--reverse',
                 '%s..%s' % (old_gate, new_gate)).split()


def first_bad(g, features, old_gate, new_gate, resolve=None, sync=None,
              check=None, cache=None):
    """The first gate commit after OLD_GATE that cannot be taken in.

    A commit cannot be taken in when intake onto it is not ok, or CHECK
    (given the integration commit) returns false.  Bisects gate's
    first-parent history, assuming that once bad it stays bad.  None if
    NEW_GATE itself is good.  CACHE, a dict, keeps each probe's Intake.
    """
    cache = {} if cache is None else cache

    def good(c):
        if c not in cache:
            r = intake(g, features, old_gate, c, resolve, sync)
            cache[c] = (r, r.ok and (check is None or check(r.integration)))
        return cache[c][1]
    commits = gate_commits(g, old_gate, new_gate)
    if not commits or good(commits[-1]):
        return None
    lo, hi = 0, len(commits) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if good(commits[mid]):
            lo = mid + 1
        else:
            hi = mid
    good(commits[lo])
    return commits[lo]


def take_in(g, features, old_gate, new_gate, resolve=None, sync=None,
            check=None):
    """Take gate in as far toward NEW_GATE as it can go cleanly.

    Returns TakeIn: `taken`, the Intake for the commit reached (None if
    nothing could be taken); `reached`; `bad`, the first gate commit that
    could not be taken in (None if NEW_GATE was reached); `stuck`, the
    features that conflict or do not merge there; `candidates`, their
    attempts at `bad` (keeping the feature's side of each conflict) for
    a person to finish; and `check_failed`, true when `bad` failed only
    the check.
    """
    cache = {}
    bad = first_bad(g, features, old_gate, new_gate, resolve, sync, check,
                    cache)
    if bad is None:
        full = cache[new_gate][0] if new_gate in cache else intake(
            g, features, old_gate, new_gate, resolve, sync)
        return TakeIn(full, new_gate, None, [], {}, False)
    at_bad = cache[bad][0]
    stuck = sorted(set(at_bad.conflicts) | set(n for n, _ in at_bad.held))
    candidates = {n: at_bad.features[n] for n in stuck
                  if n in at_bad.features}
    commits = gate_commits(g, old_gate, new_gate)
    i = commits.index(bad)
    reached = commits[i - 1] if i else old_gate
    taken = None
    if reached != old_gate:
        taken = cache[reached][0] if reached in cache else intake(
            g, features, old_gate, reached, resolve, sync)
    return TakeIn(taken, reached, bad, stuck, candidates, at_bad.ok)


def write_gate_merge(g, master, gate_commit, integration, message=None):
    """Master's gate-merge commit: parents MASTER and GATE_COMMIT, with
    INTEGRATION's tree, which must be built on GATE_COMMIT."""
    if not ancestor(g, gate_commit, integration):
        raise IntakeError('%s is not built on %s' % (integration,
                                                     gate_commit))
    tree = g.tree(integration)
    msg = (message or '[illumos-gate merge]\n') + (
        '\nGate-intake: %s\n' % gate_commit)
    merge = g.commit_tree(tree, [master, gate_commit], msg)
    if g.tree(merge) != tree:
        raise IntakeError('gate merge %s lost the integration tree' % merge)
    return merge


def features_at(g, prefix, exclude=()):
    """{name: commit} for the refs under PREFIX, but those in EXCLUDE.

    EXCLUDE is for features master does not carry, such as the tooling
    while shadow mode runs beside master.
    """
    feats = {}
    for line in g.out('for-each-ref', '--format=%(refname) %(objectname)',
                      prefix).splitlines():
        ref, oid = line.split()
        name = ref[len(prefix):]
        if name not in exclude:
            feats[name] = oid
    return feats


def common_gate(g, features):
    """The gate commit all FEATURES are built on."""
    base = g.out('merge-base', '--octopus', *features.values())
    for n, c in features.items():
        if not ancestor(g, base, c):
            raise IntakeError('%s is not built on %s' % (n, base))
    return base


def describe(g, res):
    out = []
    taken = res.taken
    if taken:
        out.append('took gate in to %s' % g.out('log', '-1', '--format=%h %s',
                                                res.reached))
        for n, paths in sorted(taken.conflicts.items()):
            out.append('    conflict  %s: %s' % (n, ' '.join(paths)))
        for n, rs in sorted(taken.resolved.items()):
            out.append('    resolved  %s: %s' % (n, ' '.join(
                '%s (%s)' % (p, ','.join(names)) for p, names in rs)))
        for n, counts in sorted(taken.synced.items()):
            out.append('    synced    %s: %s' % (n, ' '.join(
                '%s %d' % kv for kv in sorted(counts.items()))))
        if taken.retired:
            out.append('    retired   %s (gate has all of it)' %
                       ' '.join(taken.retired))
    else:
        out.append('took nothing in')
    if res.bad:
        out.append('stopped at %s' % g.out('log', '-1', '--format=%h %s',
                                           res.bad))
        if res.check_failed:
            out.append('    the check failed there')
        for n in res.stuck:
            out.append('    stuck     %s' % n)
    return '\n'.join(out)


def issue(g, res, name, candidates):
    """(title, body) of the escalation for stuck feature NAME."""
    subject = g.out('log', '-1', '--format=%h %s', res.bad)
    title = 'Gate intake: %s stuck at %s' % (name, subject)
    body = ('Gate intake could not rebase or merge feature `%s` onto gate '
            'commit %s.\n\nIts attempt, keeping the feature\'s side of each '
            'conflict, is on `%s%s/features/%s`.  Fix it there and run gate '
            'intake again.\n' % (name, subject, candidates, res.bad, name))
    return title, body


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--repo', required=True)
    ap.add_argument('--to', required=True)
    ap.add_argument('--prefix', default='refs/heads/features/')
    ap.add_argument('--master', default='refs/heads/master')
    ap.add_argument('--gate-ref')
    ap.add_argument('--check')
    ap.add_argument('--no-resolvers', action='store_true')
    ap.add_argument('--report')
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--candidates', default='refs/heads/intake/')
    ap.add_argument('--push')
    ap.add_argument('--open-issues', metavar='OWNER/REPO')
    ap.add_argument('--exclude', action='append', default=[],
                    metavar='FEATURE')
    a = ap.parse_args()
    g = ft.Git(a.repo)
    feats = features_at(g, a.prefix, a.exclude)
    old = common_gate(g, feats)
    new = g.rev(a.to)
    if a.gate_ref and not ancestor(g, new, g.rev(a.gate_ref)):
        raise IntakeError('%s is not on %s' % (new, a.gate_ref))
    master = g.rev(a.master)
    before = ft.integrate(g, old, sorted(feats.items()))
    if before.conflicts or g.tree(before.commit) != g.tree(master):
        raise IntakeError('the features on %s do not give master\'s tree; '
                          'dispatch has not caught up' % old)
    check = None
    if a.check:
        def check(integration):
            env = dict(os.environ, INTEGRATION=integration)
            return subprocess.run(a.check, shell=True, env=env).returncode == 0
    tools = {} if a.no_resolvers else dict(resolve=resolvers.resolve_file,
                                           sync=manifest.sync_feature)
    res = take_in(g, feats, old, new, check=check, **tools)
    print(describe(g, res))
    if a.report:
        os.makedirs(os.path.join(a.report, 'issues'), exist_ok=True)
        with open(os.path.join(a.report, 'intake.txt'), 'w') as f:
            f.write(describe(g, res) + '\n')
        if res.taken:
            with open(os.path.join(a.report, 'tips.tsv'), 'w') as f:
                for n, c in sorted(res.taken.features.items()):
                    f.write('%s\t%s\n' % (n, c))
            with open(os.path.join(a.report, 'intake.json'), 'w') as f:
                json.dump(res.taken._asdict(), f, indent=1, sort_keys=True)
        for n in res.stuck:
            title, body = issue(g, res, n, a.candidates)
            url = escalate.escalate(os.path.join(a.report, 'issues'), n,
                                    title, body, a.open_issues)
            if url:
                print('opened %s' % url)
    if not a.write:
        return 0 if res.bad is None else 1
    pushes = []
    if res.taken:
        merge = write_gate_merge(g, master, res.reached,
                                 res.taken.integration)
        g.run('update-ref', a.master, merge, master)
        pushes.append(('%s:%s' % (merge, a.master), None))
        for n, c in res.taken.features.items():
            g.run('update-ref', a.prefix + n, c, feats[n])
            pushes.append(('%s:%s%s' % (c, a.prefix, n), feats[n]))
        for n in res.taken.retired:
            g.run('update-ref', '-d', a.prefix + n, feats[n])
            pushes.append((':%s%s' % (a.prefix, n), feats[n]))
    for n, c in res.candidates.items():
        ref = '%s%s/features/%s' % (a.candidates, res.bad, n)
        g.run('update-ref', ref, c)
        pushes.append(('%s:%s' % (c, ref), None))
    if a.push:
        for spec, lease in pushes:
            ref = spec.split(':', 1)[1]
            args = ['push', a.push, spec]
            if lease:
                args.insert(1, '--force-with-lease=%s:%s' % (ref, lease))
            g.run(*args)
    return 0 if res.bad is None else 1


if __name__ == '__main__':
    sys.exit(main())
