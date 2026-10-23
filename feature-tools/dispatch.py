#!/usr/bin/env python3
"""Dispatch: keep the features in step with master.

After a commit lands on master, dispatch routes its pieces into the
features it touches (ft.route), using the decisions file and any
"Feature:" trailers in the commit message, and checks that the features,
merged on their gate commit, give exactly that commit's tree.  On
success the features gain the routed commits (only ever adding commits)
and master gains a dispatch record: a merge of the verified integration,
naming the dispatched commit in a Dispatched-commit trailer.

A dry run does the same for a pull request before it merges, writing
nothing, and reports where each part would go and which placements need
a "Feature:" trailer.

  dispatch.py dry-run --repo DIR --head COMMIT [--base REV]
            [--message FILE] [--decisions FILE] [--prefix P]
  dispatch.py land --repo DIR [--master refs/heads/master]
            [--decisions FILE] [--prefix P] [--write] [--push REMOTE]
            [--report DIR] [--open-issues OWNER/REPO]

dry-run: HEAD is the pull request's merge result, BASE (default master)
what it merges into; --message gives the squash message, whose
trailers count, if not HEAD's own.  Exits 1 if a placement is needed or
the features would not give HEAD's tree.

land: dispatches every master commit since the last dispatch record or
gate intake, in order, stopping at the first that fails.  Nothing
changes without --write; --push pushes the features (fast-forward) and
master to REMOTE.  A commit that cannot be dispatched is escalated as an
issue, written under --report and opened on GitHub only with
--open-issues.
"""
import argparse
import collections
import os
import sys

import escalate
import ft
import intake

RECORD = 'Dispatched-commit'
INTAKE = 'Gate-intake'


class DispatchError(Exception):
    pass


Dispatch = collections.namedtuple(
    'Dispatch', 'features routed unrouted equal integration')


def dispatch(g, features, gate, commit, decide=None, message=None,
             integ=None):
    """Route COMMIT's tree into FEATURES (built on GATE).

    DECIDE holds standing decisions (the decisions file); trailers in
    MESSAGE (default: COMMIT's message) add to them.  INTEG, if given,
    is FEATURES' integration on GATE, already computed.
    """
    msg = g.message(commit) if message is None else message
    decisions = dict(decide or {})
    decisions.update(ft.decisions_from_message(msg))
    target = g.tree(commit)
    r = ft.route(g, gate, features, target, msg, g.author(commit),
                 decisions, integ=integ)
    feats = dict(features)
    feats.update(r.commits)
    out = ft.integrate(g, gate, sorted(feats.items()))
    equal = (not out.conflicts and not r.unrouted and
             g.tree(out.commit) == target)
    return Dispatch(feats, sorted(r.commits), r.unrouted, equal, out.commit)


def placement(g, before, after):
    """{feature: [paths]} each feature changed between BEFORE and AFTER."""
    out = {}
    for n, c in sorted(after.items()):
        old = before.get(n) or c + '^'
        if old == c:
            continue
        paths = g.out('diff-tree', '-r', '--name-only', '--no-renames',
                      old, c).split('\n')
        out[n] = sorted(p for p in paths if p)
    return out


def write_record(g, master, commit, integration, routed):
    """Master's dispatch record for COMMIT, on top of MASTER.

    INTEGRATION must have COMMIT's tree, or nothing is written.  The
    record keeps MASTER's tree; when MASTER is COMMIT, both parents have
    that tree, which is checked as well.
    """
    if g.tree(integration) != g.tree(commit):
        raise DispatchError('integration %s does not have the tree of %s' %
                            (integration, commit))
    subject = g.out('log', '-1', '--format=%s', commit)
    msg = 'Dispatch %s %s\n\nFeatures: %s\n\n%s: %s\n' % (
        commit[:11], subject, ', '.join(routed) or '(none)', RECORD, commit)
    tree = g.tree(master)
    rec = g.commit_tree(tree, [master, integration], msg)
    if g.tree(rec) != tree:
        raise DispatchError('record %s lost master\'s tree' % rec)
    if master == commit and g.tree(rec) != g.tree(integration):
        raise DispatchError('record %s differs from its integration' % rec)
    return rec


def pending(g, tip, stop_tree=None, limit=5000):
    """Master commits up to TIP not yet dispatched, oldest first.

    They follow the newest dispatch record or gate intake on master's
    first-parent line, or the newest commit with STOP_TREE (the tree the
    features give now).
    """
    out = []
    log = g.run('log', '--first-parent', '-n', str(limit),
                '--format=%H%x00%T%x00%B%x01', tip).stdout.decode()
    for rec in log.split('\x01'):
        rec = rec.strip('\n')
        if not rec:
            continue
        commit, tree, body = rec.split('\0', 2)
        trailers = [line.split(':', 1)[0] for line in body.splitlines()]
        if RECORD in trailers or INTAKE in trailers or tree == stop_tree:
            return list(reversed(out))
        out.append(commit)
    raise DispatchError('no dispatch record or gate intake in the last %d '
                        'commits of %s' % (limit, tip))


def read_decisions(path):
    """{path: feature} from a decisions file of "path feature" lines."""
    decide = {}
    if path:
        for line in open(path):
            words = line.split('#')[0].split()
            if words:
                decide[words[0]] = words[1]
    return decide


def describe_unrouted(unrouted):
    out = []
    for u in unrouted:
        out.append('    needs a placement: %s (%s)' % (u.path, u.reason))
    if unrouted:
        out.append('    add a trailer to the squash message, for example:')
        out.append('        Feature: <feature>')
        out.append('    or, for one path only:')
        out.append('        Feature: <feature> %s' % unrouted[0].path)
    return out


def dry_run(a, g):
    feats = intake.features_at(g, a.prefix)
    gate = intake.common_gate(g, feats)
    base = g.rev(a.base)
    integ = ft.integrate(g, gate, sorted(feats.items()))
    if integ.conflicts or g.tree(integ.commit) != g.tree(base):
        raise DispatchError('the features do not give %s\'s tree; dispatch '
                            'has not caught up' % a.base)
    message = open(a.message).read() if a.message else None
    head = g.rev(a.head)
    r = dispatch(g, feats, gate, head, read_decisions(a.decisions), message,
                 integ=integ)
    print('Dispatch dry run for %s' % head[:11])
    for n, paths in placement(g, feats, r.features).items():
        print('    %s: %s' % (n, ' '.join(paths)))
    for line in describe_unrouted(r.unrouted):
        print(line)
    print('    integration matches: %s' % ('yes' if r.equal else 'NO'))
    return 0 if r.equal else 1


def land(a, g):
    feats = intake.features_at(g, a.prefix)
    gate = intake.common_gate(g, feats)
    integ = ft.integrate(g, gate, sorted(feats.items()))
    if integ.conflicts:
        raise DispatchError('the features do not merge: %s' % integ.conflicts)
    tip = g.rev(a.master)
    todo = pending(g, tip, stop_tree=g.tree(integ.commit))
    if todo and g.tree(todo[0] + '^') != g.tree(integ.commit):
        raise DispatchError('the features do not give the tree before %s' %
                            todo[0])
    decide = read_decisions(a.decisions)
    pushed = {}
    for c in todo:
        r = dispatch(g, feats, gate, c, decide)
        subject = g.out('log', '-1', '--format=%h %s', c)
        if not r.equal:
            print('dispatch failed for %s' % subject)
            for line in describe_unrouted(r.unrouted):
                print(line)
            if a.report:
                body = ('Dispatch could not place commit %s in the '
                        'features, or the features did not give its tree.'
                        '\n\n```\n%s\n```\n\nRecord a placement in the '
                        'decisions file and run dispatch again.\n' %
                        (subject, '\n'.join(describe_unrouted(r.unrouted))))
                url = escalate.escalate(
                    os.path.join(a.report, 'issues'), c[:11],
                    'Dispatch failed: %s' % subject, body, a.open_issues)
                if url:
                    print('opened %s' % url)
            return 1
        print('dispatched %s -> %s' % (subject, ', '.join(r.routed) or '-'))
        if not a.write:
            feats = r.features
            continue
        master = g.rev(a.master)
        rec = write_record(g, master, c, r.integration, r.routed)
        for n, new in r.features.items():
            old = feats.get(n)
            if old == new:
                continue
            if old and not intake.ancestor(g, old, new):
                raise DispatchError('%s would not fast-forward' % n)
            g.run('update-ref', a.prefix + n, new, *([old] if old else []))
            pushed[n] = new
        g.run('update-ref', a.master, rec, master)
        feats = r.features
    if a.write and a.push:
        for n, c in sorted(pushed.items()):
            g.run('push', a.push, '%s:%s%s' % (c, a.prefix, n))
        g.run('push', a.push, '%s:%s' % (g.rev(a.master), a.master))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    d = sub.add_parser('dry-run')
    d.add_argument('--head', required=True)
    d.add_argument('--base', default='refs/heads/master')
    d.add_argument('--message')
    ld = sub.add_parser('land')
    ld.add_argument('--master', default='refs/heads/master')
    ld.add_argument('--write', action='store_true')
    ld.add_argument('--push')
    ld.add_argument('--report')
    ld.add_argument('--open-issues', metavar='OWNER/REPO')
    for p in (d, ld):
        p.add_argument('--repo', required=True)
        p.add_argument('--decisions')
        p.add_argument('--prefix', default='refs/heads/features/')
    a = ap.parse_args()
    g = ft.Git(a.repo)
    return dry_run(a, g) if a.cmd == 'dry-run' else land(a, g)


if __name__ == '__main__':
    sys.exit(main())
