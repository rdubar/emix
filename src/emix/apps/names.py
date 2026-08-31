"""Reversible 8.3 aliases for host names a historical filesystem cannot hold.

CP/M has eight characters, a dot, and three more. Modern host names do not.
The rule that matters is not "shorten the name" but **"shorten it so exactly
one host file comes back"**, which is why every alias produced here is
recorded in the session manifest rather than recomputed on the way home.

The mapping is deliberately *not* injective on its own: ``Meeting notes.txt``
and ``meeting-notes.txt`` both want ``MEETIN~1.TXT``. Collisions are resolved
against the names already handed out, so the manifest is the only authority
on which host file an alias refers to.
"""

from __future__ import annotations

from collections.abc import Iterable

#: Characters CP/M accepts in a filename. Everything else folds to ``_``.
_SAFE = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789$_-")

#: How many collision suffixes to try before giving up.
_MAX_COLLISIONS = 999

#: Character introducing a collision suffix.
#:
#: DOS used ``~``, and so does everyone's mental image of an 8.3 alias. Real
#: CP/M applications disagree: the CCP parses ``MEETIN~1.TXT`` correctly, but
#: TE rejects both ``~`` and ``-`` when it re-parses the command tail itself.
#: ``_`` is accepted everywhere tested, so it is the default, and the profile
#: can override it for an application that wants something else.
DEFAULT_SUFFIX = "_"


def _fold(text: str, limit: int) -> str:
    """Upper-case ``text``, replace what CP/M forbids, and truncate."""
    folded = "".join(character if character in _SAFE else "_" for character in text.upper())
    return folded[:limit]


def split_host_name(name: str) -> tuple[str, str]:
    """Split a host name into stem and extension, without the dot.

    A leading dot is part of the stem: ``.profile`` is a stem, not an
    extension, because that is how the host means it.
    """
    stem, dot, extension = name.rpartition(".")
    if not dot or not stem:
        return name, ""
    return stem, extension


def to_alias(name: str, taken: Iterable[str] = (), suffix: str = DEFAULT_SUFFIX) -> str:
    """Return an 8.3 guest name for ``name`` that is not already ``taken``.

    Names that already fit are only case-folded, so ``NOTES.TXT`` survives
    intact and the common case stays recognisable.
    """
    claimed = {existing.upper() for existing in taken}
    stem, extension = split_host_name(name)
    short_stem = _fold(stem, 8)
    short_extension = _fold(extension, 3)

    def assemble(base: str) -> str:
        return f"{base}.{short_extension}" if short_extension else base

    # Folding ``+`` to ``_`` loses a character but not a *length*, and the
    # manifest still maps the result back to one host file. Truncation is the
    # case that must announce itself, because ``PYPROJEC.TOM`` looks like a
    # real name and is not one.
    truncated = len(stem) > 8 or len(extension) > 3
    if not truncated and assemble(short_stem) not in claimed:
        return assemble(short_stem)

    for ordinal in range(1, _MAX_COLLISIONS + 1):
        marker = f"{suffix}{ordinal}"
        candidate = assemble(short_stem[: 8 - len(marker)] + marker)
        if candidate not in claimed:
            return candidate
    raise ValueError(f"no free 8.3 alias for {name!r}")


class AliasMap:
    """Stable, reversible 8.3 names for one directory listing.

    A listing that prints ``PYPROJEC.TOM`` names a file you cannot type back,
    which the roadmap calls authentic and useless. A listing that prints
    ``PYPROJ_1.TOM`` and *accepts it back* is the useful version, and the only
    thing that makes it safe is that the mapping is built from the whole
    listing at once: aliases are assigned in a fixed order, so the same
    directory always produces the same names within a session.

    The host file is never renamed. This is a presentation layer.
    """

    def __init__(self, names: Iterable[str], suffix: str = DEFAULT_SUFFIX) -> None:
        self._to_guest: dict[str, str] = {}
        self._to_host: dict[str, str] = {}
        # Sorted, so the ordinal a name receives does not depend on the order
        # the filesystem happened to yield.
        for name in sorted(names, key=str.casefold):
            guest = to_alias(name, self._to_host, suffix)
            self._to_guest[name] = guest
            self._to_host[guest.upper()] = name

    def alias(self, host_name: str) -> str:
        """The 8.3 name for a host file, or the host name if it has none."""
        return self._to_guest.get(host_name, host_name)

    def host(self, guest_name: str) -> str | None:
        """The host file an 8.3 name refers to, or ``None``."""
        return self._to_host.get(guest_name.upper())

    def __len__(self) -> int:
        return len(self._to_guest)
