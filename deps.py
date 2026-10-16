#!/usr/bin/env python3
"""Estimate which feature branches need which others to compile.

For each features/<name> branch, take the lines it adds in C, header,
assembly, yacc and lex files, and collect the identifiers those lines
define (#define, function definitions with the name at column 0,
struct/union/enum tags, typedef names, struct members and enum
constants) and use (every identifier token outside comments and string
literals).  An identifier is *new* if BASE does not contain it as a word
anywhere.  Feature F depends on feature G if F uses a new identifier
that G defines and F does not.

This is a static estimate: it misses dependencies through Makefiles,
manifests and data files, and an identifier defined by several features
counts as a dependency on each of them.  Only a build settles it.

  deps.py          summary: independent features, dependency edges
  deps.py -v       also the identifiers behind each edge

Writes data/deps.json.
"""
import collections
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import features as F  # noqa: E402

SRC = re.compile(r'\.(c|h|s|S|y|l|il|in|d)$')
IDENT = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
KEYWORDS = set('''auto break case char const continue default do double else
enum extern float for goto if inline int long register restrict return short
signed sizeof static struct switch typedef union unsigned void volatile while
_Bool boolean_t uint8_t uint16_t uint32_t uint64_t int8_t int16_t int32_t
int64_t size_t ssize_t uintptr_t intptr_t NULL B_TRUE B_FALSE define include
ifdef ifndef endif undef elif pragma defined'''.split())
DEFS = [
    re.compile(r'^\s*#\s*define\s+([A-Za-z_]\w*)'),
    re.compile(r'^([A-Za-z_]\w*)\s*\('),                      # fn at col 0
    re.compile(r'\b(?:struct|union|enum)\s+([A-Za-z_]\w*)\s*\{'),
    re.compile(r'^\s*}\s*([A-Za-z_]\w*)\s*;'),                # } name_t;
    re.compile(r'^\s*typedef\b.*?\b([A-Za-z_]\w*)\s*;'),
    re.compile(r'^\s+[A-Za-z_][\w\s\*]*?\b([A-Za-z_]\w*)\s*(?:\[[^]]*\])?'
               r'\s*(?::\s*\d+)?\s*;'),                       # member
    re.compile(r'^\s+([A-Z_][A-Z0-9_]{2,})\s*(?:=[^,]*)?,?\s*(?:/\*.*)?$'),
]


def strip(line):
    # a block comment's continuation line (" * text")
    if re.match(r'^\s*\*(\s|/|$)', line):
        return ''
    line = re.sub(r'"(\\.|[^"\\])*"', '""', line)
    line = re.sub(r"'(\\.|[^'\\])*'", "''", line)
    line = re.sub(r'/\*.*?\*/', ' ', line)
    return re.sub(r'(//|/\*).*$', ' ', line)


def base_words(cand):
    """The candidates that occur as a word in any BASE source file."""
    paths = [l.split('\t', 1) for l in F.out('ls-tree', '-r', F.BASE).split('\n')]
    shas = [meta.split()[2] for meta, p in paths
            if SRC.search(p) and meta.split()[1] == 'blob']
    # feed the ids from a file: writing them all to a pipe before reading
    # any output deadlocks once cat-file's output pipe fills
    idf = F.DATA + '/base-blobs.txt'
    with open(idf, 'w') as fp:
        fp.write('\n'.join(shas) + '\n')
    p = subprocess.Popen(['git', '-C', F.ILLUMOS, 'cat-file', '--batch'],
                         stdin=open(idf), stdout=subprocess.PIPE)
    found = set()
    word = re.compile(rb'[A-Za-z_][A-Za-z0-9_]*')
    for _ in shas:
        hdr = p.stdout.readline().split()
        data = p.stdout.read(int(hdr[2]))
        p.stdout.read(1)
        found.update(w for w in set(word.findall(data)))
    p.wait()
    os.unlink(idf)
    return set(w.decode() for w in found) & cand


def added_lines(branch):
    lines = collections.defaultdict(list)
    cur = None
    diff = F.run('diff', '--no-ext-diff', '--no-renames', '-U0', F.BASE,
                 branch).stdout.decode('utf-8', 'replace')
    for l in diff.splitlines():
        if l.startswith('+++ b/'):
            cur = l[6:] if SRC.search(l[6:]) else None
        elif cur and l.startswith('+') and not l.startswith('+++'):
            lines[cur].append(l[1:])
    return lines


def main():
    verbose = '-v' in sys.argv
    names = [r[len('refs/heads/' + F.PREFIX):] for r in F.out(
        'for-each-ref', '--format=%(refname)',
        'refs/heads/' + F.PREFIX).split('\n') if r]
    defs, uses = {}, {}
    for n in names:
        d, u = set(), set()
        incomment = False
        for path, ls in added_lines(F.PREFIX + n).items():
            for l in ls:
                if incomment:
                    if '*/' in l:
                        incomment = False
                        l = l.split('*/', 1)[1]
                    else:
                        continue
                s = strip(l)
                if '/*' in l and '*/' not in l.split('/*', 1)[1]:
                    incomment = True
                for r in DEFS:
                    m = r.search(s)
                    if m:
                        d.add(m.group(1))
                u.update(IDENT.findall(s))
        defs[n], uses[n] = d - KEYWORDS, u - KEYWORDS
    cand = set().union(*defs.values())
    inbase = base_words(cand)
    new = {n: d - inbase for n, d in defs.items()}
    definers = collections.defaultdict(set)
    for n, d in new.items():
        for x in d:
            definers[x].add(n)
    edges = collections.defaultdict(lambda: collections.defaultdict(set))
    for n in names:
        for x in uses[n] - defs[n]:
            for g in definers.get(x, ()):
                if g != n:
                    edges[n][g].add(x)
    json.dump({n: {g: sorted(xs) for g, xs in es.items()}
               for n, es in edges.items()},
              open(F.DATA + '/deps.json', 'w'), indent=1, sort_keys=True)

    order = [b for b, _, _ in F.BUCKETS if b in names]
    indep = [n for n in order if not edges.get(n)]
    print('%d feature branches; %d new identifiers defined; %d defined by '
          'more than one feature' % (len(names), len(definers),
                                     sum(1 for g in definers.values()
                                         if len(g) > 1)))
    print('no detected dependencies (%d): %s' % (len(indep), ', '.join(indep)))
    print('dependencies (feature -> needs: identifiers):')
    for n in order:
        if not edges.get(n):
            continue
        es = sorted(edges[n].items(), key=lambda kv: -len(kv[1]))
        print('  %-18s %s' % (n, ', '.join('%s(%d)' % (g, len(xs))
                                           for g, xs in es)))
        if verbose:
            for g, xs in es:
                print('      %-16s %s' % (g, ' '.join(sorted(xs)[:12])))


if __name__ == '__main__':
    main()
