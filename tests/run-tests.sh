#!/bin/sh -e
# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2020 Max Rees
# See LICENSE for more information.
export PATH="$PWD/bin:$PATH"
export PYTHONPATH="$PWD:$PYTHONPATH"

export AF_TESTDIR="tests/tmp"
export AF_CONFIG="$AF_TESTDIR/config"
export AF_LOCAL="$AF_TESTDIR/local"
export AF_CACHE="$AF_TESTDIR/cache"
export AF_LOGLEVEL="DEBUG"

rm -rf "$AF_TESTDIR"
mkdir -p "$AF_TESTDIR"

while getopts nq opt; do
case "$opt" in
n) no_network=1;;
q) quiet=1;;
esac
done
shift "$((OPTIND - 1))"

if [ -n "$quiet" ]; then
	exec 3>"$AF_TESTDIR/log" 4>&3
else
	exec 3>&1 4>&2
fi

log() {
	printf "$@" >&2
	[ -z "$quiet" ] || printf "$@" >&4
}

failures=0
for test; do
	if ! [ -x "$test" ]; then
		log 'XXXX %s: no such test\n' "${test##*/}"
		failures="$((failures + 1))"
		continue
	fi
	case "$test" in
	*.net.test)
		if [ -n "$no_network" ]; then
			log 'SKIP %s\n' "${test##*/}"
			continue
		fi
		;;
	*.test)
		;;
	*)
		log 'XXXX %s: not a test\n' "${test##*/}"
		failures="$((failures + 1))"
		continue
		;;
	esac

	log 'TEST %s\n' "${test##*/}"
	if ! "$test" >&3 2>&4; then
		log 'FAIL %s\n' "${test##*/}"
		failures="$((failures + 1))"
	else
		log 'PASS %s\n' "${test##*/}"
	fi
done

if [ "$failures" -ne 0 ]; then
	cat >&2 <<-EOF

	Re-run failed tests:
	tests/run-tests.sh [-nq] tests/TEST1 [tests/TEST2 ...]

	Output is in tests/tmp/log
EOF
fi

exit "$failures"
