# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2018-2020 Max Rees
# See LICENSE for more information.
import hashlib        # sha256
import logging        # getLogger
import mmap           # ACCESS_READ, mmap
import resource       # getpagesize
import shutil         # copyfileobj
import urllib.parse   # urlparse
import urllib.request # urlopen
from pathlib import Path

import apkfoundry # ROOTFS_CACHE

_LOGGER = logging.getLogger(__name__)
_PAGESZ = resource.getpagesize()

def _file_sha256(filename, old):
    with open(filename, "r") as f:
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            new = hashlib.sha256()
            chunk = mm.read(_PAGESZ)
            while chunk:
                new.update(chunk)
                chunk = mm.read(_PAGESZ)

    new = new.hexdigest()
    if old != new:
        _LOGGER.error("%s: sha256 does NOT match", filename.name)
        filename.unlink()
        return False

    _LOGGER.info("%s: OK", filename.name)
    return True

def _download_rootfs(url, filename):
    apkfoundry.ROOTFS_CACHE.mkdir(parents=True, exist_ok=True)
    _LOGGER.info("Downloading %s...", filename.name)
    with open(filename, "wb") as f:
        with urllib.request.urlopen(url) as response:
            shutil.copyfileobj(response, f)

def _get_rootfs(conf, arch):
    url = conf.get("rootfs." + arch, "").strip()
    sha256 = conf.get("sha256." + arch, "").strip()
    if not (url and sha256):
        _LOGGER.error("Missing rootfs/sha256 for arch %r", arch)
        return None

    url_parts = urllib.parse.urlparse(url)
    if url_parts.scheme not in ("http", "https", "ftp"):
        _LOGGER.error("Invalid URL scheme %r", url_parts.scheme)
        return None

    name = Path(url_parts.path).name
    if not name:
        _LOGGER.error("No name for URL %r", url)
        return None

    cached = apkfoundry.ROOTFS_CACHE / name
    if not cached.is_file():
        _download_rootfs(url, cached)

    if not _file_sha256(cached, sha256):
        return None

    return cached

def extract_rootfs(cont, conf):
    rootfs = _get_rootfs(conf, cont.arch)
    if not rootfs:
        return 1
    rootfs = Path("/tmp/af/rootfs-cache") / rootfs.relative_to(
        apkfoundry.ROOTFS_CACHE
    )

    exclusions = [("--exclude", i) for i in conf.getlist("rootfs-exclude", [])]
    exclusions = [j for i in exclusions for j in i]

    rc, _ = cont.run_external(
        # Relative to CWD = cdir
        ("tar", "-xf", rootfs, *exclusions),
    )
    if rc:
        return rc

    rc, _ = cont.run_external(
        # Relative to CWD = cdir
        ("chown", f"{cont._uid}:0", "."),
    )

    return rc
