# vi: noet
DESTDIR = target
PREFIX = usr
DOCDIR = $(PREFIX)/share/doc/apkfoundry
LIBEXECDIR = $(PREFIX)/libexec/apkfoundry
LOCALSTATEDIR = var/lib/apkfoundry
SYSCONFDIR = etc/apkfoundry
export DOCDIR LIBEXECDIR SYSCONFDIR

BWRAP = bwrap.nosuid
DEFAULT_ARCH = $(shell apk --print-arch)

PYTHON = python3
PYLINT = pylint
SETUP.PY = $(PYTHON) src/setup.py

LINT_TARGETS = \
	apkfoundry \
	bin/af-buildrepo \
	bin/af-chroot \
	bin/af-depgraph \
	bin/af-mkchroot \
	bin/af-rmchroot \
	libexec/gl-run

C_TARGETS = \
	libexec/af-req-root \
	libexec/af-su

.PHONY: all
all: libexec
	$(SETUP.PY) build

libexec/%: src/%.c
	$(CC) $(CFLAGS) -Wall -Wextra -fPIE -static-pie $(LDFLAGS) -o $@ $<

libexec: $(C_TARGETS)

.PHONY: install
install: all configure
	$(SETUP.PY) install \
		--root="$(DESTDIR)" \
		--prefix="/$(PREFIX)"
	chmod 2755 "$(DESTDIR)/$(SYSCONFDIR)"
	-chgrp apkfoundry "$(DESTDIR)/$(SYSCONFDIR)"
	mkdir -p "$(DESTDIR)/$(LOCALSTATEDIR)"
	chmod 2770 "$(DESTDIR)/$(LOCALSTATEDIR)"
	-chgrp apkfoundry "$(DESTDIR)/$(LOCALSTATEDIR)"
	mkdir "$(DESTDIR)/$(LOCALSTATEDIR)/build"
	chmod 770 "$(DESTDIR)/$(LOCALSTATEDIR)/build"
	-chgrp apkfoundry "$(DESTDIR)/$(LOCALSTATEDIR)/build"
	mkdir "$(DESTDIR)/$(LOCALSTATEDIR)/apk-cache"
	chmod 775 "$(DESTDIR)/$(LOCALSTATEDIR)/apk-cache"
	-chgrp apkfoundry "$(DESTDIR)/$(LOCALSTATEDIR)/apk-cache"
	mkdir "$(DESTDIR)/$(LOCALSTATEDIR)/rootfs-cache"
	chmod 775 "$(DESTDIR)/$(LOCALSTATEDIR)/rootfs-cache"
	-chgrp apkfoundry "$(DESTDIR)/$(LOCALSTATEDIR)/rootfs-cache"
	mkdir "$(DESTDIR)/$(LOCALSTATEDIR)/src-cache"
	chmod 775 "$(DESTDIR)/$(LOCALSTATEDIR)/src-cache"
	-chgrp apkfoundry "$(DESTDIR)/$(LOCALSTATEDIR)/src-cache"

.PHONY: configure
configure: apkfoundry/__init__.py
	sed -i \
		-e '/^BWRAP = /s@= .*@= "$(BWRAP)"@' \
		-e '/^DEFAULT_ARCH = /s@= .*@= "$(DEFAULT_ARCH)"@' \
		-e '/^LIBEXECDIR = /s@= .*@= "/$(LIBEXECDIR)"@' \
		-e '/^LOCALSTATEDIR = /s@= .*@= "/$(LOCALSTATEDIR)"@' \
		-e '/^SYSCONFDIR = /s@= .*@= "/$(SYSCONFDIR)"@' \
		apkfoundry/__init__.py

.PHONY: dist
dist: clean
	$(SETUP.PY) sdist -u root -g root -t src/MANIFEST.in

.PHONY: setup
setup:
	@$(SETUP.PY) $(SETUP_ARGS)

.PHONY: lint
lint: $(LINT_TARGETS)
	-$(PYLINT) --rcfile src/pylintrc $?

.PHONY: clean
clean:
	rm -rf MANIFEST apkfoundry.egg-info build dist target
	rm -f $(C_TARGETS)
