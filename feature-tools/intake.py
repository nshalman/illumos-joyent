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
a person.  A person fixes one by committing on it; the next intake takes
the fixed feature from there (a candidate whose tree is still the
tool's attempt is not taken in), and --write removes it once used.

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
import metadata
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


Rebased = collections.namedtuple('Rebased',
                                 'tip conflicts resolved emptied synced')


def rebase_feature(g, tip, old_gate, new_gate, resolve=None, sync=None):
    """One feature's TIP rebased from OLD_GATE onto NEW_GATE, as intake does.

    Returns Rebased: the new `tip`; the paths left in `conflicts`; the
    paths `resolved` by RESOLVE, as [path, resolver names]; the commits
    `emptied`; and the manifest entries `synced` by SYNC, counted by kind
    (None when SYNC changed nothing).
    """
    if old_gate == new_gate:
        return Rebased(tip, [], [], [], None)
    r = ft.rebase(g, old_gate, tip, new_gate, resolve=resolve)
    tip = r.tip
    conflicts = sorted(set(p for _, ps in r.conflicts for p in ps))
    resolved = [[p, names] for _, p, names in r.resolved]
    synced = None
    if sync:
        commit, report = sync(g, old_gate, new_gate, tip)
        if commit:
            tip = commit
            synced = {k: len(v) for k, v in report.items()
                      if v and k in ('added', 'changed', 'removed')}
    return Rebased(tip, conflicts, resolved, r.emptied, synced)


def intake(g, features, old_gate, new_gate, resolve=None, sync=None,
           fixed=None):
    """Rebase FEATURES from OLD_GATE onto NEW_GATE and integrate them.

    RESOLVE is passed to ft.rebase(); SYNC(g, old, new, feature) returns
    (new commit or None, report), as manifest.sync_feature does.  FIXED,
    from fixed_candidates(), gives features a person fixed at a gate
    commit: {name: (gate commit, tip)}; such a feature is rebased from
    that tip once NEW_GATE includes its gate commit.  The result is ok
    when no conflict is left and the features merge.
    """
    if not ancestor(g, old_gate, new_gate):
        raise IntakeError('%s does not descend from %s' % (new_gate,
                                                          old_gate))
    feats, conflicts, resolved, synced, emptied = {}, {}, {}, {}, {}
    for n in sorted(features):
        base, tip = old_gate, features[n]
        if fixed and n in fixed and ancestor(g, fixed[n][0], new_gate):
            base, tip = fixed[n]
        r = rebase_feature(g, tip, base, new_gate, resolve, sync)
        feats[n] = r.tip
        for out, value in ((conflicts, r.conflicts), (resolved, r.resolved),
                           (emptied, r.emptied)):
            if value:
                out[n] = value
        if r.synced is not None:
            synced[n] = r.synced
    retired = sorted(n for n in feats if g.tree(feats[n]) == g.tree(new_gate))
    for n in retired:
        del feats[n]
    integ = ft.integrate(g, new_gate, ft.chain(feats))
    ok = not conflicts and not integ.conflicts
    return Intake(new_gate, feats, conflicts, resolved, synced, emptied,
                  retired, integ.conflicts, integ.commit, ok)


def gate_commits(g, old_gate, new_gate):
    return g.out('rev-list', '--first-parent', '--reverse',
                 '%s..%s' % (old_gate, new_gate)).split()


def first_bad(g, features, old_gate, new_gate, resolve=None, sync=None,
              check=None, cache=None, fixed=None):
    """The first gate commit after OLD_GATE that cannot be taken in.

    A commit cannot be taken in when intake onto it is not ok, or CHECK
    (given the integration commit) returns false.  Bisects gate's
    first-parent history, assuming that once bad it stays bad.  None if
    NEW_GATE itself is good.  CACHE, a dict, keeps each probe's Intake.
    FIXED is passed to intake().
    """
    cache = {} if cache is None else cache

    def good(c):
        if c not in cache:
            r = intake(g, features, old_gate, c, resolve, sync, fixed)
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
            check=None, fixed=None):
    """Take gate in as far toward NEW_GATE as it can go cleanly.

    Returns TakeIn: `taken`, the Intake for the commit reached (None if
    nothing could be taken); `reached`; `bad`, the first gate commit that
    could not be taken in (None if NEW_GATE was reached); `stuck`, the
    features that conflict or do not merge there; `candidates`, their
    attempts at `bad` (keeping the feature's side of each conflict) for
    a person to finish; and `check_failed`, true when `bad` failed only
    the check.  FIXED is passed to intake().
    """
    cache = {}
    bad = first_bad(g, features, old_gate, new_gate, resolve, sync, check,
                    cache, fixed)
    if bad is None:
        full = cache[new_gate][0] if new_gate in cache else intake(
            g, features, old_gate, new_gate, resolve, sync, fixed)
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
            g, features, old_gate, reached, resolve, sync, fixed)
    return TakeIn(taken, reached, bad, stuck, candidates, at_bad.ok)


def fixed_candidates(g, features, old_gate, new_gate, prefix, resolve=None,
                     sync=None):
    """Candidates a person fixed: {name: (gate commit, tip)}.

    A candidate is PREFIX<gate commit>/features/<name>, for a gate
    commit after OLD_GATE up to NEW_GATE.  It counts as fixed when it
    sits on that gate commit, with no later gate commit in it, and its
    tree differs from the attempt intake makes there; an unchanged
    attempt is not taken in.  The latest fixed one per feature wins.
    """
    commits = gate_commits(g, old_gate, new_gate)
    at = {c: i for i, c in enumerate(commits)}
    out = {}
    refs = g.out('for-each-ref', '--format=%(refname)', prefix).split()
    for ref in refs:
        parts = ref[len(prefix):].split('/')
        if len(parts) != 3 or parts[1] != 'features':
            continue
        c, n = parts[0], parts[2]
        if c not in at or n not in features:
            continue
        tip = g.rev(ref)
        if g.out('merge-base', tip, new_gate) != c:
            continue
        if n in out and at[out[n][0]] > at[c]:
            continue
        attempt = rebase_feature(g, features[n], old_gate, c, resolve, sync)
        if g.tree(attempt.tip) != g.tree(tip):
            out[n] = (c, tip)
    return out


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


def describe(g, res, landed=(), used=()):
    """RES as text; LANDED is metadata.watch's watched tickets taken in,
    USED the fixed candidates taken in, as (name, gate commit)."""
    out = []
    taken = res.taken
    if taken:
        out.append('took gate in to %s' % g.out('log', '-1', '--format=%h %s',
                                                res.reached))
        for n, c in used:
            out.append('    picked up %s fixed at %s' % (n, c[:11]))
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
        for n, ticket, commit in landed:
            out.append('    upstream  %s landed in %s (%s)' % (
                ticket, g.out('log', '-1', '--format=%h', commit),
                '%s retired' % n if n in taken.retired else
                '%s still differs from gate: review' % n))
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
    ap.add_argument('--state', default=metadata.STATE)
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
    has_state = metadata.use_order(g, a.state)
    feats = features_at(g, a.prefix, a.exclude)
    old = common_gate(g, feats)
    new = g.rev(a.to)
    if a.gate_ref and not ancestor(g, new, g.rev(a.gate_ref)):
        raise IntakeError('%s is not on %s' % (new, a.gate_ref))
    master = g.rev(a.master)
    before = ft.integrate(g, old, ft.chain(feats))
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
    fixed = fixed_candidates(g, feats, old, new, a.candidates, **tools)
    res = take_in(g, feats, old, new, check=check, fixed=fixed, **tools)
    used = sorted((n, c) for n, (c, _) in fixed.items()
                  if res.taken and ancestor(g, c, res.reached))
    meta = metadata.load(g, a.state) if has_state else {}
    landed = metadata.watch(g, meta, old, res.reached) if res.taken else []
    print(describe(g, res, landed, used))
    if a.report:
        os.makedirs(os.path.join(a.report, 'issues'), exist_ok=True)
        with open(os.path.join(a.report, 'intake.txt'), 'w') as f:
            f.write(describe(g, res, landed, used) + '\n')
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
        for n, c in used:
            ref = '%s%s/features/%s' % (a.candidates, c, n)
            g.run('update-ref', '-d', ref, fixed[n][1])
            pushes.append((':' + ref, fixed[n][1]))
        retired = metadata.retire(meta, res.taken.retired, res.reached)
        if retired:
            state = g.rev(a.state)
            metadata.save(g, a.state, retired, 'Retire %s: gate has all of '
                          'it as of %s\n' % (', '.join(sorted(retired)),
                                             res.reached))
            pushes.append(('%s:%s' % (g.rev(a.state), a.state), state))
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
