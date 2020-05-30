# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019-2020 Max Rees
# See LICENSE for more information.
import enum         # Enum
import logging      # Formatter, getLogger, StreamHandler
import datetime     # datetime
import os           # environ, isatty
import sys          # stderr

class _Colors(enum.Enum):
    NORMAL = "\033[1;0m"
    STRONG = "\033[1;1m"
    CRITICAL = ERROR = RED = "\033[1;31m"
    INFO = GREEN = "\033[1;32m"
    WARNING = YELLOW = "\033[1;33m"
    DEBUG = BLUE = "\033[1;34m"
    MAGENTA = "\033[1;35m"

    def __str__(self):
        return self.value

class _AbuildLogFormatter(logging.Formatter):
    def __init__(self, color=True, sections=False, **kwargs):
        fmt = "%(levelcolor)s%(prettylevel)s%(normal)s%(message)s"
        super().__init__(fmt, **kwargs)

        self.color = color
        self.sections = sections

    def format(self, record):
        if self.color:
            try:
                record.levelcolor = _Colors[record.levelname]
                record.strong = _Colors.STRONG
                record.normal = _Colors.NORMAL
                record.magenta = _Colors.MAGENTA
            except KeyError:
                record.levelcolor = ""
                record.strong = ""
                record.normal = ""
                record.magenta = ""
        else:
            record.levelcolor = ""
            record.strong = ""
            record.normal = ""
            record.magenta = ""

        if self.sections:
            sectionfmt = "section_%s:%s:%s\r\033[0K"
        else:
            # Discard arguments
            sectionfmt = "%.0s%.0s%.0s"

        if record.levelname == "INFO":
            record.prettylevel = ">>> "
        elif record.levelno == 25:
            record.prettylevel = "\t"
        elif record.levelno in (26, 27):
            record.prettylevel = ""
            msg = record.msg
            record.msg = sectionfmt
            if msg.strip():
                record.msg += "\n" if record.levelno == 27 else ""
                record.msg += f"{_Colors.MAGENTA}{_Colors.STRONG}>>>"
                record.msg += f" {msg}{_Colors.NORMAL}"
        else:
            record.prettylevel = f">>> {record.levelname}: "

        return super().format(record)

def init(name=None, *, level=None, color=None, sections=False):
    if level is None:
        level = os.environ.get("AF_LOGLEVEL", "INFO")
    if color is None:
        color = os.isatty(sys.stderr.fileno())

    logger = logging.getLogger(name)
    logger.setLevel(level)
    handler = logging.StreamHandler()
    formatter = _AbuildLogFormatter(color=color, sections=sections)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger

def msg2(logger, s, *args, **kwargs):
    if not logger or isinstance(logger, str):
        logger = logging.getLogger(logger)
    if isinstance(s, str):
        logger.log(25, s, *args, **kwargs)
    else:
        for i in s:
            logger.log(25, i, *args, **kwargs)

_SECTIONS = []
def section_start(logger, name, *args, **kwargs):
    if not logger or isinstance(logger, str):
        logger = logging.getLogger(logger)

    ts = str(int(datetime.datetime.now().timestamp()))
    _SECTIONS.append((ts, name))

    logger.log(26, args[0], "start", ts, name, *args[1:], **kwargs)

def section_end(logger, *args, **kwargs):
    if not logger or isinstance(logger, str):
        logger = logging.getLogger(logger)

    if not args:
        args = [""]

    ts, name = _SECTIONS.pop()
    logger.log(27, args[0], "end", ts, name, *args[1:], **kwargs)
