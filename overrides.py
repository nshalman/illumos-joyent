# Hand-assigned buckets for files the path rules in classify.py do not
# cover (mostly generic kernel and libc files touched by several features).
# B is a list, not a dict, so a bucket may appear more than once.
# Each file was placed by looking at which tickets wrote its '+' lines
# (see report_tickets.py).  Paths are relative to usr/src/.
#
#  brand-*       generic kernel/libc hooks whose changes are predominantly
#                for lx, split by subsystem: brand ops, exec, process and
#                signals, poll/events/timers, sockets, fs syscalls, lx NFS,
#                x86 context/trap, native-root userland
#  zone-kernel   zone.c/zone.h and zone resource management: memory caps,
#                RSS tracking, vm_usage, page invalidation, FX/RT priority,
#                zone privileges, kmem access restrictions
#  inotify       file event monitoring: fem, vnode events, portfs, and the
#                per-filesystem event emission inotify relies on
B = [
# brand-kernel split by subsystem (Nahum, 2026-10-14).  These are the
# generic kernel/libc files whose changes are predominantly for lx.
('brand-ops', '''
uts/common/os/brand.c uts/common/sys/brand.h uts/intel/sys/machbrand.h
uts/common/syscall/brandsys.c
uts/common/brand/sn1/sn1_brand.c uts/common/brand/sn1/sn1_brand.h
uts/common/brand/solaris10/s10_brand.c uts/common/brand/solaris10/s10_brand.h
'''),
('brand-exec', '''
uts/common/exec/elf/elf.c uts/common/exec/elf/elf_notes.c uts/common/exec/intp/intp.c
uts/common/exec/java/java.c uts/common/exec/shbin/shbin.c uts/common/os/exec.c
uts/common/sys/exec.h uts/common/sys/auxv.h uts/common/os/mmapobj.c
uts/common/os/core.c uts/common/fs/vfs.c lib/libc/port/gen/getauxv.c
'''),
('brand-process', '''
uts/common/os/exit.c uts/common/os/fork.c uts/common/os/lwp.c uts/common/sys/klwp.h
uts/common/os/sig.c uts/common/sys/thread.h uts/common/sys/proc.h uts/common/os/pid.c
uts/common/os/contract.c uts/common/os/acct.c uts/common/sys/acct.h uts/common/os/main.c
uts/common/sys/signal.h uts/common/sys/iso/signal_iso.h uts/common/sys/user.h
uts/common/sys/procfs.h uts/common/disp/priocntl.c uts/common/sys/fss.h
uts/common/sys/ia.h uts/common/sys/ts.h uts/common/os/rctl.c uts/common/os/rctl_proc.c
uts/common/os/grow.c uts/common/sys/vmsystm.h uts/i86pc/vm/vm_machdep.c
uts/common/os/sysent.c uts/common/os/cpu.c uts/common/sys/cpuvar.h
lib/libc/amd64/gen/siginfolst.c lib/libc/i386/gen/siginfolst.c
lib/libc/sparc/gen/siginfolst.c lib/libc/sparcv9/gen/siginfolst.c
lib/libc/port/gen/siglist.c lib/libc/port/gen/str2sig.c
lib/libc/port/threads/sigaction.c lib/libc/port/threads/thr.c lib/libc/inc/thr_uberdata.h
lib/libproc/common/Pcontrol.c
'''),
('brand-events', '''
uts/common/syscall/poll.c uts/common/sys/poll_impl.h uts/common/io/eventfd.c
uts/common/sys/eventfd.h uts/common/io/signalfd.c uts/common/os/timer.c
uts/common/sys/timer.h uts/common/sys/time.h uts/common/fs/fifofs/fifosubr.c
uts/common/fs/fifofs/fifovnops.c uts/common/sys/fs/fifonode.h uts/common/os/streamio.c
'''),
('brand-net', '''
uts/common/fs/sockfs/sockcommon_subr.c uts/common/fs/sockfs/socksubr.c
uts/common/fs/sockfs/socktpi_impl.h uts/common/sys/socket.h uts/common/sys/uio.h
uts/common/inet/udp/udp.c uts/common/inet/udp/udp_opt_data.c uts/common/inet/udp_impl.h
uts/common/netinet/udp.h uts/common/inet/ip/conn_opt.c uts/common/inet/ip/ipclassifier.c
uts/common/inet/ipclassifier.h cmd/cmd-inet/etc/sock2path.d/system%2Fkernel
cmd/cmd-inet/sbin/dhcpagent/defaults.c lib/libdhcpagent/common/dhcpagent_util.c
'''),
('brand-fs', '''
uts/common/syscall/chdir.c uts/common/syscall/fcntl.c uts/common/syscall/open.c
uts/common/syscall/stat.c uts/common/syscall/umount.c uts/common/syscall/uadmin.c
uts/common/sys/uadmin.h uts/common/sys/file.h uts/common/os/fio.c uts/common/fs/lookup.c
uts/common/io/ptm.c uts/common/sys/ptms.h uts/common/sys/termios.h
'''),
('brand-nfs', '''
uts/common/klm/klmmod.c uts/common/klm/nlm_dispatch.c uts/common/klm/nlm_impl.c
uts/common/klm/nlm_impl.h uts/common/klm/mapfile-mod uts/common/nfs/nfssys.h
uts/common/fs/nfs/nfs_sys.c cmd/fs.d/nfs/lib/nfs_sec.c cmd/fs.d/nfs/lockd/lockd.c
cmd/fs.d/mount.c lib/libnsl/netselect/netselect.c
'''),
('brand-x86', '''
uts/intel/syscall/getcontext.c uts/sparc/syscall/getcontext.c uts/intel/os/sendsig.c
uts/intel/os/archdep.c uts/i86pc/ml/offsets.in uts/intel/genassym/offsets.in
uts/intel/genassym/Makefile uts/i86pc/ml/syscall_asm_amd64.S uts/i86pc/os/trap.c
uts/i86pc/sys/apic.h uts/intel/os/desctbls.c uts/intel/sys/segments.h
uts/intel/sys/ucontext.h uts/i86pc/sys/comm_page.h uts/intel/os/comm_page_util.c
uts/intel/os/cpuid.c man/man4d/cpuid.4d uts/i86pc/ml/kpti_trampolines.S
uts/intel/ml/modstubs.S
'''),
('brand-native', '''
lib/libc/port/sys/zone.c lib/libcurses/screen/setupterm.c lib/libc/port/stdio/system.c
head/regexp.h cmd/truss/codes.c cmd/truss/print.c cmd/truss/systable.c
cmd/prstat/prstat.c cmd/prstat/prstat.h man/man8/prstat.8
'''),
('zone-kernel', '''
uts/common/os/zone.c uts/common/sys/zone.h head/zone.h uts/common/syscall/sysconfig.c
uts/common/vm/page.h uts/i86pc/vm/hment.c uts/i86pc/os/startup.c uts/sfmmu/vm/hat_sfmmu.c
uts/common/vm/vm_usage.c uts/common/sys/vm_usage.h uts/common/os/vm_pageout.c uts/common/sys/vm.h
uts/common/vm/vm_page.c uts/common/os/kstat_fr.c uts/common/sys/resource.h
uts/common/syscall/rusagesys.c uts/i86pc/sys/vm_machparam.h uts/common/vm/hat.h
uts/i86pc/vm/hat_i86.c uts/common/sys/buf.h uts/common/sys/mman.h uts/common/syscall/memcntl.c
uts/common/vm/seg_vn.c uts/common/vm/vm_pvn.c uts/common/vm/vm_as.c
uts/common/os/policy.c uts/common/sys/policy.h uts/common/os/priv_defs man/man7/privileges.7
uts/common/disp/fx.c uts/common/sys/fx.h uts/common/disp/rt.c uts/common/sys/rt.h uts/common/disp/rt_dptbl.c
uts/common/contract/process.c uts/common/sys/contract/process.h
uts/common/os/cred.c uts/common/sys/cred.h uts/common/io/ksyms.c uts/common/io/mem.c uts/common/io/physmem.c
uts/common/fs/nfs/nfs3_vfsops.c uts/common/fs/nfs/nfs4_vfsops.c uts/common/fs/nfs/nfs_vfsops.c
cmd/prtconf/prtconf.c man/man7/resource_controls.7
'''),
('inotify', '''
uts/common/fs/fem.c uts/common/os/sched.c uts/common/disp/thread.c uts/intel/ml/swtch.S
uts/common/fs/vnode.c uts/common/sys/vnode.h uts/common/fs/portfs/port_fop.c
uts/common/fs/nfs/nfs3_vnops.c uts/common/fs/nfs/nfs4_vnops.c uts/common/fs/nfs/nfs_vnops.c
uts/common/fs/pcfs/pc_vnops.c uts/common/fs/pcfs/pc_dir.c uts/common/fs/udfs/udf_vnops.c
uts/common/fs/udfs/udf_dir.c uts/common/fs/ufs/ufs_vnops.c
test/zfs-tests/cmd/watch_dir/watch_dir.c
test/zfs-tests/tests/functional/cli_root/zfs_mount/zfs_mount_watched_portfs.ksh
'''),
('datalink', '''
uts/common/inet/ip.h uts/common/inet/ip/ip.c uts/common/inet/ip/ip_if.c uts/common/io/mac/mac_protect.c
uts/common/sys/mac_flow.h uts/common/sys/mac_client_priv.h uts/common/io/mac/mac_client.c
uts/common/sys/mac_client_impl.h uts/common/io/mac/mac.c uts/common/io/mac/mac_stat.c uts/common/sys/mac_client.h
common/net/dhcp/octet.c cmd/ibd_upgrade/ibd_delete_link.c
test/util-tests/tests/dladm/allowed-cids.ksh test/util-tests/tests/dladm/allowed-ips.ksh
test/util-tests/tests/dladm/common.ksh test/util-tests/tests/dladm/dynamic-methods.ksh
test/util-tests/tests/dladm/vnic-mtu.ksh
'''),
('vnd', '''
uts/common/inet/squeue.c uts/common/sys/squeue.h uts/common/sys/squeue_impl.h
uts/common/inet/ip/ip_squeue.c uts/common/sys/neti.h uts/common/sys/netstack.h uts/common/sys/dlpi.h
uts/common/io/ksocket/ksocket.c lib/libdlpi/common/libdlpi.c lib/libdlpi/common/libdlpi.h
lib/libdlpi/common/libdlpi_impl.h man/man3dlpi/dlpi_open.3dlpi cmd/cmd-inet/usr.sbin/snoop/snoop.c
cmd/cmd-inet/usr.sbin/snoop/snoop_capture.c man/man8/snoop.8 uts/common/io/rsm/rsm.c
test/os-tests/tests/OS-6097.c
'''),
('overlay-svp', '''
cmd/cmd-inet/usr.sbin/snoop/snoop.h cmd/cmd-inet/usr.sbin/snoop/snoop_rport.c
cmd/cmd-inet/usr.sbin/snoop/snoop_svp.c
'''),
('icmp-bpf', '''
uts/common/inet/ip/icmp.c uts/common/inet/ip/icmp_opt_data.c uts/common/inet/rawip_impl.h
uts/common/inet/sockmods/sockmod_pfp.c
'''),
('datafilt', '''
uts/common/fs/sockfs/sockfilter.c uts/common/fs/sockfs/sockfilter_impl.h uts/common/sys/socketvar.h
uts/common/sys/sockfilter.h uts/common/fs/sockfs/sockcommon_sops.c
'''),
('zfd', 'cmd/devfsadm/misc_link.c uts/common/io/pseudo.conf'),
('net-misc', '''
cmd/cmd-inet/usr.sbin/arp.c cmd/cmd-inet/usr.sbin/ndp.c cmd/cmd-inet/usr.sbin/route.c man/man8/route.8
cmd/cmd-inet/sbin/dhcpagent/request.c uts/common/inet/ipd/ipd.c uts/common/sys/ipd.h
man/man3xnet/htonl.3xnet
'''),
('zones-tools', 'lib/xml/os_dtd.c lib/xml/os_dtd.h'),
('boot', 'uts/common/io/tem_safe.c lib/libefi/common/crc32_efi.c lib/libefi/common/rdwr_efi.c cmd/fs.d/pcfs/mkfs/mkfs_main.c'),
('zfs', 'lib/libbe/common/be_list.c lib/libgrubmgmt/common/libgrub_fs.c uts/common/sys/fs/zfs.h'),
('dump-encryption', 'lib/libc/port/gen/arc4random.c test/libc-tests/tests/random/chacha_tv.c'),
('bunyan', 'test/util-tests/tests/bunyan/btest.c test/util-tests/tests/bunyan/bunyan.ksh'),
('rtld-sgs', 'uts/common/sys/elf.h man/man1/ld.so.1.1'),
('platform-config', '''
cmd/auditd/auditd.xml cmd/cmd-crypto/etc/pkcs11.conf cmd/cmd-inet/etc/services cmd/coreadm/coreadm.xml
cmd/dispadmin/dispadmin.conf cmd/localedef/UTF-8.x cmd/cmd-inet/usr.sbin/routeadm/routeadm.c
'''),
('smartos-test', '''
test/os-tests/tests/secflags/secflags_zonecfg.sh test/util-tests/tests/grep_xpg4/grep_test.ksh
test/test-runner/cmd/run test/libc-tests/runfiles/default.run test/os-tests/runfiles/default.run
test/util-tests/runfiles/default.run test/util-tests/tests/awk/tests/T.misc
test/util-tests/tests/dis/distest.ksh
'''),
('altexec', 'man/man1has/csh.1has'),
# Split out of misc (Nahum, 2026-10-14).
('sed', 'cmd/sed/main.c man/man1/sed.1'),
('sysv-ipc', '''
uts/common/os/ipc.c uts/common/os/shm.c uts/common/sys/ipc_impl.h
uts/common/sys/shm.h uts/common/sys/shm_impl.h
'''),
('kernel-platform', '''
uts/i86pc/os/cpr_impl.c uts/i86pc/os/ibft.c uts/i86pc/os/lgrpplat.c
uts/intel/pcbe/core_pcbe.c uts/common/conf/param.c uts/common/sys/param.h
'''),
('sched', 'uts/common/disp/cmt.c uts/common/disp/disp.c'),
('compiler-fixes', '''
cmd/adbgen/common/adbsub.c lib/libc/inc/thr_inlines.h lib/libnisdb/db_mindex3.cc
lib/libnisdb/db_table.cc lib/libnisdb/nis_db.cc cmd/vi/port/ex_cmdsub.c
uts/sun4u/io/pci/pcisch.c
'''),
('nfs', 'cmd/fs.d/nfs/mount/mount.c cmd/fs.d/nfs/umount/umount.c cmd/fs.d/nfs/svc/nfs-server'),
('man-fixes', '''
man/man1/diff.1 man/man1/hostname.1 man/man3c/psignal.3c man/man4/swap.4
man/man8/tunefs.8 man/man9f/ddi_fm_init.9f man/man9f/bzero.9f
'''),
('ctf', 'lib/libproc/common/Psymtab.c lib/libproc/common/Pcontrol.h'),
('fm-topo', 'uts/intel/io/ipmi/ipmivars.h cmd/devfsadm/devlink.tab.sh'),
('platform-config', 'cmd/halt/halt.c man/man8/reboot.8'),
('ptools', 'uts/common/fs/proc/prcontrol.c'),
('zone-kernel', 'uts/common/io/random.c'),
('bhyve', 'uts/intel/sys/vmm.h'),
# parent Makefiles that wire in more than one feature
('integration', 'cmd/fs.d/Makefile'),
# OS-5549 moved bpf_filter into ip; these drop the io/bpf include path
('icmp-bpf', '''
uts/intel/bpf/Makefile uts/intel/dld/Makefile uts/intel/dls/Makefile uts/intel/icmp/Makefile
uts/intel/iptun/Makefile uts/intel/mac/Makefile uts/intel/mac_ether/Makefile
uts/intel/mac_ib/Makefile uts/intel/mac_wifi/Makefile
'''),
# consumers of the platform OpenSSL link the sunw_-prefixed libraries
('openssl-sunw', '''
cmd/cmd-inet/usr.lib/wpad/Makefile cmd/sendmail/src/Makefile
lib/krb5/plugins/preauth/pkinit/Makefile.com lib/libkmf/plugins/kmf_openssl/Makefile.com
'''),
]
OVERRIDES = {}
for _b, _s in B:
    for _p in _s.split():
        _k = 'usr/src/' + _p
        assert _k not in OVERRIDES, 'duplicate override: ' + _k
        OVERRIDES[_k] = _b
