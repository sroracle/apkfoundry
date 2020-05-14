# vi: noet
DESTDIR = target
PREFIX = usr
SYSCONFDIR = etc/apkfoundry
LIBEXECDIR = $(PREFIX)/libexec/apkfoundry
DOCDIR = $(PREFIX)/share/doc/apkfoundry
LOCALSTATEDIR = var/lib/apkfoundry

export SYSCONFDIR LIBEXECDIR DOCDIR

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
	bin/af-rootd \
	libexec/gl-run

C_TARGETS = \
	libexec/af-req-root

.PHONY: all
all: libexec
	$(SETUP.PY) build

libexec/%: src/%.c
	$(CC) $(CFLAGS) -Wall -Wextra -fPIE -static-pie $(LDFLAGS) -o $@ $<

libexec: $(C_TARGETS)

.PHONY: install
install: all paths
	$(SETUP.PY) install \
		--root="$(DESTDIR)" \
		--prefix="/$(PREFIX)"
	chmod 750 "$(DESTDIR)/$(SYSCONFDIR)"
	-chgrp apkfoundry "$(DESTDIR)/$(SYSCONFDIR)"
	mkdir -p "$(DESTDIR)/$(LOCALSTATEDIR)"
	chmod 2770 "$(DESTDIR)/$(LOCALSTATEDIR)"
	-chown af-root:apkfoundry "$(DESTDIR)/$(LOCALSTATEDIR)"
	mkdir "$(DESTDIR)/$(LOCALSTATEDIR)/build"
	chmod 770 "$(DESTDIR)/$(LOCALSTATEDIR)/build"
	chmod g-s "$(DESTDIR)/$(LOCALSTATEDIR)/build"
	-chown af-root:apkfoundry "$(DESTDIR)/$(LOCALSTATEDIR)/build"
	@echo
	@echo '*****************************************'
	@echo 'The following files should be installed'
	@echo 'to "$(DESTDIR)/$(SYSCONFDIR)":'
	@echo '	bwrap.nosuid'
	@echo '	skel/etc/group'
	@echo '	skel/etc/hosts'
	@echo '	skel/etc/passwd'
	@echo '	skel/etc/resolv.conf'
	@echo '	skel:bootstrap/apk.static'
	@echo '	skel:bootstrap/etc/apk/ca.pem'
	@echo '	skel:bootstrap/etc/services'
	@echo
	@echo 'See the documentation for details.'
	@echo '*****************************************'
	@echo

.PHONY: paths
paths: apkfoundry/__init__.py
	sed -i \
		-e '/SYSCONFDIR = Path("/s@("[^"]*")@("/$(SYSCONFDIR)")@' \
		-e '/LIBEXECDIR = Path("/s@("[^"]*")@("/$(LIBEXECDIR)")@' \
		-e '/LOCALSTATEDIR = Path("/s@("[^"]*")@("/$(LOCALSTATEDIR)")@' \
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
	rm -rf MANIFEST apkfoundry.egg-info build dist etc target
	rm -f $(C_TARGETS)
