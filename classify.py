#!/usr/bin/env python3
# Assign every delta path to exactly one bucket.  In order of precedence:
#  1. copyright residue: files whose diff is only copyright/comment noise
#     (data/copyright_only.txt) go to copyright-residue
#  2. hand overrides (overrides.py)
#  3. path rules (RULES, first match wins)
#  4. hub files (Makefiles, mapfiles, package manifests) that a path rule
#     sent to integration but that live in one feature's directory follow
#     that feature; GLOBAL_HUB files always stay in integration
#  5. integration files are divided by kind (INTEGRATION_SPLIT)
#  6. the rest: a vote of the tickets that wrote the file's lines, where
#     each ticket's bucket is learned from the path-placed files it wrote
#     in; files whose biggest share belongs to an unplaced ticket go to misc
import os, re, sys, collections, json

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'data')
sys.path.insert(0, HERE)
from overrides import OVERRIDES

# Ordered (bucket, regex). First match wins.
RULES = [
    # integration: shared/hub files land in the last commit
    ('integration', r'^manifest$|^boot\.manifest$|^\.gitignore$|/\.gitignore$|^Jenkinsfile$|^exception_lists/|^mancheck\.conf$|^usr/src/Makefile\.testarchive$|^usr/src/req\.flg$|^usr/src/Targetdirs$|/Makefile[^/]*$|/Manlink$|^usr/src/pkg/manifests/(?!system-test-(vnd|smartos)test|driver-crypto-nfp|system-zones-brand-lx)|^usr/src/tools/findunref/|^usr/src/uts/intel/os/(driver_aliases|driver_classes|minor_perm|name_to_major|path_to_inst|device_policy)$|ipf\.global-objs\.debug64$|/mapfile-vers$|/mapfile-mod$|^usr/src/uts/common/mapfiles/'),
    ('lx', r'brand/lx|/lx_|lxautofs|lxprocfs|/lxproc|lxproc\.|/man7/lx\.7$|system-zones-brand-lx\.p5m$|/lx\.h$'),
    ('vnd', r'/vnd[^/]*$|/vnd/|libvnd|vndadm|vndstat|man3vnd|/frameio|gsqueue|vndtest'),
    ('overlay-svp', r'lib/varpd|cmd/varpd|io/overlay/|vxlan\.4p|refhash'),
    ('resolver', r'libresolv2_joy|resolv_joy\.h|lib/nsswitch/dns/|netfiles/(nsswitch|resolv)\.conf'),
    ('smartlogin', r'libzdoor|libsmartsshd|zdoor\.h'),
    ('bunyan', r'libbunyan'),
    ('nvpair-json', r'nvpair_json|json_nvlist|libnvpair\.h$'),
    ('hyprlofs', r'hyprlofs'),
    ('inotify', r'inotify'),
    ('ipf-cfw', r'/ipf/|cmd/ipf/|ipf_cfw'),
    ('datafilt', r'datafilt'),
    ('icmp-bpf', r'inet/bpf|io/bpf/'),
    ('nfp', r'/nfp/|/nfp$|driver-crypto-nfp'),
    ('vmxnet', r'vmxnet'),
    ('zfd', r'zfd'),
    ('zfs-zone-io', r'zfs_zone|ziostat|vfsstat|arcstat|zfscache'),
    ('dump-encryption', r'common/crypto/chacha|cmd/dumpadm/|cmd/savecore/|sys/dumphdr\.h|sys/dumpadm\.h|/dumpadm\.8|/savecore\.8|os/dumpsubr\.c|io/dump\.c'),
    ('ctf', r'tools/ctf/|lib/libctf/'),
    ('fm-topo', r'lib/fm/|cmd/fm/|libipmi'),
    ('boot', r'^usr/src/boot/|^usr/src/grub/|pnglite'),
    ('dboot', r'uts/i86pc/dboot/'),
    ('bhyve', r'cmd/bhyve/|cmd/zhyve/|libppt'),
    ('zone-brands', r'lib/brand/|lib/libbrand/'),
    ('zone-memory', r'cmd/rcap/'),
    ('datalink', r'cmd/dladm/|cmd/dlmgmtd/|lib/libdladm/|cmd/dlstat/|cmd/flowadm|cmd/flowstat|uts/common/io/dl[sd]/|sys/dl[sd][_.]|sys/dls_|sys/dld_|lib/libipadm|cmd/cmd-inet/lib/ipmgmtd|/dladm\.8|/flowadm\.8'),
    ('zones-admin', r'cmd/zoneadmd/|cmd/zlogin/|/zlogin\.1$'),
    ('zones-tools', r'cmd/zoneadm|cmd/zonecfg|cmd/zlogin|lib/libzonecfg|head/libzonecfg|cmd/zonename|cmd/zonestat|/zoneadm\.8|/zonecfg\.8|/zlogin\.1'),
    ('ptools', r'cmd/ptools/|cmd/pgrep/|cmd/ps/|fs/proc/prargv|/pgrep\.1|/ps\.1b?$|/process\.5$|/proc\.5$'),
    ('platform-config', r'cmd/svc/milestone|cmd/Adm/|cmd/nsadmin/|cmd/cron/|cmd/logadm/|cmd/syslogd/|cmd/init/|cmd/initpkg/|cmd/login/|tools/protocmp/stdusers|crontab\.1|lib/libsecdb/user_attr'),
    ('ssh-removal', r'cmd/ssh/'),
    ('altexec', r'altexec'),
    ('column', r'/column[/.]'),
    ('machid', r'machid'),
    ('nicstat', r'nicstat'),
    ('smartos-test', r'test/smartos-test|smartostest'),
    ('tcp-connstat', r'cmd/connstat|inet/tcp|tcp_impl\.h|inet/mib2\.h|/connstat\.8'),
    ('tmpfs', r'fs/tmpfs/|sys/fs/tmp\.h|tests/tmpfs/'),
    ('zone-cpu', r'cpucaps'),
    ('sdev', r'uts/common/fs/dev/|sdev_impl'),
    ('mdb', r'cmd/mdb/|test/util-tests/tests/mdb/'),
    ('dtrace', r'cmd/dtrace/|lib/libdtrace/|uts/common/dtrace/|sys/systrace\.h|intel/dtrace/'),
    ('rtld-sgs', r'cmd/sgs/'),
    ('zfs', r'fs/zfs/|lib/libzfs/|cmd/zfs/|cmd/zpool/|common/zfs/|zfs-tests|libfakekernel|lib/libzpool|libshare/nfs|cmd/fs.d/nfs/lib/smfcfg'),
    ('storage-drivers', r'io/qede|qede|mpt_sas|mr_sas|scsi/|sata/|ixgbe|dktp|dadk|sd\.conf|iscsi|libdiskmgt'),
    ('smf', r'cmd/svc/|lib/libscf/'),
    ('onbld-tools', r'^usr/src/tools/'),
]
RULES = [(b, re.compile(r)) for b, r in RULES]

# Files that end up in integration are then divided by kind, so the
# build changes are not buried among long lists.  First match wins;
# anything else (Makefiles, mapfiles) stays in integration.
INTEGRATION_SPLIT = [(b, re.compile(r)) for b, r in [
    ('integration-manifest', r'^manifest$|^boot\.manifest$'),
    ('integration-drivers', r'^usr/src/uts/intel/os/(driver_aliases|driver_classes|'
        r'minor_perm|name_to_major|path_to_inst|device_policy)$'),
    ('integration-pkg', r'^usr/src/pkg/manifests/|/Manlink$|^usr/src/Targetdirs$'),
    ('integration-checks', r'^exception_lists/|^mancheck\.conf$|^Jenkinsfile$|'
        r'(^|/)\.gitignore$'),
]]

# Hub files that always stay in integration, even if a feature rule or
# their siblings would claim them.
GLOBAL_HUB = re.compile(r'^manifest$|^boot\.manifest$|^Jenkinsfile$|'
    r'^exception_lists/|^mancheck\.conf$|^usr/src/[^/]+$|'
    r'^usr/src/(cmd|lib|man|test|tools|uts|head|ucbhead)/(Makefile[^/]*|\.gitignore)$|'
    r'^usr/src/uts/[^/]+/Makefile[^/]*$|^usr/src/uts/common/sys/Makefile$|'
    r'/man[0-9a-z]+/(Makefile|Manlink)$|^usr/src/pkg/manifests/|'
    r'^usr/src/uts/intel/os/|^usr/src/lib/libc/|/\.gitignore$')

TICKET = re.compile(r'(?:Revert "?|backout )?([A-Z]+-\d+|\d{4,5})\b')

AUTHORS = {}

def load():
    authors = AUTHORS
    commits = {}
    for l in open(DATA + '/commits.tsv'):
        h, p, d, a, s = l.rstrip('\n').split('\t', 4)
        authors[h] = a
        if len(p.split()) > 1:
            t = 'MERGE'
        else:
            m = TICKET.match(s)
            t = m.group(1) if m else 'untagged:' + h[:11]
        commits[h] = (t, s, d)
    delta = []
    for l in open(DATA + '/delta.txt'):
        st, f = l.rstrip('\n').split('\t')
        delta.append((st, f))
    blame = {}
    for st, f in delta:
        fn = DATA + '/blame/' + f.replace('/', '%')
        c = collections.Counter()
        if os.path.exists(fn):
            for l in open(fn):
                n, h = l.split()
                if h != 'BOUNDARY':
                    c[commits.get(h, ('?',))[0]] += int(n)
        blame[f] = c
    return commits, delta, blame

def load_raw_blame():
    """Per-file Counter of '+' lines by commit sha, BOUNDARY included."""
    raw = {}
    for fn in os.listdir(DATA + '/blame'):
        c = collections.Counter()
        for l in open(DATA + '/blame/' + fn):
            n, h = l.split()
            c[h] += int(n)
        raw[fn.replace('%', '/')] = c
    return raw

def path_bucket(f, skip_integration=False):
    for b, r in RULES:
        if skip_integration and b == 'integration':
            continue
        if r.search(f):
            return b
    return None

def classify():
    commits, delta, blame = load()
    assign, how = {}, {}
    residue = set()
    if os.path.exists(DATA + '/copyright_only.txt'):
        residue = set(open(DATA + '/copyright_only.txt').read().split())
    for st, f in delta:
        if f in residue:
            # differs from upstream only in copyright/comment noise
            assign[f], how[f] = 'copyright-residue', 'residue'
        elif f in OVERRIDES:
            assign[f], how[f] = OVERRIDES[f], 'override'
        else:
            b = path_bucket(f)
            if b:
                assign[f], how[f] = b, 'path'
    # A hub-type file (Makefile, mapfile, package manifest) that lives
    # in a single feature's directory belongs with that feature; only
    # hubs shared between features stay in integration.
    for f, b in list(assign.items()):
        if b != 'integration' or how[f] != 'path' or GLOBAL_HUB.search(f):
            continue
        nb = path_bucket(f, skip_integration=True)
        if nb is None:
            d = os.path.dirname(f)
            sib = collections.Counter(assign[g] for g in assign
                if os.path.dirname(g) == d and assign[g] != 'integration')
            if len(sib) == 1:
                nb = list(sib)[0]
        if nb:
            assign[f], how[f] = nb, 'added-hub'
    # learn ticket -> bucket from path-assigned, non-integration files
    tb = collections.defaultdict(collections.Counter)
    for f, b in assign.items():
        if b in ('integration', 'copyright-residue'):
            continue
        for t, n in blame[f].items():
            tb[t][b] += n
    ticket_bucket = {}
    for t, c in tb.items():
        if t == 'MERGE':
            continue
        b, n = c.most_common(1)[0]
        # tickets spread across buckets (sweeps) stay neutral
        if n >= 0.6 * sum(c.values()):
            ticket_bucket[t] = b
    votes = {}
    for st, f in delta:
        if f in assign:
            continue
        v = collections.Counter()
        for t, n in blame[f].items():
            v[ticket_bucket.get(t, '?' + t)] += n
        votes[f] = v
        top = [k for k, _ in v.most_common()]
        if top and not top[0].startswith('?'):
            assign[f], how[f] = top[0], 'vote'
        else:
            assign[f], how[f] = 'misc', 'none'
    for f, b in assign.items():
        if b == 'integration':
            for nb, r in INTEGRATION_SPLIT:
                if r.search(f):
                    assign[f] = nb
                    break
    return commits, delta, blame, assign, how, votes, ticket_bucket

if __name__ == '__main__':
    commits, delta, blame, assign, how, votes, tbk = classify()
    json.dump(assign, open(DATA + '/assign.json', 'w'), indent=0, sort_keys=True)
    c = collections.Counter(assign.values())
    for b, n in c.most_common():
        hc = collections.Counter(how[f] for f in assign if assign[f] == b)
        print('%-16s %4d  %s' % (b, n, dict(hc)))
    if '-v' in sys.argv:
        for f in sorted(votes):
            v = votes[f]
            print('%-14s %s  %s' % (assign[f], f,
                  ' '.join('%s:%d' % kv for kv in v.most_common(4))))
