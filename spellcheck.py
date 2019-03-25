# spellcheck.py
# Copyright (c) 2018-2019 Pablo Acosta-Serafini
# See LICENSE for details
# pylint: disable=C0111,C0325,C0411,E1101,E1123,E1129,R0205,R0903,R0912,R1718,W0611,W1113

# Standard library imports
from fnmatch import fnmatch
import os
import platform
import re
import sys

# PyPI imports
import hunspell
from pylint.interfaces import IRawChecker
from pylint.checkers import BaseChecker


# Literal copy from [...]/site-packages/pip/_vendor/compat.py
try:
    from shutil import which
except ImportError:  # pragma: no cover
    # Implementation from Python 3.3
    def which(cmd, mode=os.F_OK | os.X_OK, path=None):
        """Mimic CLI which function, copied from Python 3.3 implementation."""
        # pylint: disable=C0103,C0113,W0622
        # Check that a given file can be accessed with the correct mode.
        # Additionally check that `file` is not a directory, as on Windows
        # directories pass the os.access check.
        def _access_check(fn, mode):
            return os.path.exists(fn) and os.access(fn, mode) and not os.path.isdir(fn)

        # If we're given a path with a directory part, look it up directly rather
        # than referring to PATH directories. This includes checking relative to the
        # current directory, e.g. ./script
        if os.path.dirname(cmd):
            if _access_check(cmd, mode):
                return cmd
            return None

        if path is None:
            path = os.environ.get("PATH", os.defpath)
        if not path:
            return None
        path = path.split(os.pathsep)

        if sys.platform == "win32":
            # The current directory takes precedence on Windows.
            if not os.curdir in path:
                path.insert(0, os.curdir)

            # PATHEXT is necessary to check on Windows.
            pathext = os.environ.get("PATHEXT", "").split(os.pathsep)
            # See if the given file matches any of the expected path extensions.
            # This will allow us to short circuit when given "python.exe".
            # If it does match, only test that one, otherwise we have to try
            # others.
            if any(cmd.lower().endswith(ext.lower()) for ext in pathext):
                files = [cmd]
            else:
                files = [cmd + ext for ext in pathext]
        else:
            # On other platforms you don't have things like PATHEXT to tell you
            # what file suffixes are executable, so just pass on cmd as-is.
            files = [cmd]

        seen = set()
        for dir in path:
            normdir = os.path.normcase(dir)
            if not normdir in seen:
                seen.add(normdir)
                for thefile in files:
                    name = os.path.join(dir, thefile)
                    if _access_check(name, mode):
                        return name
        return None


###
# Global variables
###
IS_PY3 = sys.hexversion > 0x03000000
REF_WHITELIST = os.path.join("data", "whitelist.en.pws")
REF_EXCLUDE = os.path.join("data", "exclude-spelling")


###
# Functions
###
def _find_ref_fname(fname, ref_fname):
    """
    Find reference file.

    Start one directory above where current script is located
    """
    curr_dir = ""
    next_dir = os.path.dirname(os.path.dirname(os.path.abspath(fname)))
    while next_dir != curr_dir:
        curr_dir = next_dir
        rcfile = os.path.join(curr_dir, ref_fname)
        if os.path.exists(rcfile):
            return rcfile
        next_dir = os.path.dirname(curr_dir)
    return ""


def _make_abspath(value):
    """Homogenize files to have absolute paths."""
    value = value.strip()
    if not os.path.isabs(value):
        value = os.path.abspath(os.path.join(os.getcwd(), value))
    return value


def _read_file(fname):
    """Return file lines as strings."""
    with open(fname) as fobj:
        for line in fobj:
            yield _tostr(line).strip()


def _tostr(obj):  # pragma: no cover
    """Convert to string if necessary."""
    return obj if isinstance(obj, str) else (obj.decode() if IS_PY3 else obj.encode())


def check_spelling(fname, whitelist_fname="", exclude_fname=""):
    """Check spelling against whitelist."""
    # pylint: disable=R0914
    fname = os.path.abspath(fname)
    whitelist_fname = whitelist_fname.strip() or _find_ref_fname(fname, REF_WHITELIST)
    exclude_fname = exclude_fname.strip() or _find_ref_fname(fname, REF_EXCLUDE)
    if whitelist_fname:
        whitelist_fname = os.path.abspath(whitelist_fname)
        whitelist = []
        if not os.path.exists(whitelist_fname):
            print("WARNING: Whitelist file {0} not found".format(whitelist_fname))
        else:
            with open(whitelist_fname, "r") as fobj:
                whitelist = [item.strip() for item in fobj]
            # print("Using {0}".format(whitelist_fname))
    if exclude_fname:
        exclude_fname = os.path.abspath(exclude_fname)
        if not os.path.exists(exclude_fname):
            print("WARNING: exclude file {0} not found".format(exclude_fname))
        # print("Using {0}".format(exclude_fname))
    if os.path.exists(exclude_fname):
        patterns = [_make_abspath(item) for item in _read_file(exclude_fname)]
        if any(fnmatch(fname, pattern) for pattern in patterns):
            return []
    spell_obj = hunspell.Hunspell("en_US")
    ret = []
    with open(fname, "r") as fobj:
        for num, line in enumerate(fobj):
            line = line.strip()
            for word in re.split("[^a-zA-Z]", line):
                if (not spell_obj.spell(word)) and (word not in whitelist):
                    ret.append((num + 1, (word,)))
    return ret


###
# Classes
###
class SpellChecker(BaseChecker):
    """Check for spelling."""

    __implements__ = IRawChecker

    MISSPELLED_WORD = "spellchecker"

    name = "spellchecker"
    msgs = {"W9904": ("Misspelled word %s", MISSPELLED_WORD, "Misspelled word")}

    options = (
        (
            "whitelist",
            {
                "default": "",
                "type": "string",
                "metavar": "<whitelist>",
                "help": "Whitelist",
            },
        ),
        (
            "exclude",
            {
                "default": "",
                "type": "string",
                "metavar": "<exclude file>",
                "help": "File with patterns used to exclude files from spell checking",
            },
        ),
    )

    def process_module(self, node):
        """Process a module. Content is accessible via node.stream() function."""
        if which("hunspell"):
            sdir = os.path.dirname(os.path.abspath(__file__))
            whitelist_fname = _tostr(self.config.whitelist)
            exclude_fname = _tostr(self.config.exclude)
            if whitelist_fname:
                whitelist_fname = os.path.abspath(os.path.join(sdir, whitelist_fname))
            if exclude_fname:
                exclude_fname = os.path.abspath(os.path.join(sdir, exclude_fname))
            for line, args in check_spelling(
                node.file, whitelist_fname=whitelist_fname, exclude_fname=exclude_fname
            ):
                self.add_message(self.MISSPELLED_WORD, line=line, args=args)
        else:
            print("hunspell binary not found, skipping")


def register(linter):
    """Register checker."""
    linter.register_checker(SpellChecker(linter))


def main():
    """Script entry point for testing."""
    fname = sys.argv[1]
    whitelist_fname = sys.argv[2] if len(sys.argv) >= 3 else ""
    exclude_fname = sys.argv[3] if len(sys.argv) >= 4 else ""
    out = check_spelling(
        fname, whitelist_fname=whitelist_fname, exclude_fname=exclude_fname
    )
    print(out)


if __name__ == "__main__":
    main()
