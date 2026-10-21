# illumos-joyent restructure

Generates a branch that re-expresses illumos-joyent `master` as about 80
topical commits on top of the illumos-gate commit it last merged.  The
branch's final tree is byte-identical to `master`.

To see what the commits look like without running anything, read
`branch-log.txt`: each commit's message and `--stat`, oldest first.

The same delta is also built as independent branches, one per feature,
each applying to illumos-gate on its own (`./hunks.py && ./features.py`);
`features-log.txt` shows those, and an octopus merge of all of them
reproduces `master`'s tree.  `buildcheck-results.txt` records which
of them build alone on illumos-gate, and that every one that does not
builds once merged with the features it needs.

Suspected bugs, deliberate divergences from upstream and cleanup
candidates found along the way are in `FINDINGS.md`.

Phase 2, maintaining these features as branches on illumos-gate with
tooling, is designed in `WORKFLOW.md`, a living document.  Decisions it
reaches land as tools on the `features/tooling` branch.

## Running it

You need an illumos-joyent clone with `master`, an `illumos` remote
for illumos-gate, and (for the lx commits) an `omniosce` remote for
OmniOS.  Then:

    ILLUMOS=/path/to/illumos-joyent ./collect.sh   # about a minute
    ILLUMOS=/path/to/illumos-joyent ./build.py --branch joyent-restructure

`build.py` creates or resets `joyent-restructure` in that clone,
verifies its tree against `master`, puts the clone back on the branch it
was on, and rewrites `branch-log.txt`.  The clone's working tree must be
clean.  Then look at the branch, from the base named at the top of
`branch-log.txt` (also `BASE` in `data/refs`):

    git log --stat <base>..joyent-restructure

`./build.py --messages DIR` writes just the commit messages.
