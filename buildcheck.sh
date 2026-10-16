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
#   buildcheck.sh stack [-s SNAP] [-l LABEL] NAME PROVIDER...
#                                 like feature, merging the providers'
#                                 branches too; builds as stack-LABEL
#                                 (default stack-NAME)
#   buildcheck.sh stacks PLAN     build every line "NAME PROVIDER..." of PLAN
#                                 (stackplan.py) that has no result yet
#   buildcheck.sh summary         one line per result in $RESULTS
#
# The illumos.sh is smartos-live's, except that the workspace is $FB's
# clone and ROOT/PARENT_ROOT are that clone's own proto area: smartos-live's
# shared proto holds illumos-joyent headers and libraries that would hide
# missing dependencies.  The toolchain (proto.strap) is shared.  It also
# drops nightly's -m: with postfix disabled, every mailed report leaves a
# sendmail/postdrop pair hanging.  Like smartos-live, build writes the
# proto area's buildstamp.
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
	# smartos-live's Makefile writes $(ROOT)/buildstamp before building
	# illumos, and SmartOS's cmd/Adm reads it
	mkdir -p "$WS"/proto/root_i386
	[[ -f $WS/proto/root_i386/buildstamp ]] ||
	    TZ=UTC date +%Y%m%dT%H%M%SZ > "$WS"/proto/root_i386/buildstamp
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
	local name=$1 snap=${2:-gate-built}
	[[ -n $name ]] || die "feature needs a name"
	merge_build "feature-$name" "$snap" "$name"
}

# merge_build LABEL SNAP NAME...: roll back to SNAP, merge features/NAME...
# from $SRCWS, touch every file the merge changes, and build as LABEL
merge_build() {
	local label=$1 snap=$2 out n
	shift 2
	out=$RESULTS/$label
	zfs rollback -r "$DATASET@$snap" || die "rollback to $snap failed"
	cd "$WS" || die "no $WS"
	local pre=$(git rev-parse HEAD)
	local refs=()
	for n in "$@"; do
		git fetch -q "$SRCWS" "refs/heads/features/$n:refs/heads/features/$n" \
		    || die "no features/$n in $SRCWS"
		refs+=("features/$n")
	done
	if ! git -c user.name=buildcheck -c user.email=buildcheck@localhost \
	    merge -q --no-edit "${refs[@]}" > "$RESULTS/merge-$label.log" 2>&1; then
		rm -rf "$out"; mkdir -p "$out"
		mv "$RESULTS/merge-$label.log" "$out"/merge.log
		git merge --abort
		echo "status=merge-conflict seconds=0" > "$out"/result
		cat "$out"/result
		return
	fi
	rm -f "$RESULTS/merge-$label.log"
	# make sure dmake sees every changed file as new (the merge moved the
	# checked-out branch, so compare with the commit from before it)
	git diff --name-only -z --diff-filter=d "$pre" HEAD > "$RESULTS/touch-$label"
	[[ -s $RESULTS/touch-$label ]] && xargs -0 touch < "$RESULTS/touch-$label"
	tr '\0' '\n' < "$RESULTS/touch-$label" > "$RESULTS/touched-$label.txt"
	rm -f "$RESULTS/touch-$label"
	build "$label"
	mv "$RESULTS/touched-$label.txt" "$out"/touched.txt
}

stack() {
	local snap=gate-built label= args=()
	while (( $# )); do
		case $1 in
		-s) snap=$2; shift 2 ;;
		-l) label=$2; shift 2 ;;
		*) args+=("$1"); shift ;;
		esac
	done
	(( ${#args[@]} )) || die "stack needs a name"
	merge_build "stack-${label:-${args[0]}}" "$snap" "${args[@]}"
}

stacks() {
	local plan=$1 name rest
	[[ -f $plan ]] || die "no plan $plan"
	grep -v '^#' "$plan" | while read -r name rest; do
		[[ -n $name ]] || continue
		[[ -f $RESULTS/stack-$name/result ]] && continue
		echo "=== stack $name ($(date -u +%H:%M:%S))"
		( stack "$name" $rest )
	done
	zfs rollback -r "$DATASET@gate-built"
	echo "=== done ($(date -u +%H:%M:%S))"
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
	# errors/warnings: nightly's build sections; checks: lines in its
	# cstyle/hdrchk section (e.g. runfiles naming tests that are absent);
	# stage: where a failure happened (setup = dmake setup/tools)
	local d r m stage
	for d in "$RESULTS"/*/; do
		[[ -f $d/result ]] || continue
		r=$(cat "$d"/result)
		m=$d/mail_msg
		if [[ ! -f $d/nightly.out ]]; then
			stage=setup
		elif [[ $r == status=0* ]]; then
			stage=-
		else
			stage=nightly
		fi
		printf '%-30s %-32s errors=%-3s warnings=%-3s checks=%-3s stage=%s\n' \
		    "$(basename "$d")" "$r" \
		    "$(sed -n '/Build errors (non-DEBUG)/,/Build warnings (non-DEBUG)/p' \
		    "$m" 2>/dev/null | grep -cv '^====\|^$')" \
		    "$(sed -n '/Build warnings (non-DEBUG)/,/Elapsed build time/p' \
		    "$m" 2>/dev/null | grep -cv '^====\|^$')" \
		    "$(sed -n '/cstyle\/hdrchk errors/,/Find core files/p' \
		    "$m" 2>/dev/null | grep -cv '^====\|^$')" "$stage"
	done
}

case $1 in
setup) setup ;;
baseline) shift; baseline "$@" ;;
build) shift; build "$@" ;;
snapshot) shift; snapshot "$@" ;;
feature) shift; feature "$@" ;;
run) shift; run "$@" ;;
stack) shift; stack "$@" ;;
stacks) shift; stacks "$@" ;;
summary) summary ;;
*) die "usage: buildcheck.sh setup | baseline BASE JOYENT | build LABEL |" \
    "snapshot NAME | feature NAME [SNAP] | run [SNAP] | summary" ;;
esac
