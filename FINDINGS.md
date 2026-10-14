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

### ZFS/VM (13 files) and kernel/boot/tools (17 files): no mismerges
Merge-written lines correctly adapt joyent code to upstream changes
(zfs mount_and_share / snapshot batching, txg_delay in ns, vdev_queue
AVL, max_bonuslen, 13097 pageout rework, vm_usage uio_seg, VN_RELE_LOCKED,
14890 dboot EFI memmap, 15583 core-file sizing, ucontext uc_filler,
16700 eventfd wakeups, handle-based ctf_convert, FD_CLOFORK in truss).

Bugs found in ordinary joyent commits along the way, each checked
against source in master (all joyent-only code; upstream lacks it):

10. **tmpfs xattr dir error path frees the wrong node (VERIFIED, real).**
    `tmp_vnops.c` tmp_lookup(), ~line 924 (08280dbb7d3, OS-5539 era):
    on `tdirinit()` failure (ENOSPC at the size limit) it does
    `v_flag &= V_XATTRDIR` (should be `&= ~V_XATTRDIR`) and then
    `tmpnode_cleanup(tp)` on the *parent* instead of `xdp`: zeroes the
    parent's link count, truncates it if it is a directory, drops a hold
    the caller owns, and leaks xdp.  Triggerable by creating an xattr
    dir on a full size-limited tmpfs.  Most serious finding so far.
11. **zfs_ioctl.c operator precedence (VERIFIED).**  ~lines 2221 and
    2433: `(error = get_nvlist(...) != 0)` assigns 1 (EPERM) instead of
    the real error (e4c080eef3a, OS-1048 cached props).
12. **Core-file .debug_* output loop off by one (VERIFIED, low).**
    `elf.c` ~line 2129 `off = 0;` with the loop starting at i = 1, so it
    reads header i-1 and never the last header; the counting loop at
    ~1963 correctly starts at `e_shentsize` (685e6567cd5).
13. **Pconvert_file_ctf always returns NULL (VERIFIED, low).**
    `Psymtab.c` ~line 801 returns NULL even after setting
    `fptr->file_ctfp`, so the first Pbuild_file_ctf call fails
    (092a4fbb8cf).
14. Reported by review agents, NOT yet verified by me:
    - zfs_zone_txg_delay() returns 0 (no wait) for zones without
      zpers_zfsp, where upstream waits 10ms (4851e24d85b, OS-6540).
    - vm_usage.c: VMUSAGE_A_ZONE stripped from flags but not flags_orig
      for non-global callers, so req_zone_id is used uninitialized
      (2f904f0710c); no cross-zone leak.
    - zfs destroy without -F prints errors twice (OS-604).
    - dboot_add_memlist drops upstream's `type == t` merge guard; only
      matters for unsorted firmware maps.
14b. **fm ipmi IPv6 route enumeration (VERIFIED).**  `ipmi_enum.c` ~837:
    `inet_ntop(..., ipv6_routes[i], sizeof (ipv6_routes[i]))` passes
    sizeof(char *) == 8 for an INET6_ADDRSTRLEN buffer, so any IPv6
    route longer than 7 chars fails with ENOSPC and aborts the whole
    service-processor node enumeration (4a99ae16188, joyent-only code).
    Fix: INET6_ADDRSTRLEN.

### datalink/zones/misc (28 files): no mismerges
Includes the flag renumbering joyent did to dodge new upstream values
(DL_PROMISC_FIXUPS 0x05 -> 0x07 etc.; in-tree consistent, an ABI change
for any out-of-tree DLPI user), zonecfg token renumbering (checked
index-for-index), and smartos-test header-tests switch (a correct fix
made inside merge eab31c4851f).  Not yet verified by me:
- net-early-admin:53-56 unconditional `svcadm enable varpd`, marked
  "XXX Until OS-8367 is sorted out", added in merge 4822583a749.
  Is OS-8367 resolved?
- crontab usage string advertises `-g` alone, code requires `-l`
  (merge 82a64156a05).
- zcons.c:62 merge capitalized "Zcons driver" (cosmetic).

15. Cosmetic leftovers (not worth a commit of their own): vm_pageout.c
    comment lost its first line in e995d04dc2a; stray blank lines and
    dropped braces in libzfs_iter.c; space indentation in zpool_main.c;
    stale /*ARGSUSED*/ and wrong __unused in eventfd.c; exit.c comments
    with tabs instead of double spaces (a13af751641).

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
