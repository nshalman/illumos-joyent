#!/usr/bin/env python3
"""Feature metadata: what each feature is, kept on the meta/state branch.

Each feature has a file, features/<name>, of "Key: value" lines (a line
starting with a space continues the value before it):

  Feature: lx
  Description: The lx brand: Linux binary compatibility in a zone.
  Owner: someone@example.com
  Depends: brand-ops, brand-process, hyprlofs
  Upstream: keep
  Upstream-Tickets:
  Tests: lx-tests

Upstream is the intent: keep (ours for good), upstream (to be offered to
illumos, or carried until gate lands it) or landed (gate has it; the
feature is retired).  Upstream-Tickets are the illumos tickets gate
intake watches for.  Depends orders the merge chain and the builds.

  metadata.py check --repo DIR [--state refs/heads/meta/state]
              [--prefix refs/heads/features/] [--exclude FEATURE]...
  metadata.py order --repo DIR [--state ...] [--prefix ...]
"""
import argparse
import collections
import re
import sys

import ft

FIELDS = ['Feature', 'Description', 'Owner', 'Depends', 'Upstream',
          'Upstream-Tickets', 'Tests']
DIR = 'features/'
STATE = 'refs/heads/meta/state'
TICKET = re.compile(r'^(\d+)\s', re.M)


def parse(text):
    """{key: value} from a metadata file's TEXT."""
    out = collections.OrderedDict()
    key = None
    for line in text.splitlines():
        if line[:1].isspace() and key:
            out[key] += '\n' + line.strip()
        elif ':' in line:
            key, value = line.split(':', 1)
            out[key.strip()] = value.strip()
    return dict(out)


def render(meta):
    """A metadata file's text for META, fields in the usual order."""
    keys = [k for k in FIELDS if k in meta] + sorted(k for k in meta
                                                     if k not in FIELDS)
    out = []
    for k in keys:
        first, *rest = (meta[k] or '').split('\n')
        out.append('%s: %s' % (k, first) if first else '%s:' % k)
        out.extend(' ' + line for line in rest)
    return '\n'.join(out) + '\n'


def _list(meta, key):
    return [x.strip() for x in (meta.get(key) or '').split(',') if x.strip()]


def depends(meta):
    return _list(meta, 'Depends')


def tickets(meta):
    return _list(meta, 'Upstream-Tickets')


def stub(name, description, tickets=(), upstream='upstream'):
    """Metadata for a new feature, for a person to complete."""
    return {'Feature': name, 'Description': description, 'Owner': '',
            'Depends': '', 'Upstream': upstream,
            'Upstream-Tickets': ', '.join(tickets), 'Tests': ''}


def _components(meta, names):
    """Strongly connected components of the dependency graph on NAMES."""
    names = set(names)
    edges = {n: [d for d in depends(meta.get(n, {})) if d in names]
             for n in names}
    index, low, stack, on, comps = {}, {}, [], set(), []

    def visit(v):
        index[v] = low[v] = len(index)
        stack.append(v)
        on.add(v)
        for w in edges[v]:
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            comps.append(sorted(comp))
    for n in sorted(names):
        if n not in index:
            visit(n)
    return comps, edges


def cycles(meta):
    """Groups of features that depend on each other, each sorted."""
    comps, _ = _components(meta, meta)
    return sorted(c for c in comps if len(c) > 1)


def order(meta, names):
    """NAMES with every feature after those it depends on.

    Ties go by name; features in a cycle stay together, by name.
    """
    comps, edges = _components(meta, names)
    of = {n: i for i, c in enumerate(comps) for n in c}
    needs = {i: set(of[d] for n in c for d in edges[n]) - {i}
             for i, c in enumerate(comps)}
    out, done = [], set()
    while len(done) < len(comps):
        ready = [i for i in needs if i not in done and needs[i] <= done]
        i = min(ready, key=lambda i: comps[i][0])
        out.extend(comps[i])
        done.add(i)
    return out


def check(meta, branches):
    """Problems between metadata META and the feature BRANCHES."""
    branches = set(branches)
    out = []
    for b in sorted(branches):
        if b not in meta:
            out.append('feature %s has no metadata' % b)
    for n in sorted(meta):
        for d in depends(meta[n]):
            if d not in branches:
                out.append('feature %s depends on %s, which is not a '
                           'feature' % (n, d))
    for n in sorted(meta):
        if n not in branches and meta[n].get('Upstream') != 'landed':
            out.append('metadata for %s, but no such feature branch' % n)
    for c in cycles({n: m for n, m in meta.items() if n in branches}):
        out.append('features %s depend on each other' % ', '.join(c))
    return out


def watch(g, meta, old_gate, new_gate):
    """(feature, ticket, gate commit) for watched tickets gate landed."""
    wanted = {t: n for n, m in meta.items() for t in tickets(m)}
    out = []
    log = g.out('log', '--format=%H%x00%B%x01', '--reverse',
                '%s..%s' % (old_gate, new_gate))
    for rec in log.split('\x01'):
        if '\x00' not in rec:
            continue
        commit, body = rec.strip('\n').split('\x00', 1)
        for t in TICKET.findall(body):
            if t in wanted:
                out.append((wanted[t], t, commit))
    return out


def load(g, ref=STATE):
    """{name: metadata} from the features/ directory on REF."""
    files = []
    listing = g.run('ls-tree', '-z', ref, '--', DIR).stdout.decode()
    for rec in listing.split('\0'):
        if rec:
            meta, path = rec.split('\t', 1)
            if meta.split()[1] == 'blob':
                files.append((path[len(DIR):], meta.split()[2]))
    texts = g.blobs(oid for _, oid in files)
    return {n: parse(texts[oid].decode()) for n, oid in sorted(files)}


def use_order(g, ref=STATE):
    """Merge features in REF's dependency order (see ft.chain).

    False, leaving the order by name, if REF does not exist.
    """
    if g.run('rev-parse', '-q', '--verify', ref, ok=(0, 1)).returncode:
        return False
    meta = load(g, ref)
    ft.set_order(lambda names: order(meta, names))
    return True


def save(g, ref, metas, message):
    """Write METAS ({name: metadata, or None to remove}) on REF."""
    return ft.commit_files(g, ref, {
        DIR + n: (None if m is None else render(m).encode())
        for n, m in metas.items()}, message)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('check', 'order'):
        p = sub.add_parser(name)
        p.add_argument('--repo', required=True)
        p.add_argument('--state', default=STATE)
        p.add_argument('--prefix', default='refs/heads/features/')
        p.add_argument('--exclude', action='append', default=[],
                       metavar='FEATURE')
    a = ap.parse_args()
    import intake  # it orders its chains with this module
    g = ft.Git(a.repo)
    meta = load(g, a.state)
    branches = intake.features_at(g, a.prefix, a.exclude)
    if a.cmd == 'order':
        print('\n'.join(order(meta, branches)))
        return 0
    problems = check(meta, branches)
    for p in problems:
        print(p)
    print('%d features, %d problems' % (len(branches), len(problems)))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
