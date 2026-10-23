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

## The process at a glance

Agreed 2026-10-23; the sections below give the detail.

- **Developers keep landing on `master`.** A pull request is squash-merged
  after a person approves it, exactly as today.
- **Dispatch keeps the features in step with master.** After each commit
  lands, CI routes its pieces to the feature branches it touches, integrates
  the features, and checks the result equals master. On success it pushes the
  features and records the dispatch on master. Before the merge, the same
  dispatch runs as a dry run on the pull request, so placement problems show
  up in review.
- **Gate intake takes in illumos-gate.** At a gate commit we choose, every
  feature is rebased onto it and all are merged; once checked and built, that
  integration becomes master's gate-merge commit. Conflicts the tools cannot
  resolve are escalated per feature, to the feature's owner.
- **Releases are cut at a gate intake.** A release branch is the gate commit
  plus the merge of all features; its tree equals master's at that moment.
  Later fixes land on master first and are cherry-picked to the release.

The invariant behind all of it: after every dispatch and every gate intake,
the features, merged on master's gate commit, give exactly master's tree.

## Glossary

| Term | Meaning |
| --- | --- |
| gate | illumos-gate, our upstream |
| feature | a branch on a gate commit holding one coherent part of our delta (`features/<name>`), plus its metadata |
| integration | the chain of merges of every feature onto one gate commit, and its tree |
| gate intake | taking in a new gate commit: rebase every feature onto it, integrate, check and build, and write master's gate-merge commit |
| dispatch | after a commit lands on master, routing its pieces into the features and checking the integration equals master |
| dry-run dispatch | the same, run in CI on a pull request before it merges, writing nothing |
| routing | deciding which features own each piece of a change |
| decision | a person's placement choice where routing cannot decide: a `Feature:` trailer in the commit message, or an entry in the decisions file |
| resolver | a mechanical conflict fixer, such as for copyright lines or Makefile lists |
| manifest sync | bringing the top-level `manifest` in line with gate's package manifests at each gate intake |
| escalation | handing a stuck gate intake or dispatch to a person, as an issue on the fork |
| retire | dropping a feature that gate has absorbed completely |
| release cut | a release branch made at a gate intake: the gate commit plus the merge of every feature |
| replay | running gate intake and dispatch over past master history, with master as the answer key |
| shadow mode | replay run on master's new commits as they arrive |

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
commits and get squashed at the next gate intake, so the series stays
reviewable.
`git range-diff` shows reviewers how a series changed.

## Where the tooling and its state live

The tooling is a feature like any other, `features/tooling`, rebased onto gate
with the rest. State that changes on every gate intake should not live there,
because rebasing that history is pointless churn.

| What | Where | Why |
| --- | --- | --- |
| Tool code | `features/tooling` | Versioned with the tree; appears in every integrated build |
| Docs: README-SmartOS.md and workflow docs | `features/tooling` | Belongs in the tree readers clone |
| Feature list and dependency graph | `features/tooling` | Changes rarely; reviewed like code |
| Shared rerere cache | `meta/state` | Grows every gate intake |
| Last gate commit taken in, each feature's tip per intake | `meta/state` | Changes every gate intake |
| Intake and dispatch reports, conflict log, decisions file | `meta/state` | History of what happened |
| This design document and the phase 1 analysis | `meta/restructure` | Working material; may be abandoned once phase 2 settles |

On `nshalman/illumos-joyent`:

- `features/*`: the 78 phase 1 features, on gate 479a4a914dc.
- `features/tooling`: on the same gate commit. It starts with Dan McDonald's
  two README-SmartOS.md commits from PR #547, cherry-picked unchanged (OS-8751,
  then "Last batch, I think."). They stay as-is through every rebase; the
  tooling builds on top of them, in a top-level `feature-tools/` directory:
  `ft.py` (rebase, integrate, route), `resolve.py` (conflict resolvers),
  `manifest.py` (manifest sync), `replay.py` and `release.py` (rebuild a
  release from gate, backports and features), each with tests.
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
gate intake job checks out `features/tooling` on its own and runs from there.

### Dan's README

Dan's README-SmartOS.md has two parts. The framing prose (SmartOS design
choices, ramdisk root, boot modes) stays handwritten. Its "List of substantive
differences" is in effect a hand-written list of features, so it should be
generated from feature descriptions, or at least checked against the feature
list. Otherwise the doc and the feature set drift apart. Because his commits
stay unchanged on `features/tooling`, that generation or check lands as a
later commit on top.

## Gate intake

Gate intake takes in a new illumos-gate commit. The goal is that it runs on its
own and escalates only what the tools cannot resolve. Because features are
textually independent, each rebases alone, and a conflict in one does not stop
the others.

### Steps

1. Fetch gate and pick the target commit. Not every gate commit: intake runs at
   points we choose, about as often as master takes gate today (a few times a
   week), or daily.
2. Wait until dispatch has caught up with master, and hold further merges
   (one lock, such as GitHub's merge queue, covers both). Intake rebuilds
   master's tree from the features, so a change on master not yet in the
   features would be lost.
3. Check for upstream absorption (see Detecting features landing upstream), so
   expected conflicts are labelled.
4. Rebase each feature onto the target, through the escalation ladder; run
   the manifest sync on the feature that carries the manifest.
5. Integrate: merge all features, in a chain, onto the target.
6. Build the integration, and run the tests. A clean rebase is not enough: the
   replays found changes that raise no conflict yet still need a person, such
   as smartos-test after gate's 18295.
7. Write master's gate-merge commit: parents master and the gate commit, tree
   the checked integration, written explicitly (`git commit-tree`) and
   asserted equal. Force-push the rebased features, and record each feature's
   new tip on `meta/state`.
8. Publish the delta report and the per-feature range-diffs.

### When intake cannot finish

A conflict the tools cannot resolve, a build failure, or a test failure:

1. Find the first gate commit responsible by bisecting the new gate commits
   (next sections).
2. Take gate in up to the commit before it, so master keeps moving and the
   problem is one gate commit wide (recommended; see Open questions).
3. Publish the half-done feature on a candidate branch,
   `intake/<gate-commit>/features/<name>`, and open an issue on the fork naming
   the feature, its owner, the conflict, and the gate commit.
4. A person fixes the candidate branch; the next intake run picks it up,
   re-checks it, and continues.

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

Beside the tree check against master, a reviewer needs to see what changed.
The useful one is how our delta changed: compare `diff(old gate, old
integration)` with `diff(new gate, new integration)`. If only gate moved, the
changed lines match, though diff context and line numbers shift. Whatever
differs is what the gate intake did to our code, and that is what a reviewer
reads.

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
   Each gate intake scans the new gate commits and flags a feature whose
   ticket landed.
2. **Patch match.** `git patch-id` finds gate commits identical to one of our
   commits, the case where we upstreamed the patch as is. `git cherry` does
   this per branch.
3. **Shrinkage.** After a rebase, compare each feature's diff size with the
   previous gate intake's. A feature that shrank sharply, or a commit that
   became empty, probably met an equivalent upstream change, even one with a
   different ticket or rewritten code.

A flagged feature gets a report, not an automatic drop: the upstream version
may differ from ours, and someone has to decide whether to retire the feature,
shrink it to the remaining difference, or keep it.  The exception is a feature
left with no changes at all after a rebase: gate has all of it, and it retires.

Seen on real history (replay, 2026-10-22): Dan committed 18158 on master
before gate landed the identical patch, and OS-8746 fixed gate's test runfiles
before gate took them as 18163.  Each became a short-lived feature, by a
person's decision, and retired at the gate merge that landed it; one OS-8746
commit routed into zfs-tests emptied the same way.  A fix we carry until gate
takes it is just a feature with an expected end.

The same scan can watch for gate commits that touch files a feature touches,
as an early warning before the conflict happens.

Open point: features whose changes came from a joyent ticket (OS-xxxx) rather
than an illumos one have no illumos ticket to watch. When we upstream one, its
metadata should gain the illumos ticket number then.

## Master, releases and history

Agreed 2026-10-23. Developers keep landing on `master`; the feature branches
follow master through dispatch; master's gate merges are written by gate
intake; releases are cut from gate plus features.

### Master

Master stays the branch developers clone, branch from and build, and it is
never rewritten. It gains three kinds of commit:

- squash-merged pull requests, as today;
- dispatch records: after a commit is dispatched, a merge into master of the
  integration that dispatch verified (see Dispatch records, below);
- gate-merge commits written by gate intake, whose tree is the checked
  integration.

The feature branches are rebased at each gate intake and force-pushed then;
dispatch only adds commits to them. Each feature's tip at each gate intake is
recorded on `meta/state`, so every past state stays reachable and
`git range-diff` can show what an intake did to a feature.

### Dispatch records

A dispatch record must never hide a mismatch, so nothing about it is taken on
trust:

1. Before writing it, dispatch requires the integration's tree to equal the
   tree of the master commit it dispatched (`git diff --quiet <commit>
   <integration>`). If not, nothing is written or pushed, and it becomes an
   issue.
2. The merge queue holds the next pull request until the record is written,
   so the record sits directly on the dispatched commit and both its parents
   have the same tree. It is then a plain merge, and dispatch checks that the
   merge's tree equals each parent's before pushing.
3. If master has moved anyway, say by a direct push, the record goes on top of
   master keeping master's tree (`-s ours`), names the dispatched commit in its
   message, and is written only after check 1 passed for that commit. A
   record's second parent is always an integration verified against the
   commit it names.

### Release cuts

A release is cut at a gate intake: the release branch is the integration
commit itself, the gate commit plus the chain of feature merges. Its history
says exactly which gate commit and which feature versions it holds, and its
tree equals master's at that moment. Merging it into master is then trivial
(identical trees always merge to that tree), and that is checked rather than
assumed: the merge's tree must equal master's, or the cut is wrong. Cutting from a gate commit newer than master's means running
gate intake first.

### Fixes to a release

By the time a release needs a fix, the features have moved on to newer gate
commits, so a release is not rebuilt from them; it is an ordinary whole-tree
branch from the cut onwards, and a recut is a new tag on it.

- **Fix master first (the default).** The fix lands on master and is
  dispatched to its features as usual; the original squash commit is then
  cherry-picked onto the release with `-x`.
- **Fix the release first (urgent).** The fix must also land on master. The
  check: merging the release into master must leave master's tree unchanged.
  A change means a release fix never reached master, or a gate backport has
  not reached gate yet; `release.py` tells the two apart by patch-id.
- **Gate backports** are cherry-picked from gate onto the release, as now
  (release-20260430 took gate's 17903 revert; release-20260514 took 18118).
  They belong to no feature and need no routing back.

`release.py` checks that a release equals its cut plus its backports and
fixes, as the replay did for the two 2026 releases with commits of their own.

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
| Pull request | Dry-run dispatch, then the integration with the change | Feedback for the author and reviewer |
| Every gate intake | The integration on the new gate, and the tests | Catch gate changes that break us before master moves |
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

A developer works in master, a whole tree, and lands whole commits; dispatch
decides which features a commit touches, and asks only when it cannot. Nobody
needs to know the feature graph to fix a bug.

### From idea to landed commit

1. **Get a tree.** Branch from master. It builds and boots in smartos-live as
   it does today.
2. **Make the change.** Edit, build and test as usual; the pull request becomes
   one commit when squash-merged, with a ticket in its message.
3. **Dry-run dispatch on the pull request.** CI routes the pull request's
   merge result onto the features, integrates them, and compares the result
   with what master would become, writing nothing. It posts where each part
   goes ("lx: 2 files, brand-ops: 1 hunk"), so placement is reviewed with the
   code. Three outcomes:
    - clear: nothing to do;
    - ambiguous (a gate file no feature touches, or a new file): the author
      names the feature with a trailer in the squash message,
      `Feature: brand-ops`. A trailer naming a feature that does not exist
      starts it on gate, as `Feature: upstream-18158` would for a fix carried
      until gate lands it;
    - several features: fine; dispatch splits the commit, and each part keeps
      the author and message, plus a trailer naming the original commit.
4. **Review and merge.** A person approves; the pull request is
   squash-merged to master.
5. **Dispatch.** CI takes master's new commits in order, one at a time:
   routes the commit onto the features as the previous dispatch left them,
   integrates, and checks the tree equals master's. On success it pushes the
   features (a fast-forward: dispatch only adds commits) and adds the
   dispatch record to master, checked as described in Dispatch records.

Dispatch failing after the merge (an unforeseen ambiguity, or a tree that does
not match) leaves the commit on master and the features behind. CI opens an
issue; the decision, which can no longer go in the commit, goes in the
decisions file on `meta/state`; dispatch reruns. Later commits queue behind
it, and gate intake waits. The dry run is what keeps this rare.

### Cost of the dry run

Measured 2026-10-22 on nshalman-builds for three real joyent commits from the
replay: 11.6 to 13.9 s each (integrate 3.4 s, route 4.9 to 6.9 s, integrate
again 3.4 s), all correct. About 3.4 s of `route` is a second integration
that can be shared, giving roughly 8 to 10 s. Getting the repository is the
larger cost: its pack is about 720 MB, which a fresh hosted runner would have
to clone each time (not measured). So the dry run belongs on a runner with a
persistent clone, for now the build host, the same place gate intake and
dispatch run.

### Tools still to build

| Tool | Does |
| --- | --- |
| Dry-run dispatch | Routes a pull request's merge result, integrates, compares, posts the placement |
| Trailer decisions | `ft.route` reads `Feature:` trailers as decisions |
| Dispatch | Routes a landed commit, checks the tree, pushes the features, records the dispatch on master |
| Gate intake driver | Rebases, integrates, builds, writes master's gate-merge commit, escalates per feature |
| Release cut | Branches a release from an intake's integration commit |
| Divergence report | For replay and shadow mode: what the tools produced, what master had, the diff |

### Working on one feature on purpose

Someone deliberately working on a single feature, such as a driver import, can
check out `features/<name>` and open a pull request against it. That branch
does not build on its own (36 of 78 features need others), so building means
merging the feature's dependency closure into a separate worktree, as phase 1's
stacked builds did. This is a path for specialists, not the default.

### New features

A new feature starts as a branch on the current gate base, either by a
`Feature:` trailer naming it on its first commit or by creating it outright,
with its metadata entry (description, owner, `depends`, `upstream`). Examples
are a FreeBSD driver import, or a fix carried until gate takes it. From then on
it is taken through gate intake, built and reported like any other, and it
retires on its own if gate ends up with all of it.

### Open questions here

- Routed commits accumulate on feature branches as small commits. Do features
  keep full history, or get curated (squashed) periodically? A split commit is
  not a `fixup!`, so the earlier plan of squashing fixups at each gate intake
  does not cover it.
- How smartos-live is pointed at an integration branch other than master,
  for developers testing a feature branch's effect before landing.

## Transition: running beside master

We start in shadow mode while master-based development continues. During that
time the reference tree stays useful: the integration should keep matching
master.

Shadow mode is replay pointed at the present: `replay.py` over master's new
first-parent commits since the last run.

1. Fetch master and gate (both public; no credentials needed to read).
2. For each new master commit: a gate merge becomes a gate intake onto its
   gate commit, through the resolvers and the manifest sync; a joyent commit
   is dispatched to the features it touches; whatever still differs from master
   is routed too and recorded as work a person did.
3. Check that the integration's tree equals master's at every step.
4. When a release branch appears or gains commits, rebuild it with
   `release.py`.
5. Push the updated `features/*` and record the run on `meta/state`.

It starts from the 78 phase 1 features, which reproduce da512a7e2e6; master
was 21 commits past that on 2026-10-22. `features/tooling` is left out of the
comparison, since master does not carry `feature-tools/` or
README-SmartOS.md.

Decided 2026-10-22:

- Runs are manual for now.
- Each feature's tip at each gate intake is recorded on `meta/state` (a list
  of commit ids), not as tags on the fork.
- When a run stops, it becomes an issue on the fork naming the commit, the
  paths and the reason; the placement decision goes into a decisions file on
  `meta/state` (today it is on the build host) and the run resumes.
- Exit: every master commit reproduced over about a month including at least
  one release, with every case that needed a person being a real conflict, a
  placement decision or a mistake in master, and none a tool failure. Then
  gate intake and dispatch take over from people merging gate and routing by
  hand, as described in The process at a glance.

Still open: how commits made by the tools are attributed and signed (today
they carry the original author for routed joyent commits and are unsigned).

Replay forces equality at every step, so a divergence from master shows up
only as a "Resolve as master did" commit; two real master bugs in the wide
replay were found by reading those by hand. The divergence report (Tools still
to build) lists each one directly: what the tools produced, what master had,
and the diff, for a person to review after each run.

Replay is shadow mode run over the past, and both can start from any master
commit: phase 1 bootstraps the features there (tested six weeks and six
months back). Simulation cannot reproduce the person (master's answer stands
in), races between pull requests, or builds.

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
  release's gate base, and a joyent change that master also gets. A release
  is therefore a gate commit, plus any gate commits backported onto it, plus
  the features.
- Starting at release-20260416's branch point (06ea1eb6c40, 2026-04-15), there
  are 73 first-parent master commits up to our reference da512a7e2e6. 60 of
  them are gate merges; the other 13 are joyent changes, committed directly
  on master. Master took 3 to 12 gate merges between consecutive releases.
- Master has moved 21 commits past da512a7e2e6 since phase 1. Those are the
  first input for live shadow mode.
- Phase 1's `collect.sh` takes `JOYENT=<commit>` and derives the gate base
  from that commit's last gate merge, so the analysis can be rerun at an
  earlier point.

That window exercises dozens of gate intakes, ordinary joyent changes, a
release fix also carried on master, and two gate backports onto releases. It
does not obviously contain a feature landing upstream; whether any joyent
change in the window later reached gate is worth checking before relying on
replay to test upstream detection.

### Method

1. **Bootstrap.** Rerun the phase 1 analysis at 06ea1eb6c40, producing
   features on that commit's gate base. Check that their integration equals
   06ea1eb6c40. Phase 1's overrides match on file and pattern, so some may
   not apply to the older tree; how many need adjusting is itself a measure of
   how robust the split is.
2. **Walk master's first-parent history** to da512a7e2e6, one commit at a
   time:
    - a gate merge becomes a gate intake onto its second parent, climbing
      the escalation ladder;
    - a joyent commit is dispatched to the features that own its lines;
    - after each step, the integration's tree must equal that master commit's
      tree.
3. **Use master as the human.** When gate intake reaches the human tier, or
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
   disappear from it once a later gate intake reaches a gate that includes
   them.
5. **Compare the ends.** The replayed features at da512a7e2e6 and the 78 from
   phase 1 describe the same tree. Where their split differs, the difference
   shows how much the split depends on where the analysis starts.

Tree equality at every step means replay needs no builds: master was built and
shipped at each of those commits. Builds come in only where a step departs
from master, such as a resolver choosing a different but plausible
resolution.

### What replay needs from the tooling

These land on `features/tooling`, and replay is their first test:

1. The feature list and metadata format.  Not built yet.
2. `integrate`: the merge chain, and a tree comparison against a reference.
   Built (`ft.integrate`).
3. gate intake: rebase every feature onto a gate commit through tiers 1 to 3,
   recording the tier for each feature.  Built as `ft.rebase` with
   `resolve.py` and `manifest.py`; tier 2 (rerere) is not.
4. `route`: assign a commit's hunks to features by line ownership, splitting
   where needed and reporting what it cannot place.  Built (`ft.route`).
5. `replay`: the driver for this section, which then stays as a regression
   test for the other tools.  Built (`replay.py`), with `release.py` for the
   release rebuilds.

Results go to `meta/state` under a replay directory, kept apart from live
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
  resolvers (manifest). Gate intake cannot stop at "rebase was clean"; the
  manifest check and the tests are part of it.

### Second run: the same window with resolvers (2026-10-21)

Done with `features/tooling` 1ad185d0f20; the record is
`replay/2026-10-21-small-resolvers/` on `meta/state`.

- `resolve.py` (copyright lines, Makefile list entries) and `manifest.py`
  (the top-level `manifest` following gate's package manifests) now run at
  every gate merge.
- All 15 steps again equal master, and the end state again matches phase
  1's split for all 78 features.
- Seven of the eight pieces of person-made work now need no person. The
  one left is smartos-test.
- At a2098682c51 the manifest sync wrote the four zoneinfo lines correctly
  (`0644 root bin`) where master's merge left them without mode, owner or
  group. Master fixed that four commits later in eb7e560a400. Replay had to
  route master's broken lines back in to stay equal; with the tool running,
  the bug and its fix would not have happened.

### Wide run: release-20260416 to da512a7e2e6 (2026-10-22)

Done on nshalman-builds in one pass with `features/tooling` 2cd003134cc; the
record, with the person-made decisions and their reasons, is
`replay/2026-10-22-wide/` on `meta/state`.

- Phase 1 rerun six months back gave the same 78 features with no override
  changes.
- All 73 master commits (60 gate merges, 13 joyent commits) reproduced tree
  for tree.
- Every release forked in the window rebuilds from gate, gate backports and
  the features.  release-20260430 and release-20260514 carry commits of their
  own: two are gate backports, which belong to no feature, and OS-8741 routes
  to inotify.
- 47 of 60 gate merges needed no person.  The resolvers fired 47 times (46
  copyright, 1 Makefile list); the manifest sync changed the manifest at 16
  merges.  Of the 13 that needed someone, two were master's own mistakes the
  tools would have avoided (zoneinfo lines without attributes; six weeks of a
  stale os-tests runfile), one was a semantic change (smartos-test after
  18295), and most of the rest were real code conflicts from gate
  restructuring (64-bit fmtopo, ps.1 in mdoc, posix_spawn, dladm tests).
- 10 of 13 joyent commits routed with no help; three needed a recorded
  placement decision.
- At the end, 72 of 78 features match phase 1's split exactly; the other six
  hold the same lines in different places (zhyve.c in zone-brands rather
  than bhyve, and one OmniOS copyright line).

How routing works, as settled by this run: a file only one feature touches
goes to it whole.  A shared file is rebuilt per feature from gate, gate's
lines plus the hunks of the gate-to-target diff that feature owns: those its
own changes overlap or touch, preferring those that already hold the lines.
Building from gate rather than editing the integrated file means edits do not
spread from feature to feature over time, and features that no longer merge
after a rebase are rebuilt the same way.  Ownership is by position, never by
matching text.  A hunk nobody owns goes with its file's other changes if it is
a copyright line, to code that gate moved if a feature's lines moved with it,
and otherwise to a feature a person names; an unnamed one stops the run.

Known gaps:

- Lines git can merge only together, such as both sides of a deleted gate
  line, end up in each feature involved until a person reassigns them.
- The manifest sync judges a package shipped by any listed file or link;
  libc-tests ships a few test locale files, so one /opt/libc-tests directory
  was added that master leaves out.
- Rerere (tier 2) is not built; ps.1 conflicted at two merges in a row.

Next: live shadow mode, from da512a7e2e6 onward, and the feature metadata
format.

## Open questions

- [x] Publishing: master stays the developer branch; features follow it by
      dispatch; master's gate merges come from gate intake (decided
      2026-10-23).
- [x] Releases: cut at a gate intake from gate plus features; later fixes
      land on master first and are cherry-picked (decided 2026-10-23).
- [ ] When gate intake hits trouble, take gate in up to the last good commit,
      or stop until a person resolves it? Recommended: up to the last good
      commit.
- [x] Dispatch record: a merge on master, verified against the dispatched
      commit before it is written; serialized by the merge queue so it is a
      plain merge of identical trees (decided 2026-10-23).
- [ ] How commits made by the tools are attributed and signed.
- [ ] Do feature branches keep full history, or get curated periodically?
- [ ] How does smartos-live choose its illumos-joyent branch, and what must
      change there?
- [ ] Build infrastructure: nshalman-builds for now; what after the
      experiment?
- [ ] Test infrastructure: a VM in the nshalman-builds zone for now; what per
      release, and after the experiment?
- [ ] Should AI-proposed conflict resolutions exist at all, and is "proposes,
      never lands alone" the right limit?
- [x] Gate intake cadence: at points we choose, a few times a week or daily,
      not every gate commit (decided 2026-10-23).
- [x] Where escalations go: issues on the fork (decided 2026-10-22).
- [ ] boot/dboot and datalink/vnd: merge each pair, or test them together?
- [ ] Conflict hotspots: measure them, then decide whether to restructure any,
      such as the top-level `manifest`.
- [ ] Ownership: who owns each of the 78 features?
- [ ] zhyve.c: keep it in zone-brands, where replay kept it, or move it to
      bhyve, where phase 1 puts it?
- [x] Replay: start small (release-20260903), then widen to
      release-20260416. Both done; see Replaying history.
