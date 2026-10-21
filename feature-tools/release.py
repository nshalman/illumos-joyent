#!/usr/bin/env python3
"""Rebuild a release from gate, gate backports and features.

A release branch forks from master at FORK and may carry commits of its
own.  Rebuilt the feature way, a release is:

- its gate commit, plus the gate commits backported onto it: a release
  commit is a backport when it has the same patch-id as a gate commit
  between the release's gate commit and GATE_REF;
- the features as they were at FORK, rebased onto that gate side, with
  the release's other commits routed to the features owning their
  lines.

recut() builds that and checks its tree against the release's tip.

  release.py --repo DIR --gate GATE --fork FORK --tip TIP
             --gate-ref illumos/master --integration COMMIT

--integration names the integration commit for FORK (one of replay.py's
steps), from which the features are read.
"""
import argparse
import collections
import sys

import ft
import resolve

Recut = collections.namedtuple(
    'Recut', 'commit gate features backports routed unrouted equal')


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
    for arg in ('repo', 'gate', 'fork', 'tip', 'gate-ref', 'integration'):
        ap.add_argument('--' + arg, required=True)
    a = ap.parse_args()
    g = ft.Git(a.repo)
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
