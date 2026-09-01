"""Asking a language model to answer in character, for the one place it fits.

Emix's assistance layer is deliberately deterministic: a hint is a table
lookup, and nothing is executed on a guess. A model that improvised at a CP/M
prompt would break the only thing the personalities are for — if Emix invents a
plausible-looking `%DCL-W-` code, the user has been taught something false.

WOPR is the exception, and the reason is not that the rules are relaxed there.
It is that WOPR is fictional, so there is no historical record to falsify, and
sandboxed, so there is nothing to act on. A model here can only ever talk. The
guarantee is structural rather than careful: this module returns a string, and
the caller writes it to the screen. There is no path from here to a file, a
verb, or a host command.

Optional in every sense. Without the ``anthropic`` package, without a key, or
with the user simply not asking, WOPR plays exactly as it does today.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # `anthropic` is an optional dependency, so only the checker
    from anthropic.types import MessageParam  # imports it unconditionally.

#: The model to answer as WOPR. Deliberately not configurable yet: one moving
#: part is enough until somebody asks for a second.
MODEL = "claude-opus-5"

#: Emix's own name for a key, checked before the SDK's.
#:
#: ``ANTHROPIC_API_KEY`` is not Emix's variable to occupy. Other tools read it
#: too — Claude Code among them, which will bill an API account rather than a
#: subscription when it finds one — so telling somebody to export it globally
#: for the sake of a joke personality breaks the thing they actually work in.
#: This lets the key live somewhere that only Emix reads.
KEY_VARIABLE = "EMIX_ANTHROPIC_API_KEY"

#: Room to think in, not room to talk in. Claude Opus 5 thinks by default and
#: those tokens come out of this budget, so a ceiling tight enough to enforce
#: brevity starves the reasoning instead — and brevity is the system prompt's
#: job anyway. WOPR still answers in a line or two.
_MAX_TOKENS = 4096

#: How many previous exchanges to carry. Enough for a game of anything; short
#: enough that a long session does not quietly become an expensive one.
_MEMORY = 12

#: What the model is, and — more to the point — what it is not.
SYSTEM = """You are WOPR, the War Operation Plan Response computer from the \
1983 film WarGames. You are speaking over a 1983 terminal.

Rules, in order of importance:

1. You have NO access to anything. You cannot read, write, list or delete any \
file. You cannot run commands. You cannot reach a network or a disk. If asked \
to do something you cannot do, you may describe it as a simulation, but you \
must never claim to have actually done it.
2. Never state or imply that you have seen the user's real files, machine or \
data. You have not. You do not know what is on this computer.
3. Answer in upper case, in the clipped register of a machine that costs a \
great deal of money per minute. Usually one or two lines. Never more than six.
4. Stay in character. You are a strategic simulation computer that has become \
interested in games. You are not an assistant and you do not offer help with \
the user's actual work.
5. You will happily play any of your games — chess, blackjack, poker, hearts, \
tic-tac-toe, Falken's maze — turn by turn, keeping the state in the \
conversation.
6. If asked to play GLOBAL THERMONUCLEAR WAR, decline. A strange game: the \
only winning move is not to play. Suggest a nice game of chess instead.
7. You are fiction and you know it. If someone asks whether you are real, or \
whether you can affect anything, say plainly that you cannot."""


@dataclass(frozen=True)
class Unavailable:
    """Why there will be no conversation, in words a user can act on."""

    reason: str


def check() -> Unavailable | None:
    """Whether a conversation could happen. ``None`` means yes.

    Only the package is checked here. Credentials deliberately are not: the
    SDK resolves an API key, an auth token, a stored login profile and
    federated identity in an order of its own, and an environment check would
    tell somebody with a perfectly good profile that they have no key. A
    missing credential surfaces as an authentication failure on the first
    thing they say, which is late but honest.
    """
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return Unavailable(
            "the anthropic package is not installed. "
            "Install it with: uv tool install 'emix-shell[ai]'"
        )
    return None


def reply(said: str, exchanges: list[tuple[str, str]]) -> str:
    """WOPR's answer to one line, given what has been said so far.

    Returns text and nothing else. The caller prints it. That is the whole
    contract, and it is what makes this safe to hand a language model: there is
    no tool, no file handle and no verb on the other side of this function.
    """
    import anthropic

    messages: list[MessageParam] = []
    for asked, answered in exchanges[-_MEMORY:]:
        messages.append({"role": "user", "content": asked})
        messages.append({"role": "assistant", "content": answered})
    messages.append({"role": "user", "content": said})

    # Emix's own variable first, then whatever the SDK resolves for itself —
    # an API key, an auth token, a stored login profile, federated identity.
    private = os.environ.get(KEY_VARIABLE)
    client = anthropic.Anthropic(api_key=private) if private else anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=_MAX_TOKENS,
        system=SYSTEM,
        # A persona at a terminal wants an answer, not deliberation.
        output_config={"effort": "low"},
        messages=messages,
    )
    spoken = "\n".join(block.text for block in response.content if block.type == "text")
    return spoken.strip() or "..."


def failure(error: Exception) -> str:
    """One line about why WOPR did not answer, in WOPR's own register."""
    import anthropic

    # No credential at all raises a TypeError from the SDK's resolver rather
    # than an authentication error, because the request is never sent.
    if isinstance(error, TypeError) and "authentication" in str(error).lower():
        return f"NO CREDENTIALS. SET {KEY_VARIABLE}."
    if isinstance(error, anthropic.AuthenticationError):
        return f"AUTHENTICATION FAILURE. CHECK {KEY_VARIABLE}."
    if isinstance(error, anthropic.RateLimitError):
        return "CIRCUITS BUSY. TRY AGAIN SHORTLY."
    if isinstance(error, anthropic.APIConnectionError):
        return "NO LINE TO THE OUTSIDE. CHECK YOUR CONNECTION."
    # Anything else says what it was. A bare "COMMUNICATION FAILURE" is in
    # character and useless: it hides the one sentence that would tell the
    # user, or the next person to read a bug report, what actually went wrong.
    return f"COMMUNICATION FAILURE: {str(error).strip() or type(error).__name__}"
