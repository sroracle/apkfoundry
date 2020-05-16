#!/bin/sh -e
# Disable colors if logging to a separate file (see below)
#export USE_COLORS=

. /usr/share/abuild/functions.sh
cd "$APORTSDIR/$1"
repo="${1%/*}"

echo "${STRONG}>>> Upgrading container${NORMAL}"
$SUDO_APK upgrade --available --latest

echo "${STRONG}>>> Adding extra dependencies${NORMAL}"
case "$1" in
# configure: error: GNAT is required to build ada
system/gcc) $SUDO_APK add -t .makedepends-gcc-self gcc-gnat;;
esac

echo "${STRONG}>>> abuild -r${NORMAL}"
# Log all builds to the master job log
abuild -r

# Or, log each build to a separate file: (make sure to update
# .gitlab-ci.yml to upload these!)
#
#(
#	. ./APKBUILD
#	logdir="$REPODEST/$repo/$CARCH/logs"
#	mkdir -p "$logdir"
#	rm -f /af/build/log
#	ln -s "$logdir/$pkgname-$pkgver-r$pkgrel.log" /af/build/log
#)
#abuild -r > /af/build/log 2>&1

echo "${STRONG}>>> checkapk${NORMAL}"
/af/libexec/checkapk
#/af/libexec/checkapk >> /af/build/log 2>&1
