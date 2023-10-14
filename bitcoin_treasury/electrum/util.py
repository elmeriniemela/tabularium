# Electrum - lightweight Bitcoin client
# Copyright (C) 2011 Thomas Voegtlin
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from typing import Any, Set, Optional
import secrets

bfh = bytes.fromhex
class BitcoinException(Exception): pass
class InvalidPassword(Exception):
    def __init__(self, message: Optional[str] = None):
        self.message = message

    def __str__(self):
        if self.message is None:
            return "Incorrect password"
        else:
            return str(self.message)
class WalletFileException(Exception):
    def __init__(self, message='', *, should_report_crash: bool = False):
        Exception.__init__(self, message)
        self.should_report_crash = should_report_crash

def assert_bytes(*args):
    """
    porting helper, assert args type
    """
    try:
        for x in args:
            assert isinstance(x, (bytes, bytearray))
    except Exception:
        print('assert bytes failed', list(map(type, args)))
        raise


def to_bytes(something, encoding='utf8') -> bytes:
    """
    cast string to bytes() like object, but for python2 support it's bytearray copy
    """
    if isinstance(something, bytes):
        return something
    if isinstance(something, str):
        return something.encode(encoding)
    elif isinstance(something, bytearray):
        return bytes(something)
    else:
        raise TypeError("Not a string or bytes like object")

def inv_dict(d):
    return {v: k for k, v in d.items()}


def is_hex_str(text: Any) -> bool:
    if not isinstance(text, str): return False
    try:
        b = bytes.fromhex(text)
    except Exception:
        return False
    # forbid whitespaces in text:
    if len(text) != 2 * len(b):
        return False
    return True


class classproperty(property):
    """~read-only class-level @property
    from https://stackoverflow.com/a/13624858 by denis-ryzhkov
    """
    def __get__(self, owner_self, owner_cls):
        return self.fget(owner_cls)

def all_subclasses(cls) -> Set:
    """Return all (transitive) subclasses of cls."""
    res = set(cls.__subclasses__())
    for sub in res.copy():
        res |= all_subclasses(sub)
    return res

def randrange(bound: int) -> int:
    """Return a random integer k such that 1 <= k < bound, uniformly
    distributed across that range.
    This is guaranteed to be cryptographically strong.
    """
    # secrets.randbelow(bound) returns a random int: 0 <= r < bound,
    # hence transformations:
    return secrets.randbelow(bound - 1) + 1

def to_string(x, enc) -> str:
    if isinstance(x, (bytes, bytearray)):
        return x.decode(enc)
    if isinstance(x, str):
        return x
    else:
        raise TypeError("Not a string or bytes like object")

def versiontuple(v):
    return tuple(map(int, (v.split("."))))