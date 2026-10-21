#!/usr/bin/env python3
"""Replay master's history through the feature tools.

Start from features whose integration on a gate commit equals master
commit FROM, and walk master's first-parent history to TO.  A merge is
a gate merge: every feature is rebased onto its second parent.  Any
other commit is a joyent change, routed to the features it touches.
Then whatever still differs from master's tree is routed as well: that
is the work a person would have done, such as resolving a conflict.
After each step the integration must equal master's tree; the replay
stops at the first step where it does not.

  replay.py --repo DIR --gate GATE --from FROM --to TO
            [--prefix refs/heads/features/] [--gate-ref illumos/master]
            [--decide FILE] [--log FILE] [--out-prefix refs/replay/]

--decide names a file of "path feature" lines for changes the routing
rules cannot place.  --log writes each step as JSON.  The replayed
features are written under --out-prefix.
"""
import argparse
import collections
import json
import sys

import ft


class ReplayError(Exception):
    pass


Step = collections.namedtuple(
    'Step', 'commit kind conflicts emptied held routed unrouted equal '
    'integration')
Result = collections.namedtuple('Result', 'steps features gate')


def ancestor(g, a, b):
    return g.run('merge-base', '--is-ancestor', a, b,
                 ok=(0, 1)).returncode == 0


def replay(g, features, gate, start, end, decide=None, gate_ref=None,
           log=None):
    """Replay START..END onto FEATURES ({name: commit}) based on GATE."""
    feats = dict(features)
    integ = ft.integrate(g, gate, sorted(feats.items()))
    if integ.conflicts or g.tree(integ.commit) != g.tree(start):
        raise ReplayError('features on %s do not reproduce %s' %
                          (gate, start))
    steps = []
    for m in g.out('rev-list', '--first-parent', '--reverse',
                   '%s..%s' % (start, end)).split():
        parents = g.out('rev-list', '--parents', '-n1', m).split()[1:]
        conflicts, emptied = {}, {}
        if len(parents) == 2:
            kind, new_gate = 'gate', parents[1]
            if not ancestor(g, gate, new_gate):
                raise ReplayError('%s: %s does not descend from gate %s' %
                                  (m, new_gate, gate))
            if gate_ref and not ancestor(g, new_gate, gate_ref):
                raise ReplayError('%s: %s is not on %s' %
                                  (m, new_gate, gate_ref))
            for n in sorted(feats):
                r = ft.rebase(g, gate, feats[n], new_gate)
                feats[n] = r.tip
                if r.conflicts:
                    conflicts[n] = sorted(set(p for _, ps in r.conflicts
                                              for p in ps))
                if r.emptied:
                    emptied[n] = r.emptied
            gate = new_gate
            msg, author = 'Resolve as master did in %s\n' % m, None
        elif len(parents) == 1:
            kind, msg, author = 'joyent', g.message(m), g.author(m)
        else:
            raise ReplayError('%s: %d parents' % (m, len(parents)))
        held, routed, unrouted = [], [], []
        integ = ft.integrate(g, gate, sorted(feats.items()))
        if integ.conflicts:
            held = integ.conflicts
        else:
            r = ft.route(g, gate, feats, g.tree(m), msg, author, decide)
            feats.update(r.commits)
            routed, unrouted = sorted(r.commits), r.unrouted
            integ = ft.integrate(g, gate, sorted(feats.items()))
        equal = (not integ.conflicts and
                 g.tree(integ.commit) == g.tree(m))
        step = Step(m, kind, conflicts, emptied, held, routed, unrouted,
                    equal, integ.commit)
        steps.append(step)
        if log:
            log(step)
        if not equal:
            break
    return Result(steps, feats, gate)


def describe(g, step):
    subject = g.out('log', '-1', '--format=%s', step.commit)
    out = ['%s %-6s %s %s' % (step.commit[:11], step.kind,
                              'ok  ' if step.equal else 'FAIL', subject[:60])]
    for n, paths in sorted(step.conflicts.items()):
        out.append('    conflict  %s: %s' % (n, ' '.join(paths)))
    for n, cs in sorted(step.emptied.items()):
        out.append('    emptied   %s: %d commit(s)' % (n, len(cs)))
    for n, paths in step.held:
        out.append('    held back %s: %s' % (n, ' '.join(paths)))
    if step.routed:
        out.append('    routed    %s' % ' '.join(step.routed))
    for u in step.unrouted:
        out.append('    unrouted  %s (%s)' % (u.path, u.reason))
    return '\n'.join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--repo', required=True)
    ap.add_argument('--gate', required=True)
    ap.add_argument('--from', dest='start', required=True)
    ap.add_argument('--to', dest='end', required=True)
    ap.add_argument('--prefix', default='refs/heads/features/')
    ap.add_argument('--gate-ref')
    ap.add_argument('--decide')
    ap.add_argument('--log')
    ap.add_argument('--out-prefix', default='refs/replay/')
    a = ap.parse_args()
    g = ft.Git(a.repo)
    feats = {}
    for line in g.out('for-each-ref', '--format=%(refname) %(objectname)',
                      a.prefix).splitlines():
        ref, oid = line.split()
        feats[ref[len(a.prefix):]] = oid
    decide = {}
    if a.decide:
        for line in open(a.decide):
            line = line.split('#')[0].split()
            if line:
                decide[line[0]] = line[1]
    logf = open(a.log, 'w') if a.log else None

    def log(step):
        print(describe(g, step), flush=True)
        if logf:
            d = step._asdict()
            d['unrouted'] = [list(u) for u in step.unrouted]
            logf.write(json.dumps(d, sort_keys=True) + '\n')
            logf.flush()

    res = replay(g, feats, g.rev(a.gate), g.rev(a.start), g.rev(a.end),
                 decide, a.gate_ref, log)
    for n, c in res.features.items():
        g.run('update-ref', a.out_prefix + n, c)
    ok = res.steps and all(s.equal for s in res.steps)
    print('%d step(s), %s; features under %s' % (
        len(res.steps), 'all equal to master' if ok else 'stopped',
        a.out_prefix))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
