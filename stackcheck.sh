#!/usr/bin/bash
#
# stackcheck.sh: step A, stacked compile checks (see stack-plan-*.txt).
#
#   pass 1  stack-plan-1.txt: small cycles, from gate-built
#   pass 2  stack-plan-2.txt: the core cycle and its needs, as stack-core;
#           snapshot core-built if it builds
#   pass 3  stack-plan-3.txt: features needing the core, on core-built
#
# buildcheck.sh's stacks rolls back to gate-built when done, which
# destroys core-built; rebuilding it takes one pass-2 build.
#
here=$(cd "$(dirname "$0")" && pwd)
RESULTS=${RESULTS:-/workspace/fb-results}
"$here"/buildcheck.sh stacks "$here"/stack-plan-1.txt
if [[ ! -f $RESULTS/stack-core/result ]]; then
	echo "=== stack core ($(date -u +%H:%M:%S))"
	"$here"/buildcheck.sh stack -l core $(grep -v '^#' "$here"/stack-plan-2.txt)
	grep -q '^status=0' "$RESULTS"/stack-core/result &&
	    "$here"/buildcheck.sh snapshot core-built
fi
if grep -q '^status=0' "$RESULTS"/stack-core/result; then
	"$here"/buildcheck.sh stacks "$here"/stack-plan-3.txt
else
	echo "=== core failed; skipping pass 3"
fi
