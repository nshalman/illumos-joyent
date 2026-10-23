#!/usr/bin/env python3
"""Write the first feature metadata files from the phase 1 analysis.

  metadata_bootstrap.py OUT-DIR FEATURE...

One file per FEATURE in OUT-DIR, in the format feature-tools/metadata.py
reads: the description from buckets.py, Depends from the static analysis
(data/deps.json) plus the Makefile edges stackplan.py knows, Owner left
for a person, and Upstream "keep" unless noted below.  Run once; after
that the metadata lives on meta/state and is edited there.
"""
import json
import os
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from buckets import BUCKETS  # noqa: E402
from stackplan import EXTRA  # noqa: E402

# Features phase 1 did not produce.
OTHER = {
    'tooling': ('Tools for maintaining these features: gate intake, '
                'dispatch, releases, replay (feature-tools/), and '
                'README-SmartOS.md.', 'keep', []),
    'upstream-8391': ('8391 mr_sas controller lockup on Dell H330, committed '
                      'on master (4896e3cfc6b) before illumos-gate has it; '
                      'carried until gate lands it.', 'upstream', ['8391']),
}


def render(fields):
    out = []
    for k, v in fields:
        lines = v.split('\n') if v else ['']
        out.append('%s: %s' % (k, lines[0]) if lines[0] else '%s:' % k)
        out.extend(' ' + l for l in lines[1:])
    return '\n'.join(out) + '\n'


def main():
    out, names = sys.argv[1], sys.argv[2:]
    deps = json.load(open(os.path.join(HERE, 'data', 'deps.json')))
    extra = {}
    for a, b in EXTRA:
        extra.setdefault(a, set()).add(b)
    buckets = {b: (subject, body) for b, subject, body in BUCKETS}
    os.makedirs(out, exist_ok=True)
    for n in names:
        if n in OTHER:
            desc, upstream, tickets = OTHER[n]
        else:
            subject, body = buckets[n]
            desc = subject[0].upper() + subject[1:] + '.\n' + body
            upstream, tickets = 'keep', []
        d = sorted((set(deps.get(n, {})) | extra.get(n, set())) & set(names))
        desc = '\n'.join(textwrap.wrap(desc.split('\n', 1)[0], 72) +
                         textwrap.wrap(' '.join(desc.split('\n')[1:]), 72))
        with open(os.path.join(out, n), 'w') as f:
            f.write(render([('Feature', n), ('Description', desc),
                            ('Owner', ''), ('Depends', ', '.join(d)),
                            ('Upstream', upstream),
                            ('Upstream-Tickets', ', '.join(tickets)),
                            ('Tests', '')]))


if __name__ == '__main__':
    main()
