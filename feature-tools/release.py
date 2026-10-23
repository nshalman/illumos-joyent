#!/usr/bin/env python3
"""Releases: cut one from gate plus features, and check it later.

A release is cut at a gate intake: the release branch is the
integration commit itself, gate plus the chain of feature merges, and
its tree must equal master's.  cut() builds it from the current
features and checks that, and that merging it into master changes
nothing.

After the cut, fixes land on master first and are cherry-picked to the
release, or (urgently) land on the release first and must reach master
too.  merge_check() merges the release into master for real: master's
tree must not change.  When it does, each release commit master lacks
is named, told apart by patch-id as a gate backport not yet in master
or a fix never landed on master.

recut() rebuilds a past release from its gate commit, gate backports
and the features at its fork, and checks it against the release's tip:
the audit the replay used.

  release.py cut --repo DIR --name NAME [--master refs/heads/master]
             [--prefix refs/heads/features/] [--write] [--push REMOTE]
             [--exclude FEATURE]...
  release.py check --repo DIR --release REF [--master refs/heads/master]
             --gate-ref illumos/master
  release.py audit --repo DIR --gate GATE --fork FORK --tip TIP
             --gate-ref illumos/master --integration COMMIT

cut writes the branch refs/heads/NAME only with --write.  audit's
--integration names the integration commit for FORK (one of replay.py's
steps), from which the features are read.
"""
import argparse
import collections
import sys

import ft
import intake
import resolve

Recut = collections.namedtuple(
    'Recut', 'commit gate features backports routed unrouted equal')
Check = collections.namedtuple('Check', 'ok missing')


class ReleaseError(Exception):
    pass


def cut(g, features, gate, master):
    """The release branch tip: FEATURES integrated on GATE.

    Its tree must equal MASTER's, and merging it into MASTER must leave
    MASTER's tree unchanged; otherwise ReleaseError.
    """
    integ = ft.integrate(g, gate, sorted(features.items()))
    if integ.conflicts:
        raise ReleaseError('the features do not merge: %s' % integ.conflicts)
    if g.tree(integ.commit) != g.tree(master):
        raise ReleaseError('the features do not give master\'s tree; '
                           'dispatch has not caught up')
    tree, paths = ft.merge_tree(g, master, integ.commit)
    if paths or tree != g.tree(master):
        raise ReleaseError('merging the cut into master changes master')
    return integ.commit


def merge_check(g, release, master, gate_ref):
    """Merge RELEASE into MASTER and check master's tree does not change.

    Returns Check: `ok`, and `missing`, the release commits master lacks
    by patch-id, each as (commit, 'gate backport not yet in master') or
    (commit, 'fix not on master').
    """
    tree, paths = ft.merge_tree(g, master, release)
    ok = not paths and tree == g.tree(master)
    upstream = gate_patch_ids(g, master, gate_ref)
    missing = []
    for line in g.out('cherry', master, release).splitlines():
        sign, commit = line.split()
        if sign != '+':
            continue
        kind = ('gate backport not yet in master'
                if patch_id(g, commit) in upstream else 'fix not on master')
        missing.append((commit, kind))
    return Check(ok and not missing, missing)


def features_of(g, integration, gate):
    """{name: commit} merged by ft.integrate() into INTEGRATION on GATE."""
    feats = {}
    cur = integration
    while cur != gate:
        parents = g.out('rev-list', '--parents', '-n1', cur).split()[1:]
        subject = g.out('log', '-1', '--format=%s', cur)
        if len(parents) != 2 or not subject.startswith('Merge feature '):
            raise ft.GitError('%s is not a feature merge' % cur)
        feats[subject[len('Merge feature '):]] = parents[1]
        cur = parents[0]
    return feats


def patch_ids(g, text):
    out = g.out('patch-id', '--stable', input=text)
    return [line.split() for line in out.splitlines()]


def gate_patch_ids(g, gate, gate_ref):
    """{patch-id: commit} for the gate commits GATE..GATE_REF."""
    log = g.run('log', '-p', '--no-merges', '--no-ext-diff', '--no-color',
                '%s..%s' % (gate, gate_ref)).stdout
    return dict(patch_ids(g, log))


def patch_id(g, commit):
    ids = patch_ids(g, g.run('show', '--no-ext-diff', '--no-color',
                             commit).stdout)
    return ids[0][0] if ids else None


def recut(g, features, gate, fork, tip, gate_ref):
    """Rebuild release FORK..TIP from GATE and FEATURES (at FORK)."""
    feats = dict(features)
    side = gate
    commits = g.out('rev-list', '--reverse', '%s..%s' % (fork, tip)).split()
    if g.out('rev-list', '--merges', '%s..%s' % (fork, tip)):
        raise ft.GitError('%s..%s contains merges' % (fork, tip))
    upstream = gate_patch_ids(g, gate, gate_ref) if commits else {}
    backports, routed, unrouted = [], {}, []
    for c in commits:
        if patch_id(g, c) in upstream:
            tree, paths = ft.merge_tree(g, side, c, base=c + '^')
            if paths:
                unrouted += [ft.Unrouted(p, 'backport %s conflicts' % c[:11])
                             for p in paths]
                break
            new_side = g.commit_tree(tree, [side], g.message(c), g.author(c))
            for n in sorted(feats):
                feats[n] = ft.rebase(g, side, feats[n], new_side,
                                     resolve=resolve.resolve_file).tip
            side = new_side
            backports.append(c)
        else:
            integ = ft.integrate(g, side, sorted(feats.items())).commit
            target, paths = ft.merge_tree(g, integ, c, base=c + '^')
            if paths:
                unrouted += [ft.Unrouted(p, '%s conflicts' % c[:11])
                             for p in paths]
                break
            r = ft.route(g, side, feats, target, g.message(c), g.author(c))
            feats.update(r.commits)
            routed[c] = sorted(r.commits)
            unrouted += r.unrouted
    final = ft.integrate(g, side, sorted(feats.items()))
    equal = (not unrouted and not final.conflicts and
             g.tree(final.commit) == g.tree(tip))
    return Recut(final.commit, side, feats, backports, routed, unrouted,
                 equal)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('cut')
    c.add_argument('--name', required=True)
    c.add_argument('--master', default='refs/heads/master')
    c.add_argument('--prefix', default='refs/heads/features/')
    c.add_argument('--write', action='store_true')
    c.add_argument('--push')
    c.add_argument('--exclude', action='append', default=[],
                   metavar='FEATURE')
    k = sub.add_parser('check')
    k.add_argument('--release', required=True)
    k.add_argument('--master', default='refs/heads/master')
    k.add_argument('--gate-ref', required=True)
    au = sub.add_parser('audit')
    for arg in ('gate', 'fork', 'tip', 'gate-ref', 'integration'):
        au.add_argument('--' + arg, required=True)
    for p in (c, k, au):
        p.add_argument('--repo', required=True)
    a = ap.parse_args()
    g = ft.Git(a.repo)
    if a.cmd == 'cut':
        feats = intake.features_at(g, a.prefix, a.exclude)
        gate = intake.common_gate(g, feats)
        tip = cut(g, feats, gate, g.rev(a.master))
        print('release %s: %s (gate %s, %d features)' % (
            a.name, tip[:11], gate[:11], len(feats)))
        if a.write:
            g.run('update-ref', 'refs/heads/' + a.name, tip, '0' * 40)
            if a.push:
                g.run('push', a.push, '%s:refs/heads/%s' % (tip, a.name))
        return 0
    if a.cmd == 'check':
        res = merge_check(g, g.rev(a.release), g.rev(a.master),
                          g.rev(a.gate_ref))
        for commit, kind in res.missing:
            print('%s: %s' % (kind, g.out('log', '-1', '--format=%h %s',
                                          commit)))
        print('release %s: %s' % (a.release, 'ok' if res.ok else
                                  'NOT in master'))
        return 0 if res.ok else 1
    gate = g.rev(a.gate)
    res = recut(g, features_of(g, g.rev(a.integration), gate), gate,
                g.rev(a.fork), g.rev(a.tip), g.rev(a.gate_ref))
    for c in res.backports:
        print('backport  %s' % g.out('log', '-1', '--format=%h %s', c))
    for c, names in res.routed.items():
        print('routed    %s -> %s' % (
            g.out('log', '-1', '--format=%h %s', c), ' '.join(names)))
    for u in res.unrouted:
        print('unrouted  %s (%s)' % (u.path, u.reason))
    print('release %s: %s' % (a.tip, 'equal' if res.equal else 'DIFFERS'))
    return 0 if res.equal else 1


if __name__ == '__main__':
    sys.exit(main())
