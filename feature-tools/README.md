# feature-tools

Tools for maintaining illumos-joyent's delta as feature branches on
illumos-gate. The design, and the reasons for it, are in `WORKFLOW.md` on
the `meta/restructure` branch; this file says which command does what.

## The process

- Developers land on `master` by squash-merging a pull request.
- **Dispatch** routes each landed commit into the feature branches
  (`features/<name>`) it touches and checks that the features, merged on
  their gate commit, give exactly master's tree. Before the merge, a dry run
  shows the placement on the pull request.
- **Gate intake** rebases every feature onto a new illumos-gate commit,
  merges them all, and writes master's gate-merge commit from the result.
- **Release cuts** are made at a gate intake from gate plus the features.

After every dispatch and every gate intake, the features merged on master's
gate commit give exactly master's tree.

## Commands

All of them work on a local clone (`--repo DIR`) and change nothing unless
given `--write`; `--push REMOTE` then pushes what they wrote.

| Command | Does |
| --- | --- |
| `dispatch.py dry-run --head PR-MERGE` | For a pull request: where each part of it would go, which placements need a `Feature:` trailer, and whether the features would give its tree |
| `dispatch.py land` | Dispatches every master commit since the last dispatch record or gate intake; with `--write`, the features fast-forward and master gains a verified dispatch record |
| `intake.py --to GATE-COMMIT` | Gate intake; on trouble, bisects to the first bad gate commit, takes gate in up to the one before it, and leaves the stuck features on `intake/<gate-commit>/features/<name>` |
| `release.py cut --name NAME` | Branches a release from the features integrated on their gate commit, checked equal to master |
| `release.py check --release REF` | Merges a release into master for real; names any release commit master lacks |
| `release.py audit ...` | Rebuilds a past release from gate, backports and features |
| `replay.py --from A --to B` | Runs gate intake and dispatch over past master history with master as the answer key; `--divergence DIR` writes where the tools differed from master |
| `metadata.py check` | Checks the features' metadata against the feature branches: missing or stray files, unknown dependencies, cycles |
| `metadata.py order` | Lists the features in merge order |

Escalations (a stuck feature, a commit dispatch cannot place) are written as
issue files under `--report DIR`, and opened on GitHub only with
`--open-issues OWNER/REPO`.

## Feature metadata

Each feature has a file `features/<name>` on `meta/state`, of `Key: value`
lines (a line starting with a space continues the value):

    Feature: lx
    Description: The lx brand: Linux binary compatibility in a zone.
    Owner: @TritonDataCenter/triton-engineering
    Depends: brand-ops, brand-process, hyprlofs
    Upstream: keep
    Upstream-Tickets:
    Tests:

- `Depends` sets the merge order: every command takes `--state REF`
  (default `refs/heads/meta/state`) and merges features after the ones
  they depend on, by name otherwise. Without the ref, it is by name.
- `Upstream` is the intent: `keep`, `upstream` (offered to illumos, or
  carried until gate has it) or `landed`.
- Gate intake reports each of the `Upstream-Tickets` it takes in, and
  whether the feature retired. With `--write` it marks retired features
  `Upstream: landed` and records the gate commit as `Retired`.
- Dispatch writes a stub for a feature a commit starts, for a person to
  complete; its Owner is the team (`metadata.OWNER`) until someone else
  takes it.

## Placement decisions

Where routing cannot tell which feature a change belongs to (a file no
feature touches, a new file), a person decides:

- in a pull request, with a trailer in the squash message:
  `Feature: NAME` for everything unplaced, or `Feature: NAME PATH` for one
  path. A name that is not a feature yet starts a new one on gate.
- for a commit already on master, in a decisions file passed with
  `--decisions` (or `--decide` to `replay.py`): `commit:SHA FEATURE` for
  whatever the rules cannot place in that one commit, as a trailer it
  lacked would have said, or `PATH FEATURE` for a path whenever the rules
  cannot place it.

## Modules

| File | Holds |
| --- | --- |
| `ft.py` | Git plumbing, `rebase`, `integrate`, `route`, trailers |
| `resolve.py` | Conflict resolvers: copyright lines, Makefile list entries |
| `manifest.py` | The top-level `manifest` sync with gate's package manifests |
| `intake.py` | Gate intake |
| `dispatch.py` | Dispatch, dry run, dispatch records |
| `release.py` | Release cut, check and audit |
| `escalate.py` | Issues for a person |
| `metadata.py` | Feature metadata on `meta/state` |
| `replay.py` | Replay and shadow mode |

## Tests

Each module has a `test_*.py`, run against small throwaway repositories:

    for t in test_*.py; do python3 $t; done

They need only Python 3.9 or later and git 2.43 or later (for
`merge-file --object-id` and `merge-tree --write-tree`).
