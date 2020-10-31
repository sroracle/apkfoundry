#!/bin/sh -e
# vi:noet
. "$AF_LIBEXEC/af-functions"

"${0%/*}/refresh"

# If the hosts(5) and/or resolv.conf(5) are unmodified, apk will try to
# overwrite them even though they are read-only. So we work around it
# using symlinks.
ln -srf /af/config/host/hosts /etc/hosts
ln -srf /af/config/host/resolv.conf /etc/resolv.conf

ln -srf /usr/share/zoneinfo/UTC /etc/localtime

apk upgrade -Ual

af_mkuser
af_userconf

# Copy temporary public key to uploads directory
(
	. "$ABUILD_USERCONF"
	cp "$PACKAGER_PRIVKEY.pub" "$REPODEST"
)
