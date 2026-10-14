# Findings

Running log of suspected bugs, mismerges, dead code, and decisions.
Nothing here has been fixed; these are leads for review.

## Decisions

- Base is the upstream parent of the newest `[illumos-gate merge]`
  (479a4a914dc at the start), not the latest `illumos/master`.
- Whole files per commit for the first pass.  `integration` goes last.
- Feature tickets are listed in commit messages; bug-fix tickets are
  summarized collectively.
- Intermediate commits are not expected to build.

## Context

- Dan's map of differences is `README-SmartOS.md` in
  TritonDataCenter/illumos-joyent PR #547 (unmerged).  Bucket names
  follow its sections where possible.
- Clustering files by shared tickets is useless: sweep tickets (OS-8361
  man renumbering, OS-7685 overlay merge, OS-2800 Bardiche, OS-7960,
  OS-7768 smatch) join ~1,300 of the ~1,800 files into one component.

## Leads

1. **qede binary blobs exist only in joyent.**
   `usr/src/uts/common/io/qede/579xx/drivers/ecore/{ecore_init_values.bin,
   ecore_init_values_zipped.bin,documentation/pictures/*}` were added by
   OS-5969 and upstream never shipped them.  Likely dead weight.
   `qede_list.h` / `qede_version.h` differ only by trailing whitespace.
2. **bpf_filter.c location.** Joyent has it in `uts/common/inet/`
   (OS-5549 moved it into ip for SO_ATTACH_FILTER on ICMP) and deletes
   upstream's `uts/common/io/bpf/bpf_filter.c`.  Deliberate, but a
   standing divergence to keep in mind when upstream touches bpf.
3. **Merge-resolution lines**: after diff restriction, ~5.1k surviving
   lines were written in merge commits; ~4.8k of those are `manifest`
   and driver tables (expected).  The ~70 code files are under review
   (results below).  To list: `./report.py merge-lines`; to inspect one:
   `./merge_lines.py <path>`.
4. **BOUNDARY lines**: ~800 `+` lines blame to upstream commits at or
   before BASE.  Nearly all are upstream content joyent moved or copied
   (bpf_filter.c 551, brand XMLs copied from ipkg).  The useful signal
   is a file whose joyent diff has *no* joyent commit behind it, which
   is how the sed revert (6) was found.  `./report.py boundary`.
5. Several joyent commits are labelled "fix mismerge" of upstream
   tickets and still own lines that differ from upstream (13925 elf.c,
   12349 syscall_asm_amd64.S, 13097 vm_pageout.c, 11909 pid.c, 12789
   timer.c, 17297 libproc).  These may be legitimate lx adaptations or
   leftovers; each needs a look.
6. **sed: upstream 586 is still reverted (CONFIRMED divergence).**
   58474c20a52 (John Sonnenschein, 2011-11-24) reverted illumos 586
   "sed -i should take an optional argument" with no stated reason, and
   it was never reinstated.  Joyent sed lacks `--in-place` and the
   optional `-i`/`-I` argument; sed.1 documents the old behavior too.
   Hypothesis (unverified): kept so BSD-style `sed -i ''`/`sed -i .bak`
   in SmartOS scripts keeps working.  Needs a decision: keep (and
   document in README-SmartOS) or drop.
7. **Audit of joyent reverts of upstream changes.**  Seven upstream
   commits were reverted in joyent history.  Checking whether the
   upstream lines still present in BASE are missing from master: only
   586 (sed) is still in effect.  17136, 13761, 8021, 8007, 7571 and
   1948 are fully present again (8021 differs by one comment block in
   abd.c, from OS-6387).
8. **Copyright/whitespace residue: 60 files** differ from upstream only
   in copyright lines, blank comment lines or whitespace (some show the
   same copyright line on both sides).  These are what is left of
   changes that were reverted or upstreamed.  They have their own
   commit (`copyright-residue`); restoring them to upstream would
   shrink the delta by 60 files with no functional change.  List:
   `data/copyright_only.txt`.

## Mismerge review results

### lx (12 files): no bugs, 1 suspect
All merge-written lx lines adapt correctly to upstream 16624 FD_CLOFORK
(4-arg kernel fcntl, f_setfd_or), 17689 posix_spawn (exec_common
UIO_USERSPACE), 18213 (stdio.h includes), 7882 /dev/full, and the
PGRPSYS_* constants (values checked identical).

9. **lx F_SETFD leaks FD_CLOFORK (VERIFIED, low).**
   `lx_fcntl.c:301` does `fcntl(fd, F_SETFD, arg, 0)` with the Linux arg
   unmasked.  Since 16624, `f_setfd_int` (`fio.c:1591`) honors
   `FD_CLOEXEC | FD_CLOFORK` (FD_CLOFORK == 2), so a Linux program
   passing bit 0x2 gets close-on-fork; Linux ignores all bits but
   FD_CLOEXEC.  Fix: pass `arg & FD_CLOEXEC`.  Found by review agent,
   checked against source.  (Cosmetic: lx_socket.c:1216 ORs
   `f_getfd()|FD_CLOEXEC` into f_setfd_or, redundant.)

## Questions for Nahum

- `jerry <jerry@opensolaris.(none)>` authored joyent commits in
  2010-2011 (OS-49, OS-52, OS-57, OS-66, OS-138: zone multi-tenancy,
  zfs_zone).  Almost certainly Jerry Jelinek; add a mailmap entry?
- `Joyent Automation <releng@joyent.com>` is credited as a co-author
  (e.g. OS-8027, OS-8022).  Keep bot identities in Co-authored-by, or
  drop them?
- Co-author identity uses each person's newest name/email (so Brian
  Bennett is credited as Brianna Bennett <bahamat@digitalelf.net>).
  OK as the default?

## Known limitations of the current branch

- Ticket lists in commit messages include every ticket with at least
  one surviving line in the bucket's files, so a few look misplaced
  (e.g. OS-6547 KPTI shows in brand-kernel because desctbls.c has lx
  and KPTI lines interleaved).  That is accurate to the whole-file
  rule, not a classification error.
- The feature/fix split is a subject-line heuristic.
- `misc` (54 files) is a catch-all that deserves splitting.
