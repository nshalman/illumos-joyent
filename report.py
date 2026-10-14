#!/usr/bin/env python3
"""Reports over the classifier's output.

  report.py buckets            bucket sizes and how files got there
  report.py files [BUCKET]     files per bucket (all buckets if omitted)
  report.py why PATH...        ticket shares of each file's '+' lines
  report.py tickets [N]        top N tickets by '+' lines in files that the
                               path rules do not place (the hard cases)
  report.py bucket-tickets B   tickets that wrote B's lines, by line count
  report.py boundary           files whose '+' lines blame to upstream
                               commits at or before BASE (stale-line suspects)
  report.py merge-lines        files with '+' lines blamed to merge commits
"""
import collections
import sys

import classify as C


def subjects(commits):
    subj = {}
    for h, (t, s, d) in sorted(commits.items(), key=lambda x: x[1][2]):
        subj.setdefault(t, (d, s.split(' Reviewed by')[0]))
    return subj


def shares(c, n=4):
    tot = sum(c.values()) or 1
    return ' '.join('%s:%d%%' % (k, 100 * v // tot) for k, v in c.most_common(n))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'buckets'
    args = sys.argv[2:]
    commits, delta, blame, assign, how, votes, tb = C.classify()
    raw = C.load_raw_blame()

    if cmd == 'buckets':
        c = collections.Counter(assign.values())
        for b, n in c.most_common():
            hc = collections.Counter(how[f] for f in assign if assign[f] == b)
            print('%-16s %4d  %s' % (b, n, dict(hc)))
    elif cmd == 'files':
        g = collections.defaultdict(list)
        for f, b in assign.items():
            g[b].append(f)
        for b in sorted(g):
            if args and b not in args:
                continue
            print('== %s (%d)' % (b, len(g[b])))
            for f in sorted(g[b]):
                print('   %-8s %s' % (how[f], f))
    elif cmd == 'why':
        subj = subjects(commits)
        for f in args:
            if not f.startswith('usr/src/') and f not in assign:
                f = 'usr/src/' + f
            print('%s [%s via %s] %d lines' % (f, assign.get(f), how.get(f),
                  sum(blame[f].values())))
            for t, n in blame[f].most_common(8):
                print('   %5d %-12s %s' % (n, t, subj.get(t, ('', ''))[1][:90]))
    elif cmd == 'tickets':
        n = int(args[0]) if args else 50
        subj = subjects(commits)
        lines = collections.Counter()
        files = collections.defaultdict(set)
        for f in assign:
            if how[f] == 'path':
                continue
            for t, k in blame[f].items():
                lines[t] += k
                files[t].add(f.split('/')[-1])
        for t, k in lines.most_common(n):
            print('%-12s %5d  %s  [%s]' % (t, k, subj.get(t, ('', ''))[1][:90],
                  ','.join(sorted(files[t])[:6])))
    elif cmd == 'bucket-tickets':
        subj = subjects(commits)
        lines = collections.Counter()
        for f, b in assign.items():
            if b in args:
                lines.update(blame[f])
        for t, k in lines.most_common():
            print('%-12s %6d  %s' % (t, k, subj.get(t, ('', ''))[1][:100]))
    elif cmd == 'boundary':
        for f in sorted(raw):
            n = raw[f].get('BOUNDARY', 0)
            if n:
                print('%5d  %-16s %s' % (n, assign.get(f), f))
    elif cmd == 'merge-lines':
        for f in sorted(blame):
            n = blame[f].get('MERGE', 0)
            if n:
                print('%5d  %-16s %s' % (n, assign.get(f), f))
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == '__main__':
    main()
