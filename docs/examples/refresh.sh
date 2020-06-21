#!/bin/sh -e
# vi:noet
. "$AF_LIBEXEC/af-functions"

cp "$AF_BRANCHDIR/repositories.$AF_REPO" /etc/apk/repositories
cp "$AF_BRANCHDIR/world.$AF_REPO" /etc/apk/world
cp "$AF_BRANCHDIR/abuild.$AF_ARCH.conf" /etc/abuild.conf
