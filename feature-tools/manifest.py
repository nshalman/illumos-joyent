#!/usr/bin/env python3
"""Keep the top-level manifest in step with gate's package manifests.

The top-level `manifest` lists every path in the SmartOS platform image:

  f path mode owner group     a file
  d path mode owner group     a directory
  s path=target               a symbolic link
  h path=target               a hard link, target from the top of the tree

It is joyent's own file, carried by one feature, and it has to follow
gate's package manifests (usr/src/pkg/manifests/*.p5m and *.inc).  A
rebase never conflicts over this, so after each one the feature that
carries the manifest gets these changes, for each path whose package
action changed between the old and new gate commit:

- a path gate removes is removed;
- a path gate changes, if listed, is rewritten in place;
- a path gate adds is listed only if the package file declaring it
  already has paths in the manifest (packages are in or out as a
  whole: os-tests is out), right after the largest key below it.

Mode, owner and group come from the package action, or else from the
nearest listed entry of the same type in the same directory.  Master's
own updates in 2026 follow these rules; see replay/2026-10-21-small on
the meta/state branch.
"""
import bisect
import collections
import posixpath
import shlex

import ft

PKG = 'usr/src/pkg/manifests/'
MANIFEST = 'manifest'
KINDS = {'file': 'f', 'dir': 'd', 'link': 's', 'hardlink': 'h'}
MACROS = {'ARCH64': 'amd64', 'ARCH': 'i386', 'i386_ONLY': ''}
DROP = ('$(sparc_ONLY)',)


def parse_p5m(text):
    """The file, dir, link and hardlink actions in a package manifest.

    Returns (kind, attributes) pairs.  Actions for other architectures,
    and actions still holding a macro this module does not know, are
    left out.
    """
    actions, buf = [], ''
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.endswith('\\'):
            buf += line[:-1] + ' '
            continue
        line, buf = (buf + line).strip(), ''
        if not line or line[0] in '#<' or line.startswith(DROP):
            continue
        for name, value in MACROS.items():
            line = line.replace('$(%s)' % name, value)
        if '$(' in line:
            continue
        try:
            words = shlex.split(line)
        except ValueError:
            continue
        if not words or words[0] not in KINDS:
            continue
        attrs = {}
        for w in words[1:]:
            if '=' in w:
                k, v = w.split('=', 1)
                attrs.setdefault(k, v)
        if 'path' in attrs:
            actions.append((words[0], attrs))
    return actions


def package_actions(g, commit):
    """{path: [(declaring file, kind, attributes)]} at gate COMMIT."""
    files = []
    listing = g.run('ls-tree', '-r', '-z', commit, '--', PKG).stdout
    for rec in listing.decode().split('\0'):
        if rec:
            meta, path = rec.split('\t', 1)
            if path.endswith(('.p5m', '.inc')):
                files.append((path, meta.split()[2]))
    texts = g.blobs(oid for _, oid in files)
    out = collections.defaultdict(list)
    for path, oid in sorted(files):
        for kind, attrs in parse_p5m(texts[oid].decode(errors='replace')):
            out[attrs['path']].append((path, kind, attrs))
    return out


def shape(decls):
    """What of a path's package actions shows in the manifest."""
    if not decls:
        return None
    return sorted(set((k, a.get('mode', ''), a.get('owner', ''),
                       a.get('group', ''), a.get('target', ''))
                      for _, k, a in decls))


def key(line):
    words = line.split()
    if len(words) >= 2 and words[0] in ('f', 'd', 's', 'h'):
        return words[1]
    return None


def path_of(line):
    k = key(line)
    return k and k.split('=', 1)[0]


class Listing:
    """The manifest's entries, for lookups."""

    def __init__(self, lines):
        self.index = {}
        self.bydir = collections.defaultdict(list)
        for i, line in enumerate(lines):
            p = path_of(line)
            if p is None:
                continue
            self.index[p] = i
            words = line.split()
            if words[0] in ('f', 'd') and len(words) == 5:
                self.bydir[(words[0], posixpath.dirname(p))].append(
                    (p, words[2:5]))
        for v in self.bydir.values():
            v.sort()

    def sibling(self, letter, path):
        """Mode, owner and group of the nearest entry like PATH."""
        near = self.bydir.get((letter, posixpath.dirname(path)))
        if not near:
            return None
        i = bisect.bisect_left(near, (path,))
        return near[i - 1][1] if i > 0 else near[0][1]


def line_for(path, kind, attrs, listing):
    if kind == 'link':
        return 's %s=%s' % (path, attrs['target'])
    if kind == 'hardlink':
        t = attrs['target']
        t = t.lstrip('/') if t.startswith('/') else posixpath.normpath(
            posixpath.join(posixpath.dirname(path), t))
        return 'h %s=%s' % (path, t)
    letter = KINDS[kind]
    have = [attrs.get('mode'), attrs.get('owner'), attrs.get('group')]
    if not all(have):
        sib = listing.sibling(letter, path)
        if sib is None:
            return None
        have = [h or s for h, s in zip(have, sib)]
    return '%s %s %s %s %s' % (letter, path, *have)


def sync(g, old_gate, new_gate, text):
    """TEXT, a manifest, brought from OLD_GATE's packages to NEW_GATE's.

    Returns (new text, report); the report lists the paths added,
    changed and removed, and those left alone: 'not shipped' (their
    package has nothing in the manifest), 'already listed' (gate now
    delivers a path the manifest had listed on its own) and 'no
    attributes' (no mode, owner or group to be found).
    """
    report = {k: [] for k in ('added', 'changed', 'removed', 'not shipped',
                              'already listed', 'no attributes')}
    if g.tree(old_gate) == g.tree(new_gate):
        return text, report
    old, new = package_actions(g, old_gate), package_actions(g, new_gate)
    lines = text.decode('utf-8', 'surrogateescape').split('\n')
    listing = Listing(lines)
    shipped = set(f for p, decls in new.items() if p in listing.index
                  for f, _, _ in decls)
    replace, remove, insert = {}, set(), []
    for path in sorted(set(old) | set(new)):
        o, n = shape(old.get(path)), shape(new.get(path))
        if o == n:
            continue
        i = listing.index.get(path)
        if n is None:
            if i is not None:
                remove.add(i)
                report['removed'].append(path)
            continue
        _, kind, attrs = new[path][0]
        if i is not None and o is None:
            report['already listed'].append(path)
            continue
        if i is None and not any(f in shipped for f, _, _ in new[path]):
            report['not shipped'].append(path)
            continue
        line = line_for(path, kind, attrs, listing)
        if line is None:
            report['no attributes'].append(path)
        elif i is not None:
            if line != lines[i]:
                replace[i] = line
                report['changed'].append(path)
        else:
            insert.append(line)
            report['added'].append(path)
    out = [replace.get(i, l) for i, l in enumerate(lines) if i not in remove]
    for line in sorted(insert, key=key):
        k = key(line).encode()
        best = None
        for i, l in enumerate(out):
            lk = key(l)
            if lk is not None and lk.encode() < k and (
                    best is None or lk.encode() > key(out[best]).encode()):
                best = i
        if best is None:
            best = next((i for i, l in enumerate(out) if key(l)), 0) - 1
        out.insert(best + 1, line)
    return '\n'.join(out).encode('utf-8', 'surrogateescape'), report


def sync_feature(g, old_gate, new_gate, commit, path=MANIFEST):
    """Sync the manifest in feature COMMIT, if it carries one.

    Returns (new commit or None, report or None).
    """
    have = g.entries(commit, [path]).get(path)
    if have is None:
        return None, None
    text, report = sync(g, old_gate, new_gate, g.blob(have[1]))
    if text == g.blob(have[1]):
        return None, report
    tree = ft.edit_tree(g, commit, {path: (have[0], g.hash_blob(text))})
    msg = 'manifest: follow gate %s..%s\n\n' % (old_gate[:11], new_gate[:11])
    for k in ('added', 'changed', 'removed'):
        if report[k]:
            msg += '%s:\n%s\n' % (k.capitalize(), ''.join(
                '    %s\n' % p for p in report[k]))
    return g.commit_tree(tree, [commit], msg), report
