# illumos-joyent feature-branch workflow

This is a living design document for phase 2: maintaining the illumos-joyent
delta as feature branches on illumos-gate. It lives on the `meta/restructure`
branch. Decisions it reaches land as real tools and docs on `features/tooling`.
Its history is in git; it was first drafted on 2026-10-21.

## Context and goals

We want illumos-joyent maintained as a set of named features, each a branch on
illumos-gate, with tooling that keeps them current as gate moves. Today the
delta lives as merge history on illumos-joyent `master`. That makes it hard to
see, hard to upstream, and hard to rebase.

The restructure work (phase 1) showed the delta can be split this way. It
produced 78 `features/*` branches on gate commit 479a4a914dc. Their octopus
merge reproduces master da512a7e2e6 byte for byte. 42 build alone. All 32
dependency stacks build. For now we treat that feature list as correct, but
nothing in phase 2 should lock us into it.

Phase 2 goals:

- Track every feature we apply, with its description, owner, dependencies, and
  upstream status.
- Rebase all features onto new gate commits automatically, escalating to a
  human only when tooling cannot resolve a conflict, and making that
  escalation visible.
- Let developers build and test new features and fixes to existing ones, alone
  or with their dependencies.
- Notice when a feature, or part of one, lands upstream.
- Support new features that have no history yet, such as a driver imported
  from FreeBSD before gate ships one.
- Keep the tooling itself as a feature branch on gate inside the fork,
  experimenting first on `nshalman/illumos-joyent`.

The reference tree ("octopus merge equals master") was a phase 1 acceptance
check. It goes away once development moves to features, though it stays
useful while the new tooling runs beside master-based development, and it is
the answer key for replaying history (below).

## Features as the unit

A feature is a branch `features/<name>` based on a gate commit, plus a
metadata entry. The branch holds the code. The entry holds what the code
cannot say.

Proposed metadata per feature:

| Field | Purpose |
| --- | --- |
| name | Branch name and identity |
| description | What it does and why SmartOS needs it; feeds the README list of differences |
| owner | Who gets escalations |
| depends | Features it needs in order to build or work |
| upstream | illumos tickets or gate commits it corresponds to, and intent: upstream, keep, or retire |
| tests | How to test it beyond a build, if anything |
| resolvers | Mechanical conflict resolvers that apply to its files |

### Two kinds of dependency

Phase 1 split the delta so every branch applies to gate on its own: textual
independence. Most do not build alone: 36 of 78 need other features. That is
semantic dependency. We should keep both properties distinct:

- Textual independence means a rebase conflict stays inside one feature, and
  features rebase in any order.
- Semantic dependency only decides what gets built and tested together, and
  the order features are listed in.

A feature could instead be based on the features it depends on (stacked
branches). That makes each branch build alone, but every rebase of a lower
feature forces a rebase of everything above it, and a DAG of stacks is much
harder to keep than a chain. I recommend all features on gate, with
dependencies in metadata.

The dependency graph must have no cycles. Two pairs still need each other
today, boot/dboot and datalink/vnd. They should be merged or always tested
together.

### Lifecycle and lock-in

The feature list will change. The tooling should make these operations
ordinary commands that rewrite branches and metadata together:

- create (from gate, with metadata)
- split (move commits or hunks to a new feature)
- merge (fold one feature into another)
- rename
- retire (dropped, or landed upstream)

The phase 1 analysis scripts (hunks.py and friends) are a one-time bootstrap.
The ongoing tooling should not depend on them.

### Commits inside a feature

Today each feature branch is one commit. Over time, a feature should be a
short, curated series of commits, like a patch queue. Fixes land as `fixup!`
commits and get squashed at the next sync, so the series stays reviewable.
`git range-diff` shows reviewers how a series changed.

## Where the tooling and its state live

The tooling is a feature like any other, `features/tooling`, rebased onto gate
with the rest. State that changes on every sync should not live there,
because rebasing that history is pointless churn.

| What | Where | Why |
| --- | --- | --- |
| Tool code | `features/tooling` | Versioned with the tree; appears in every integrated build |
| Docs: README-SmartOS.md and workflow docs | `features/tooling` | Belongs in the tree readers clone |
| Feature list and dependency graph | `features/tooling` | Changes rarely; reviewed like code |
| Shared rerere cache | `meta/state` | Grows every sync |
| Last synced gate commit, per-feature tags | `meta/state` and tags | Changes every sync |
| Sync reports and conflict log | `meta/state` | History of what happened |
| This design document and the phase 1 analysis | `meta/restructure` | Working material; may be abandoned once phase 2 settles |

On `nshalman/illumos-joyent`:

- `features/*`: the 78 phase 1 features, on gate 479a4a914dc.
- `features/tooling`: on the same gate commit. It starts with Dan McDonald's
  two README-SmartOS.md commits from PR #547, cherry-picked unchanged (OS-8751,
  then "Last batch, I think."). They stay as-is through every rebase; the
  tooling builds on top of them, in a top-level `feature-tools/` directory:
  `ft.py` (rebase, integrate, route) and `replay.py`, each with tests.
- `meta/state`: orphan; a bootstrap commit recording the gate commit, the
  reference master commit, and each feature's tip, and a `replay/`
  directory with the record of each replay.
- `meta/restructure`: orphan; the history of the illumos-joyent-restructure
  repo, including this file.

The orphan branches follow git.git's own maintainer workflow, where the
tooling lives in a separate `todo` branch beside the topic branches. TopGit
put dependency metadata inside each feature branch. That puts metadata files
in every branch, which then need special handling to stay out of the merged
tree. I would avoid it.

Open point: the tooling must run before the integrated tree exists, so the
sync job checks out `features/tooling` on its own and runs from there.

### Dan's README

Dan's README-SmartOS.md has two parts. The framing prose (SmartOS design
choices, ramdisk root, boot modes) stays handwritten. Its "List of substantive
differences" is in effect a hand-written list of features, so it should be
generated from feature descriptions, or at least checked against the feature
list. Otherwise the doc and the feature set drift apart. Because his commits
stay unchanged on `features/tooling`, that generation or check lands as a
later commit on top.

## Syncing with illumos-gate

A sync moves every feature from the old gate base to a new one, then
integrates, builds and reports. Because features are textually independent,
each rebases alone, and a conflict in one does not block the others. A
feature that reaches the last tier of the escalation ladder is held back from
integration while the rest proceed.

### Steps

1. Fetch gate and pick the target commit.
2. Check for upstream absorption (next section) before rebasing, so expected
   conflicts are labelled.
3. Rebase each feature onto the target, climbing the escalation ladder until
   it succeeds or reaches a human.
4. Merge all features that rebased into an integration branch. A merge
   conflict here means two features overlap in text. The known case is
   copyright lines, which several features carry identically until their
   rebases resolve them differently. Anything else is reported as a bug in
   the split.
5. Build the integration. If it fails, bisect along the merge chain to the
   feature responsible.
6. Publish the delta report and the per-feature range-diffs.

### Escalation ladder

Each feature records which tier resolved it, so we learn where the effort
goes.

1. Plain `git rebase`.
2. rerere, using the shared cache from the state branch.
3. Mechanical resolvers for conflicts we already know are mechanical:
    - copyright blocks, which phase 1 copied into every feature that touches a
      file;
    - the top-level `manifest` against `usr/src/pkg/manifests`, already a
      manual chore at every gate merge per Dan's doc;
    - `exception_lists`;
    - Makefile list entries such as `SUBDIRS`.
4. Optional: an AI-proposed resolution, published as a PR with its reasoning.
   It never lands without a green build and a human approval.
5. A human. The tool opens an issue or PR on the fork naming the feature, its
   owner, the conflict, and the gate commit that caused it.

### Finding the gate commit that caused a conflict

"lx conflicts with 18374 viona" tells you whom to ask. "lx failed to rebase"
does not. When a rebase conflicts, the tool bisects the new gate commits for
the first one the feature conflicts with, as git-imerge does. Rebasing onto
that commit's parent first also shrinks the conflict to one upstream change.

### The delta report

The reference tree goes away, so a sync needs a different check. The useful
one is how our delta changed: compare `diff(old gate, old integration)` with
`diff(new gate, new integration)`. If only gate moved, the changed lines
match, though diff context and line numbers shift. Whatever differs is what
the sync did to our code, and that is what a reviewer reads.

### Conflict hotspots

Some files are touched by many features: the top-level `manifest`, shared
Makefiles, copyright headers. I have not measured this yet; phase 1's
`data/hunks.json` can. Some hotspots may be worth restructuring, for example
per-feature manifest fragments, which would remove more conflict work than any
resolver. That changes the joyent delta itself, so it is a separate decision.

## Detecting features landing upstream

Without detection, upstreaming shows up as confusing conflicts or empty
commits during a rebase. Three signals, cheapest first:

1. **Ticket match.** illumos commit subjects start with ticket numbers. A
   feature's `upstream` field lists the illumos tickets it corresponds to.
   Each sync scans the new gate commits and flags a feature whose ticket
   landed.
2. **Patch match.** `git patch-id` finds gate commits identical to one of our
   commits, the case where we upstreamed the patch as is. `git cherry` does
   this per branch.
3. **Shrinkage.** After a rebase, compare each feature's diff size with the
   previous sync's. A feature that shrank sharply, or a commit that became
   empty, probably met an equivalent upstream change, even one with a
   different ticket or rewritten code.

A flagged feature gets a report, not an automatic drop: the upstream version
may differ from ours, and someone has to decide whether to retire the feature,
shrink it to the remaining difference, or keep it.

The same scan can watch for gate commits that touch files a feature touches,
as an early warning before the conflict happens.

Open point: features whose changes came from a joyent ticket (OS-xxxx) rather
than an illumos one have no illumos ticket to watch. When we upstream one, its
metadata should gain the illumos ticket number then.

## Publishing and release branches

Not decided. Today release branches fork from illumos-joyent `master`. One
direction is to fork them from a gate commit and apply all features. That is a
suggestion, and the options below are for discussion.

### What any option must provide

- A release is reproducible from a short record: one gate commit plus one
  commit per feature.
- A fix to a feature can reach an existing release branch without pulling in a
  new gate.
- Feature history stays reachable even though feature branches are rebased.
  Tagging each feature at each sync, such as `features/lx@<sync-id>`, covers
  this.
- Consumers that pull illumos-joyent, smartos-live first, keep working or get
  a clear migration. I have not checked how smartos-live picks its
  illumos-joyent branch; that needs a look.

### Options

| Option | master | Release branch | Cost |
| --- | --- | --- | --- |
| A. master fed by integration | Kept, forward-only: each sync adds a commit whose tree equals the integration and whose parents are old master and the new integration | Forked from master, as today | Least change downstream; master history becomes a series of sync points |
| B. Releases built from gate plus features | Optional, or a regenerated integration branch | Gate commit, then a merge of each feature at its tagged version | Cleanest record of what a release is; release fixes need a defined path (below) |
| C. Both during transition | Kept as today; integration built beside it and compared | From master until we trust B | Two systems to run for a while |

### Fixes to a release under option B

Two shapes seem workable:

- The fix lands on the feature branch, and the release branch merges or
  cherry-picks that commit. Simple, but the release then diverges from any
  recorded feature version.
- The release keeps frozen copies of its feature branches,
  `release/<id>/features/<name>`. The fix lands there and the release
  integration is rebuilt. Exact, but it doubles the branches to keep.

Some release fixes are gate commits backported ahead of the release's gate
base, as release-20260430 and release-20260514 show (see Replaying history).
Those belong to no feature. The release records them as part of its gate side,
and they need no routing back: the next sync onto a gate that includes them
absorbs them.

Either way, bug fixes do get applied to release branches from time to time and
the release is recut, so this path has to be routine, not an exception. The
routing in the developer workflow carries each release fix back to its
feature branches.

### Octopus or sequential merges

An octopus merge records all features in one commit, which reads nicely, but
git refuses an octopus merge with any conflict and cannot record a resolution.
A chain of two-parent merges in dependency order can hold resolutions, such as
the copyright lines above, and lets each step be built. For integration I lean
toward the chain.

## Builds and CI

Not decided, and likely the larger change. Today one tree, master, gets built.

### What phase 1 already proved

The phase 1 compile checks on nshalman-builds used one trick worth keeping:
build gate once, snapshot the workspace with ZFS (`fb@gate-built`), then for
each feature or stack roll back and run an incremental build with only that
merge applied. Each experiment builds into its own proto area, because
master's proto would hide missing headers. `buildcheck.sh` and `stackplan.py`
already compute stacks from dependencies.

### Build tiers

Building every feature closure all the time is overkill. Phase 1's
per-feature builds were a one-time check that the split was sound. Day to day,
the default is one integration build, and the per-feature machinery is a tool
for narrowing a failure.

| When | What gets built | Purpose |
| --- | --- | --- |
| Pull request to a feature | The integration with that change | Feedback for the author |
| Every sync | The integration on the new gate | Catch gate changes that break us |
| A build fails | Bisect: rebuild with subsets of features, or along the merge chain, until one feature is to blame | Point at the feature and owner |
| Release | Clean DEBUG and non-DEBUG builds, a platform image, and a boot test | What we ship |
| On demand | A feature with its dependency closure | Check a split, a new feature, or a dependency claim |

With a chain of two-parent merges, bisecting a failure is ordinary: each merge
in the chain is a buildable tree. The dependency graph decides the chain's
order, so a feature never lands before what it needs.

### Where builds run

The rebase and conflict work needs only git, so it can run on any Linux CI.
Compiling needs an illumos host. Candidates:

- nshalman-builds, for now.
- Triton's existing Jenkins for smartos-live builds.
- A self-hosted GitHub Actions runner on illumos. I do not know how well that
  works; it needs checking.
- Oxide's buildomat, which builds illumos; I do not know what adopting it
  would take.

### Tests beyond compiling

A build shows a feature compiles, not that it works. Today's test environment
is a VM running inside the nshalman-builds zone, which boots a platform image
built from the integration. Per-feature `tests` metadata can name which test
suites exercise a feature. Phase 1 found `smartos-test` and `zfs-tests` cannot
be stacked meaningfully on their own, so they run against the whole
integration.

## Developer workflow

A developer should be able to change one feature, build it with what it needs,
and get it reviewed, without knowing the whole feature graph. Three ways to
work, and I think we need all of them.

### Work on the feature branch

For a change that clearly belongs to one feature:

1. Check out `features/<name>` in a worktree. It sits on the current gate
   base.
2. Edit and commit there. Fixes to existing commits go in as `fixup!` commits.
3. Run the tool's build command. It merges the feature's dependency closure
   into a separate build worktree and runs an incremental build, the way phase
   1's stacks did.
4. Open a PR against `features/<name>`. CI runs the pull-request tier.

The catch: the developer edits in a tree that does not build on its own.
Editors, cscope and test runs work best in the build worktree, not the edit
tree.

### Work in the integrated tree

Most SmartOS developers today work in a full tree under smartos-live. That
should keep working:

1. Work in an integration checkout, which builds and boots as a whole.
2. Commit as usual.
3. The tool routes each commit to the feature that owns the lines it changes,
   as `git absorb` does for fixups. Phase 1's hunk ownership logic is that
   same problem. A commit touching two features is split, and the tool asks
   when ownership is unclear, such as lines added to gate code no feature
   touches.
4. The routed commits become PRs against the feature branches.

### Work against a release tree

A bug is often found in a release, and the fix is wanted there first. The
developer works on the release branch, which is a full tree like the
integrated one. The fix lands on the release, the release is recut, and the
same routing step applies each commit to the feature branches that own its
lines. The feature branches may sit on a newer gate than the release, so
applying there is a cherry-pick that can conflict; it climbs the same
escalation ladder as a sync.

### New features

The tool creates `features/<name>` from the current gate base along with its
metadata entry: description, owner, `depends`, and `upstream`. Examples are a
FreeBSD driver import, or a fix we carry until gate takes it. From then on it
is synced, built and reported like any other feature.

### Testing beyond a build

A developer needs a platform image to boot. The tool should hand smartos-live
an integration tree: gate plus all features, with the developer's branch in
place of the published one. How smartos-live gets pointed at that tree is part
of the publishing question.

## Transition: running beside master

We start in shadow mode while master-based development continues. During that
time the reference tree stays useful: the integration should keep matching
master.

Shadow mode, per master update:

1. Take master's new commits since the last shadow run.
2. Route each one to its feature, the same routing as the integrated-tree
   workflow above.
3. If master merged a new gate, run a sync onto that gate commit.
4. Check that the integration's tree equals master's. A difference means the
   routing or the sync went wrong, and it is reported.

This tests routing and sync on real work, with master as the answer key. Once
it runs clean for a while, the direction can flip: features become the source
and master, if it remains, is derived from them.

Before shadow mode runs live, we replay history (next section). Replay is
shadow mode run over the past, so the same tools serve both.

## Replaying history

Replay asks: had these tools existed six months ago, would they have
reproduced every master commit and every release branch since? Each commit
is a one-to-one test, because master's tree at that commit is the answer.

### What history offers (measured 2026-10-21)

- Release branches fork from master every two weeks. Of the eleven releases
  from release-20260430 to release-20261009, nine are just a master commit;
  two carry commits of their own:
    - release-20260430 carries gate's revert of 17903 ("loader: expose
      addresses of firmware tables in loader env"), which broke boot on some
      SMBIOS implementations. Gate made the revert (7249bc1087a) the same
      day; the release cherry-picked it, with the same patch-id.
    - release-20260514 carries a backport of gate's 18118 (SCTP,
      08292a06bdf) and OS-8741 ("Pull in OmniOS inotify enhancement"), the
      same patch as master's ec67518b999.
- So release fixes come in two kinds: a gate commit backported ahead of the
  release's gate base, and a joyent change that master also gets. The design
  above covers only the second. Under option B, a release is a gate commit,
  plus any gate commits backported onto it, plus the features.
- Starting at release-20260416's branch point (06ea1eb6c40, 2026-04-15), there
  are 73 first-parent master commits up to our reference da512a7e2e6. 60 of
  them are gate merges; the other 13 are joyent changes, committed directly
  on master. Master took 3 to 12 gate merges between consecutive releases.
- Master has moved 21 commits past da512a7e2e6 since phase 1. Those are the
  first input for live shadow mode.
- Phase 1's `collect.sh` takes `JOYENT=<commit>` and derives the gate base
  from that commit's last gate merge, so the analysis can be rerun at an
  earlier point.

That window exercises dozens of syncs, ordinary joyent changes, a release fix
also carried on master, and two gate backports onto releases. It does not
obviously contain a feature landing upstream; whether any joyent change in
the window later reached gate is worth checking before relying on replay to
test upstream detection.

### Method

1. **Bootstrap.** Rerun the phase 1 analysis at 06ea1eb6c40, producing
   features on that commit's gate base. Check that their integration equals
   06ea1eb6c40. Phase 1's overrides match on file and pattern, so some may
   not apply to the older tree; how many need adjusting is itself a measure of
   how robust the split is.
2. **Walk master's first-parent history** to da512a7e2e6, one commit at a
   time:
    - a gate merge becomes a sync onto its second parent, climbing the
      escalation ladder;
    - a joyent commit is routed to the features that own its lines;
    - after each step, the integration's tree must equal that master commit's
      tree.
3. **Use master as the human.** When a sync reaches the human tier, or
   routing is ambiguous, take the resolution from master's actual commit so
   the replay can continue, and record that a person would have been needed.
   The count of those, per tier, is the main result. Phase 1-style placement
   decisions that routing cannot make go in the same log.
4. **Rebuild each release.** At each release branch point, build the release
   from the gate commit plus the features as they stand, and compare its tree
   with the release branch's fork. For release-20260430 and release-20260514,
   apply their own commits as release fixes, recut, and check the tip's tree.
   The OS-8741 fix routes back to its feature. The two gate backports belong
   to no feature: they become part of the release's gate side, and they
   disappear from it once a later sync reaches a gate that includes them.
5. **Compare the ends.** The replayed features at da512a7e2e6 and the 78 from
   phase 1 describe the same tree. Where their split differs, the difference
   shows how much the split depends on where the analysis starts.

Tree equality at every step means replay needs no builds: master was built and
shipped at each of those commits. Builds come in only where a step departs
from master, such as a resolver choosing a different but plausible
resolution.

### What replay needs from the tooling

These land on `features/tooling`, and replay is their first test:

1. The feature list and metadata format.
2. `integrate`: the merge chain, and a tree comparison against a reference.
3. `sync`: rebase every feature onto a gate commit through tiers 1 to 3,
   recording the tier for each feature.
4. `route`: assign a commit's hunks to features by line ownership, splitting
   where needed and reporting what it cannot place.
5. `replay`: the driver for this section, which then stays as a regression
   test for the other tools.

Results go to `meta/state` under a replay directory, kept apart from live sync
state.

### First run: release-20260903 to da512a7e2e6 (2026-10-21)

Done, with `feature-tools/replay.py` on `features/tooling` (133822d2ddb).
The full record is `replay/2026-10-21-small/` on `meta/state`.

- Phase 1 rerun at feb8a55d8d3 produced the same 78 feature names with no
  override changes, and their merge equals that commit.
- All 15 master commits (13 gate merges, 2 joyent commits) were reproduced
  tree for tree, including release-20261009's branch point.
- The replayed features at da512a7e2e6 have the same trees as phase 1's
  split computed there directly, for all 78. The split is stable across the
  window, and routing keeps it so.
- Both joyent commits were routed with no help.
- The gate merges held eight pieces of work beyond a plain rebase. Seven are
  mechanical: three copyright-line conflicts, one Makefile list conflict
  (`aio_cancel` in the libc-tests `PROGS`), and three top-level `manifest`
  updates that follow gate's pkg manifests and raise no conflict at all.
  The eighth was real judgment: master adapted `smartos-test.sh` to gate's
  new way of running header tests (18295), again with no conflict.

What this changes:

- The mechanical tier earns its place: copyright, Makefile list and
  manifest resolvers would have covered seven of eight cases. They are the
  next tools to build, and replay can measure them, since a resolver must
  reproduce master's choice.
- Changes that raise no conflict still need people (smartos-test) or
  resolvers (manifest). Sync cannot stop at "rebase was clean"; the manifest
  check and the tests are part of it.

Next: build the resolvers, rerun this window to confirm they reproduce
master's choices, then widen the window back to release-20260416.

## Open questions

- [ ] Publishing: option A, B or C, and what happens to `master` in the end?
- [ ] Releases: fork from master or from gate plus features? Which shape for
      release fixes and recuts?
- [ ] How does smartos-live choose its illumos-joyent branch, and what must
      change there?
- [ ] Build infrastructure: nshalman-builds for now; what after the
      experiment?
- [ ] Test infrastructure: a VM in the nshalman-builds zone for now; what per
      release, and after the experiment?
- [ ] Should AI-proposed conflict resolutions exist at all, and is "proposes,
      never lands alone" the right limit?
- [ ] Sync cadence: every gate push, or batched? Bisecting conflicts makes
      larger batches affordable.
- [ ] Where escalations go: issues or PRs on the fork, or somewhere else?
- [ ] boot/dboot and datalink/vnd: merge each pair, or test them together?
- [ ] Conflict hotspots: measure them, then decide whether to restructure any,
      such as the top-level `manifest`.
- [ ] Ownership: who owns each of the 78 features?
- [x] Replay: start small (release-20260903), then widen to
      release-20260416. The small run is done.
