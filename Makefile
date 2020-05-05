# vi: noet
DESTDIR = target
PREFIX = usr
SYSCONFDIR = etc/apkfoundry
LIBEXECDIR = $(PREFIX)/libexec/apkfoundry
DOCDIR = $(PREFIX)/share/doc/apkfoundry
LOCALSTATEDIR = var/lib/apkfoundry

export SYSCONFDIR LIBEXECDIR DOCDIR

LIBS = -lskarnet
PYTHON = python3
PYLINT = pylint

LINT_TARGETS = \
	apkfoundry \
	bin/af-buildrepo \
	bin/af-chroot \
	bin/af-depgraph \
	bin/af-mkchroot \
	bin/af-rootd \
	libexec/gl-run

.PHONY: all
all: libexec/af-req-root
	$(PYTHON) setup.py build

libexec/af-req-root: af-req-root.c
	$(CC) $(CFLAGS) -static-pie $(LDFLAGS) -o $@ $< $(LIBS)

.PHONY: install
install: all paths
	$(PYTHON) setup.py install \
		--root="$(DESTDIR)" \
		--prefix="/$(PREFIX)"
	chmod 750 "$(DESTDIR)/$(SYSCONFDIR)"
	-chgrp apkfoundry "$(DESTDIR)/$(SYSCONFDIR)"
	mkdir -p "$(DESTDIR)/$(LOCALSTATEDIR)"
	chmod 2770 "$(DESTDIR)/$(LOCALSTATEDIR)"
	-chown af-root:apkfoundry "$(DESTDIR)/$(LOCALSTATEDIR)"
	@echo
	@echo '*****************************************'
	@echo 'The following files should be installed'
	@echo 'to "$(DESTDIR)/$(SYSCONFDIR)":'
	@echo '	bwrap.nosuid'
	@echo '	skel/etc/group'
	@echo '	skel/etc/hosts'
	@echo '	skel/etc/passwd'
	@echo '	skel/etc/resolv.conf'
	@echo '	skel.bootstrap/apk.static'
	@echo '	skel.bootstrap/etc/apk/ca.pem'
	@echo '	skel.bootstrap/etc/services'
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
	$(PYTHON) setup.py sdist

.PHONY: lint
lint: $(LINT_TARGETS)
	-$(PYLINT) $?

.PHONY: clean
clean:
	rm -rf apkfoundry.egg-info build dist etc target
	rm -f libexec/af-req-root
