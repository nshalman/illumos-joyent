#!/usr/bin/bash
#
# buildcheck.sh: compile-check trees on an illumos build host inside a
# smartos-live workspace, without touching smartos-live's own build.
#
#   buildcheck.sh setup           create the $FB dataset and an illumos
#                                 clone in it, with its own illumos.sh
#   buildcheck.sh baseline BASE JOYENT
#                                 check out BASE in the clone and commit the
#                                 baseline.txt files (baseline.py) on top
#                                 (branch "baseline")
#   buildcheck.sh build LABEL     build the clone's current checkout the
#                                 way tools/build_illumos does; results go
#                                 to $RESULTS/LABEL
#   buildcheck.sh snapshot NAME   snapshot the dataset (e.g. after building
#                                 the baseline)
#   buildcheck.sh feature NAME [SNAP]
#                                 roll back to SNAP (default gate-built),
#                                 merge features/NAME from $SRCWS onto the
#                                 baseline, touch every file it changes, and
#                                 build incrementally as feature-NAME
#   buildcheck.sh run [SNAP]      build every feature in buildcheck-order.txt
#                                 that has no result yet, one at a time
#   buildcheck.sh summary         one line per result in $RESULTS
#
# The illumos.sh is smartos-live's, except that the workspace is $FB's
# clone and ROOT/PARENT_ROOT are that clone's own proto area: smartos-live's
# shared proto holds illumos-joyent headers and libraries that would hide
# missing dependencies.  The toolchain (proto.strap) is shared.  It also
# drops nightly's -m: with postfix disabled, every mailed report leaves a
# sendmail/postdrop pair hanging.
#
set -o pipefail

SL=${SL:-/workspace/smartos-live}
SRCWS=${SRCWS:-$SL/projects/illumos}
FB=${FB:-/workspace/fb}
WS=$FB/illumos
RESULTS=${RESULTS:-/workspace/fb-results}
DATASET=${DATASET:-zones/$(zonename)/data/workspace/fb}

die() { echo "buildcheck: $*" >&2; exit 1; }

setup() {
	zfs list "$DATASET" >/dev/null 2>&1 && die "$DATASET already exists"
	zfs create "$DATASET" || die "zfs create failed"
	git clone -q --shared --no-checkout "$SRCWS" "$WS" || die "clone failed"
	cp -a "$SRCWS"/closed "$SRCWS"/on-closed-bin*.tar.bz2 "$WS"/
	sed -e "s|^GATE=.*|GATE=\"restructure\"; export GATE|" \
	    -e "s|^CODEMGR_WS=.*|CODEMGR_WS=\"$WS\";	export CODEMGR_WS|" \
	    -e "s|^ROOT=.*|ROOT=\"$WS/proto/root_i386\";	export ROOT|" \
	    -e "s|^PARENT_ROOT=.*|PARENT_ROOT=\"$WS/proto/root_i386\";	export PARENT_ROOT|" \
	    -e '/^NIGHTLY_OPTIONS=/s/^\(NIGHTLY_OPTIONS="-[^"m]*\)m/\1/' \
	    "$SRCWS"/illumos.sh > "$FB"/illumos.sh
	grep -n "^CODEMGR_WS=\|^ROOT=\|^PARENT_ROOT=\|^GATE=" "$FB"/illumos.sh
	mkdir -p "$RESULTS"
}

baseline() {
	local base=$1 joyent=$2 here
	[[ -n $base && -n $joyent ]] || die "baseline needs BASE and JOYENT"
	here=$(cd "$(dirname "$0")" && pwd)
	cd "$WS" || die "no $WS"
	git checkout -q -f -B baseline "$base" || die "checkout failed"
	"$here"/baseline.py "$WS" "$base" "$joyent" || die "baseline.py failed"
	git add -A usr || die "git add failed"
	git -c user.name=buildcheck -c user.email=buildcheck@localhost \
	    commit -q --allow-empty -m "baseline: gate plus build plumbing from baseline.txt" \
	    || die "commit failed"
	git log -1 --format='%h %s'
}

build() {
	local label=$1 out start end status
	[[ -n $label ]] || die "build needs a label"
	out=$RESULTS/$label
	rm -rf "$out"; mkdir -p "$out"
	cd "$WS" || die "no $WS"
	cp "$FB"/illumos.sh "$WS"/illumos.sh
	git -C "$WS" log -1 --format='%H %s' > "$out"/head
	git -C "$WS" status --porcelain --untracked-files=no > "$out"/dirty
	export PATH=/opt/onbld/bin:/sbin:/usr/sbin:/usr/bin:/usr/ccs/bin:/opt/SUNWspro/bin:/opt/local/bin
	export SHELL=/usr/bin/bash
	export BANNER_YEAR=$(TZ=UTC date +%Y)
	unset CC CXX
	mkdir -p log
	start=$(date +%s)
	export MAKE=/opt/local/bin/dmake
	./usr/src/tools/scripts/bldenv illumos.sh \
	    'cd $CODEMGR_WS/usr/src && export PATH="$PATH:/opt/local/bin" && \
	    dmake setup && cd tools && dmake install' > "$out"/setup.log 2>&1
	status=$?
	export -n MAKE
	if [[ $status -eq 0 ]]; then
		./usr/src/tools/scripts/nightly illumos.sh > "$out"/nightly.out 2>&1
		status=$?
	fi
	end=$(date +%s)
	local log=$(ls -1td log/log.* 2>/dev/null | head -1)
	[[ -n $log ]] && cp "$log"/mail_msg "$log"/nightly.log "$out"/ 2>/dev/null
	echo "status=$status seconds=$((end - start))" > "$out"/result
	cat "$out"/result
}

snapshot() {
	[[ -n $1 ]] || die "snapshot needs a name"
	zfs snapshot "$DATASET@$1" || die "zfs snapshot failed"
	echo "$DATASET@$1"
}

feature() {
	local name=$1 snap=${2:-gate-built} out
	[[ -n $name ]] || die "feature needs a name"
	out=$RESULTS/feature-$name
	zfs rollback -r "$DATASET@$snap" || die "rollback to $snap failed"
	cd "$WS" || die "no $WS"
	local pre=$(git rev-parse HEAD)
	git fetch -q "$SRCWS" "refs/heads/features/$name:refs/heads/features/$name" \
	    || die "no features/$name in $SRCWS"
	if ! git -c user.name=buildcheck -c user.email=buildcheck@localhost \
	    merge -q --no-edit "features/$name" > "$RESULTS/merge-$name.log" 2>&1; then
		rm -rf "$out"; mkdir -p "$out"
		mv "$RESULTS/merge-$name.log" "$out"/merge.log
		git merge --abort
		echo "status=merge-conflict seconds=0" > "$out"/result
		cat "$out"/result
		return
	fi
	rm -f "$RESULTS/merge-$name.log"
	# make sure dmake sees every changed file as new (the merge moved the
	# checked-out branch, so compare with the commit from before it)
	git diff --name-only -z --diff-filter=d "$pre" HEAD > "$RESULTS/touch-$name"
	[[ -s $RESULTS/touch-$name ]] && xargs -0 touch < "$RESULTS/touch-$name"
	tr '\0' '\n' < "$RESULTS/touch-$name" > "$RESULTS/touched-$name.txt"
	rm -f "$RESULTS/touch-$name"
	build "feature-$name"
	mv "$RESULTS/touched-$name.txt" "$RESULTS/feature-$name/touched.txt"
}

run() {
	local here name rest
	here=$(cd "$(dirname "$0")" && pwd)
	grep -v '^#' "$here"/buildcheck-order.txt | while read -r name rest; do
		[[ -n $name ]] || continue
		[[ -f $RESULTS/feature-$name/result ]] && continue
		echo "=== $name ($(date -u +%H:%M:%S))"
		( feature "$name" "$@" )
	done
	zfs rollback -r "$DATASET@${1:-gate-built}"
	echo "=== done ($(date -u +%H:%M:%S))"
}

summary() {
	local d r
	for d in "$RESULTS"/*/; do
		[[ -f $d/result ]] || continue
		r=$(cat "$d"/result)
		printf '%-32s %s  errors=%s warnings=%s\n' "$(basename "$d")" "$r" \
		    "$(sed -n '/Build errors (non-DEBUG)/,/Build warnings (non-DEBUG)/p' \
		    "$d"/mail_msg 2>/dev/null | grep -cv '^====\|^$')" \
		    "$(sed -n '/Build warnings (non-DEBUG)/,/Elapsed build time/p' \
		    "$d"/mail_msg 2>/dev/null | grep -cv '^====\|^$')"
	done
}

case $1 in
setup) setup ;;
baseline) shift; baseline "$@" ;;
build) shift; build "$@" ;;
snapshot) shift; snapshot "$@" ;;
feature) shift; feature "$@" ;;
run) shift; run "$@" ;;
summary) summary ;;
*) die "usage: buildcheck.sh setup | baseline BASE JOYENT | build LABEL |" \
    "snapshot NAME | feature NAME [SNAP] | run [SNAP] | summary" ;;
esac
