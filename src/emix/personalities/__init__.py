"""The personality registry.

Adding a personality means writing one module and listing it here.
"""

from __future__ import annotations

from emix.personalities.cms import CmsShell
from emix.personalities.cpm import CpmShell
from emix.personalities.vms import VmsShell
from emix.personalities.wopr import WoprShell
from emix.shell import Shell

#: Every personality Emix can start, keyed by its command-line name.
PERSONALITIES: dict[str, type[Shell]] = {
    personality.key: personality for personality in (CpmShell, VmsShell, CmsShell, WoprShell)
}

#: What each personality calls its drives, in mount order.
DRIVE_NAMES: dict[str, tuple[str, ...]] = {
    "cpm": tuple("ABCDEFGHIJKLMNOP"),
    "vms": ("DKA0", "DKA100", "DKA200", "DKB0"),
    "cms": tuple("ABCDEFGZ"),
    # Invented, like the machine. A defence computer would not have
    # called them drives.
    "wopr": ("PRIMARY", "SECONDARY", "TERTIARY", "ARCHIVE"),
}


def get(name: str) -> type[Shell]:
    try:
        return PERSONALITIES[name.lower()]
    except KeyError:
        raise SystemExit(
            f"emix: unknown personality {name!r}; choose from {', '.join(sorted(PERSONALITIES))}"
        ) from None


__all__ = [
    "DRIVE_NAMES",
    "PERSONALITIES",
    "CmsShell",
    "CpmShell",
    "VmsShell",
    "WoprShell",
    "get",
]
