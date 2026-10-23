# meta/state

Sync state for the illumos-joyent feature branches. This is an orphan
branch: it shares no history with illumos-gate, and it is never merged
or rebased. Each sync, and each shadow-mode run, adds a commit here.

The features themselves are the `features/*` branches, each based on an
illumos-gate commit. The tooling that maintains them will live on
`features/tooling`. The analysis that produced the first split is on
the `meta/restructure` branch.

## Files

- `gate`: the illumos-gate commit every feature branch is based on.
- `reference`: the illumos-joyent master commit whose tree the
  integration of all features equals (in shadow mode, the last master
  commit reproduced).
- `features.tsv`: one line per feature, its name and its branch tip at
  the time of this commit, which is also what `features/*` on the fork
  holds. `features/tooling` is not listed: master does not carry it
  while shadow mode runs beside it.
- each `shadow/<date>/tips.tsv` keeps the tips as that run left them,
  so every past state of a feature stays reachable.
- `decisions`: placement decisions a person made where routing could
  not, for dispatch and replay: `PATH FEATURE` or `commit:SHA FEATURE`
  lines, each with its reason in a comment.
- `shadow/<date>/`: shadow-mode runs over master's new commits.
- `replay/<date>-<name>/`: replays of past master history through the
  tools, kept apart from live state. Each has a README with the
  setup and results, and the tool's step log.

Planned, as the tooling arrives: the shared rerere cache, per-sync
reports, and the conflict log.

## Bootstrap

The first commit records the split produced by `meta/restructure`:
78 features on gate 479a4a914dc, whose merge equals illumos-joyent
master da512a7e2e6 tree for tree.
