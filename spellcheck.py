# spellcheck.py
# Copyright (c) 2018-2019 Pablo Acosta-Serafini
# See LICENSE for details
# pylint: disable=C0111,C0411,E1129,R0205,R1718,W1113

# Standard library imports
import collections
import decorator
import io
import os
import platform
import re
from subprocess import Popen, PIPE
import sys
import tempfile
import types

# Literal copy from [...]/site-packages/pip/_vendor/compat.py
try:
    from shutil import which
except ImportError:  # pragma: no cover
    # Implementation from Python 3.3
    def which(cmd, mode=os.F_OK | os.X_OK, path=None):
        """Mimic CLI which function, copied from Python 3.3 implementation."""
        # pylint: disable=C0103,C0113,R0912,W0622
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


# PyPI imports
from pylint.interfaces import IRawChecker
from pylint.checkers import BaseChecker


###
# Global variables
###
IS_PY3 = sys.hexversion > 0x03000000


###
# Functions
###
@decorator.contextmanager
def ignored(*exceptions):
    try:
        yield
    except exceptions:
        pass


class TmpFile(object):
    """
    Use a temporary file within context.

    From pmisc package
    """

    def __init__(self, fpointer=None, *args, **kwargs):  # noqa
        if (
            fpointer
            and (not isinstance(fpointer, types.FunctionType))
            and (not isinstance(fpointer, types.LambdaType))
        ):
            raise RuntimeError("Argument `fpointer` is not valid")
        self._fname = None
        self._fpointer = fpointer
        self._args = args
        self._kwargs = kwargs

    def __enter__(self):  # noqa
        fdesc, fname = tempfile.mkstemp()
        # fdesc is an OS-level file descriptor, see problems if this
        # is not properly closed in this post:
        # https://www.logilab.org/blogentry/17873
        os.close(fdesc)
        if platform.system().lower() == "windows":  # pragma: no cover
            fname = fname.replace(os.sep, "/")
        self._fname = fname
        if self._fpointer:
            with open(self._fname, "w") as fobj:
                self._fpointer(fobj, *self._args, **self._kwargs)
        return self._fname

    def __exit__(self, exc_type, exc_value, exc_tb):  # noqa
        with ignored(OSError):
            os.remove(self._fname)
        return not exc_type is not None


def _grep(fname, words):
    """Return line numbers in which words appear in a file."""
    # pylint: disable=W0631
    pat = "(.*[^a-zA-Z]|^){}([^a-zA-Z].*|$)"
    regexps = [(word, re.compile(pat.format(word))) for word in words]
    ldict = collections.defaultdict(list)
    for num, line in enumerate(_read_file(fname)):
        for word in [word for word, regexp in regexps if regexp.match(line)]:
            ldict[word].append(num + 1)
    return ldict


def _read_file(fname):
    """Return file lines as strings."""
    with open(fname) as fobj:
        for line in fobj:
            yield _tostr(line).strip()


def _tostr(obj):  # pragma: no cover
    """Convert to string if necessary."""
    return obj if isinstance(obj, str) else (obj.decode() if IS_PY3 else obj.encode())


def check_spelling(node):
    """Check spelling against whitelist."""
    # pylint: disable=R0914
    regexp = re.compile(r"(?:[^a-zA-Z]*|^)*([a-zA-Z]+)(?:[^a-zA-Z]*|$)*")
    fname = os.path.abspath(node.file)
    sdir = os.path.dirname(os.path.abspath(__file__))
    pdict = os.path.join(os.path.dirname(sdir), "data", "whitelist.en.pws")
    ret = []
    if which("hunspell"):
        cmd = ["hunspell", "-p", pdict, "-l", fname]
        obj = Popen(cmd, stdout=PIPE, stderr=PIPE)
        stdout = _tostr(obj.communicate()[0]).split(os.linesep)
        # hunspell has trouble with apostrophes and other delimiters out-of-the-box
        words = []
        for word in [word for word in stdout if word.strip()]:
            match = regexp.match(word)
            if match:
                words.append(match.groups()[0])
        words = sorted(list(set(words)))
        func = lambda x: x.write(os.linesep.join(words))
        with TmpFile(func) as temp_fname:
            cmd = ["hunspell", "-p", pdict, "-l", temp_fname]
            with io.open(temp_fname) as fobj:
                obj = Popen(cmd, stdin=fobj, stdout=PIPE, stderr=PIPE)
                stdout = _tostr(obj.communicate()[0]).split(os.linesep)
        words = sorted(list(set([word.strip() for word in stdout if word.strip()])))
        if words:
            ldict = _grep(fname, words)
            for word, lines in [(word, ldict[word]) for word in words]:
                for lnum in lines:
                    ret.append((lnum, (word,)))
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
    options = ()

    def process_module(self, node):
        """Process a module. Content is accessible via node.stream() function."""
        for line, args in check_spelling(node):
            self.add_message(self.MISSPELLED_WORD, line=line, args=args)


def register(linter):
    """Register checker."""
    linter.register_checker(SpellChecker(linter))
