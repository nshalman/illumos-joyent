#!/usr/bin/bash
#
# buildcheck.sh: compile-check trees on an illumos build host inside a
# smartos-live workspace, without touching smartos-live's own build.
#
#   buildcheck.sh setup           create the $FB dataset and an illumos
#                                 clone in it, with its own illumos.sh
#   buildcheck.sh build LABEL     build the clone's current checkout the
#                                 way tools/build_illumos does; results go
#                                 to $RESULTS/LABEL
#
# The illumos.sh is smartos-live's, except that the workspace is $FB's
# clone and ROOT/PARENT_ROOT are that clone's own proto area: smartos-live's
# shared proto holds illumos-joyent headers and libraries that would hide
# missing dependencies.  The toolchain (proto.strap) is shared.
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
	    "$SRCWS"/illumos.sh > "$FB"/illumos.sh
	grep -n "^CODEMGR_WS=\|^ROOT=\|^PARENT_ROOT=\|^GATE=" "$FB"/illumos.sh
	mkdir -p "$RESULTS"
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

case $1 in
setup) setup ;;
build) shift; build "$@" ;;
*) die "usage: buildcheck.sh setup | build LABEL" ;;
esac
