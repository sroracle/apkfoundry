# vi: noet
DESTDIR = target
PREFIX = usr
DOCDIR = $(PREFIX)/share/doc/apkfoundry
LIBEXECDIR = $(PREFIX)/libexec/apkfoundry
export DOCDIR LIBEXECDIR

BWRAP = bwrap.nosuid
DEFAULT_ARCH = $(shell apk --print-arch)

PYTHON = python3
PYLINT = pylint
CHECKBASHISMS = checkbashisms
SETUP.PY = $(PYTHON) src/setup.py

C_TARGETS = \
	libexec/af-su \
	libexec/af-sudo

TEST_ARGS = -q
TEST_TARGETS = \
	tests/*.test

CLEAN_TARGETS = \
	$(C_TARGETS) \
	MANIFEST \
	apkfoundry.egg-info \
	build \
	dist \
	target \
	tests/tmp \
	var

PYLINT_TARGETS = \
	apkfoundry \
	bin/af-buildrepo \
	bin/af-chroot \
	bin/af-depgraph \
	bin/af-mkchroot \
	bin/af-rmchroot \
	libexec/gl-config \
	libexec/gl-run

SHLINT_TARGETS = \
	docs/build \
	bin/af-mkuidmap \
	bin/af-mkgidmap \
	libexec/af-deps \
	libexec/resignapk \
	libexec/checkapk \
	libexec/af-functions \
	libexec/gl-cleanup \
	tests/run-tests.sh \
	tests/af-rmchroot.test

.PHONY: all
all: libexec
	$(SETUP.PY) build

libexec/%: src/%.c
	$(CC) $(CFLAGS) -Wall -Wextra -fPIE $(LDFLAGS) -static-pie -o $@ $<

libexec: $(C_TARGETS)

.PHONY: configure
configure:
	@printf 'CONF: BWRAP = "%s"\n' '$(BWRAP)'
	@printf 'CONF: DEFAULT_ARCH = "%s"\n' '$(DEFAULT_ARCH)'
	@sed -i \
		-e '/^BWRAP = /s@= .*@= "$(BWRAP)"@' \
		-e '/^DEFAULT_ARCH = /s@= .*@= "$(DEFAULT_ARCH)"@' \
		apkfoundry/__init__.py

.PHONY: quickstart
quickstart: configure libexec

.PHONY: check
check: quickstart
	@tests/run-tests.sh $(TEST_ARGS) $(TEST_TARGETS)

.PHONY: paths
paths: configure
	@printf 'PATH: LIBEXECDIR = "%s"\n' '$(LIBEXECDIR)'
	@sed -i \
		-e '/^LIBEXECDIR = /s@= .*@= Path("/$(LIBEXECDIR)")@' \
		apkfoundry/__init__.py

.PHONY: install
install: paths all
	$(SETUP.PY) install \
		--root="$(DESTDIR)" \
		--prefix="/$(PREFIX)"

.PHONY: clean
clean:
	rm -rf $(CLEAN_TARGETS)

.PHONY: dist
dist: clean
	$(SETUP.PY) sdist -u root -g root -t src/MANIFEST.in

.PHONY: pylint
pylint:
	-$(PYLINT) --rcfile src/pylintrc $(PYLINT_TARGETS)

.PHONY: rstlint
rstlint:
	@grep -ho '[<][^>]*[>]' *.rst docs/*.rst \
		| tr -d '<>' | grep -v http \
		| while read -r i; do [ -e "$$i" ] \
		|| echo "RST: link '$$i' does not exist"; done

.PHONY: shlint
shlint:
	-$(CHECKBASHISMS) -px $(SHLINT_TARGETS)

.PHONY: lint
lint: pylint shlint rstlint

.PHONY: setup
setup:
	@$(SETUP.PY) $(SETUP_ARGS)
