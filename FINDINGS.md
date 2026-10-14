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
3. **Merge-resolution lines**: 5.6k lines (before diff restriction)
   were written in merge commits.  To review: `./report.py merge-lines`.
4. **BOUNDARY lines**: ~800 `+` lines blame to upstream commits at or
   before BASE, meaning joyent holds an older upstream version of those
   lines.  To review: `./report.py boundary`.
5. Several joyent commits are labelled "fix mismerge" of upstream
   tickets and still own lines that differ from upstream (13925 elf.c,
   12349 syscall_asm_amd64.S, 13097 vm_pageout.c, 11909 pid.c, 12789
   timer.c, 17297 libproc).  These may be legitimate lx adaptations or
   leftovers; each needs a look.
