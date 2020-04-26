# vi: noet
DESTDIR = dest
PREFIX = /usr
SYSCONFDIR = etc

PYTHON = python3

.PHONY: all
all: libexec/af-req-root
	$(PYTHON) setup.py build

libexec/af-req-root: af-req-root.c
	$(CC) -static-pie -o $@ $< -lskarnet

.PHONY: install
install: all
	$(PYTHON) setup.py install \
		--root="$(DESTDIR)" \
		--prefix="$(PREFIX)"
	@echo
	@echo '*****************************************'
	@echo 'The following files should be installed'
	@echo 'to "$(DESTDIR)/$(SYSCONFDIR)/apkfoundry":'
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

.PHONY: clean
clean:
	rm -rf apkfoundry.egg-info build dest dist etc
	rm -f libexec/af-req-root

.PHONY: dist
dist: clean
	$(PYTHON) setup.py sdist
