# Emix ideas

This is the playful notebook, not the roadmap. Nothing here is a promise. The
test for an idea is whether it makes Emix more delightful or more useful
without blurring the line between a historical personality and an Emix
extension.

The historical application and document bridge has graduated out of this
notebook: see [APPLICATIONS.md](APPLICATIONS.md), where Phase 0 is built.

## A little colour

The jokes should be opt-in. Random jokes in error messages would make scripts
unreliable and teach the wrong historical behaviour. A shared `JOKE` command,
an optional login message, or a `SET HUMOR ON` switch would keep the authentic
path clean.

Possible neutral one-liners:

- There are two hard problems in computer science: cache invalidation, naming
  things, and convincing the operator this list has only two items.
- The cloud is just somebody else's mainframe with better marketing.
- A backup is a rumour until somebody completes a restore.
- Unix says nothing when it succeeds. It is saving the good paper.
- The fastest code is the branch the requirements removed.
- The bug was intermittent until the demo began.
- The computer is never impatient. It can misunderstand you millions of times
  per second.
- Compatibility is the art of preserving yesterday's surprises tomorrow.
- Every temporary file is applying for permanent residency.
- The terminal has 80 columns because the 81st contained the truth.
- Documentation is a message from the person who knew to the person they will
  become after six months.
- Artificial intelligence: now able to automate the typo at unprecedented
  scale.

Personality-specific lines could be more fun:

### CP/M

- `A>WHY` — `WHY?`
- PIP does not install packages. It has been moving bytes since before that
  was fashionable.
- Drive B: is not missing. It is enjoying removable media.
- Eight characters ought to be enough for anybody's filename.
- `BAD COMMAND FORMAT` — the machine's concise review of modern syntax.
- Why did the file cross the drive? PIP put it there, destination first.

### VMS

- `%COFFEE-F-NOMUG, no such vessel available`
- `%MONDAY-W-RETRY, weekend completion status not retained`
- `%HUMOR-S-DELIVERED, operator response may vary`
- DCL commands are never cut short; they are unambiguously abbreviated.
- File versions mean never having to say you overwrote it.
- The percent sign is not pessimism. It is structured pessimism.

### VM/CMS

- `DMSPUN001I HUMOR FILE A1 LOADED`
- A filename, a filetype and a filemode walk into a minidisk.
- `Ready;` is both a status report and an admirable state of mind.
- The virtual machine would like to remind the physical machine who had the
  idea first.
- CMS has no prompt. It trusts that you know whose turn it is.
- Mainframes: doing cloud computing before clouds had rounded corners.

Other ways to add atmosphere:

- A `FORTUNE` transient for CP/M, a `RUN SYS$SYSTEM:PUN` fiction for VMS, and
  a `HUMOR EXEC` fiction for CMS, all backed by the same bundled joke data.
- Rare calendar-aware greetings for harmless dates such as Programmer's Day,
  with a configuration switch and deterministic tests.
- Tiny period facts after `ABOUT /HISTORY` or `HELP EMIX`, rather than mixing
  them into authentic command help.
- An optional fake line-printer queue that turns plain text into green-bar
  HTML or PDF. This is silly, visual, and surprisingly useful.
- Achievement messages kept outside normal output: first cross-drive copy,
  first valid VMS abbreviation, first CMS three-token fileid.

## WOPR: the fourth personality that never existed

> **Built.** `emix wopr` ships as of 0.5. What follows is the reasoning that
> got it there, kept because the argument for making it a personality rather
> than an easter egg applies to the next invented one too.

`emix wopr` — the WarGames terminal. Type what David Lightman types and get
what he gets.

The important design decision is that this is **a personality, not an easter
egg**. An egg hidden inside `cpm` would put invented behaviour behind a period
prompt, which is the exact thing `is_emix_verb` and the painting rule exist to
prevent. A separate personality keeps the promise: every prompt is honest
about what it is.

And WOPR is the one personality that cannot be inauthentic, because it is
fictional. Every other personality is measured against a real system and can
be caught getting it wrong. This one is measured against a film, which makes
it the cheapest personality the engine will ever host — no manuals to check,
no error formats to reproduce, no risk of teaching something false.

The shape:

```
LOGON: JOSHUA

GREETINGS PROFESSOR FALKEN.

SHALL WE PLAY A GAME?
```

`HELP GAMES` and then `LIST GAMES` produce the list, from FALKEN'S MAZE down
through the card games to GLOBAL THERMONUCLEAR WAR. It has no prompt of its
own, because WOPR simply talks — which the engine already supports, since CMS
has no prompt either.

Three things to settle before building it:

- **Most of the games should actually work.** This is what turns a gag into a
  feature. CHESS, CHECKERS, POKER, BLACK JACK and HEARTS all exist as public
  domain BASIC programs, so `PLAY CHESS` can dispatch through the application
  machinery in [APPLICATIONS.md](APPLICATIONS.md) rather than printing an
  apology. WOPR then becomes the shop window for the catalogue below, and the
  two ideas pay for each other.
- **The dialogue is copyrighted.** WarGames is 1983 and still in copyright.
  Quoting the four lines everyone knows is short-form quotation and is very
  likely fine; reproducing the whole scene is a different act. The safer
  version is also the more Emix-ish one — recreate the *interaction* and write
  the connective tissue, exactly as the personalities recreate CP/M's
  behaviour rather than shipping CP/M.
- **GLOBAL THERMONUCLEAR WAR prints its line and stops.** "A STRANGE GAME.
  THE ONLY WINNING MOVE IS NOT TO PLAY." A straight-faced refusal is both the
  joke and the correct implementation.

ELIZA belongs in the same room. WOPR and ELIZA are the same joke seventeen
years apart — a person talking earnestly to a machine that is only matching
patterns — and most ELIZA ports are public domain. A `TALK` verb under WOPR,
or ELIZA as a catalogue entry, would make the pairing visible.

## AI integrations that fit Emix

The best AI features translate between modern intent and historical syntax.
They should not turn the shell into a generic chatbot.

### Strong candidates

1. **`ASK` — intent to command.** `ASK show large text files on drive B`
   proposes a native command such as `DIRECTORY/SIZE B:*.TXT`. It displays the
   command first and never executes destructive output without the existing
   confirmation path.
2. **`EXPLAIN` — interpret the last interaction.** Explain why VMS demanded a
   version number, why CP/M uses `NEW=OLD`, or what a CMS filemode means. This
   is educational, read-only, and naturally grounded in the active
   personality.
3. **`TRANSLATE` — move between personalities.** Show the CP/M, DCL and CMS
   equivalents of a simple file operation, including when there is no honest
   equivalent. This makes the shared engine visible and teaches all three
   systems.
4. **`FIND /MEANING` — semantic file search.** Search mounted text files for a
   concept rather than a literal string. Index only files inside sealed
   drives, honour ignore rules and size limits, and show ordinary fileids as
   results.
5. **`SCRIPT` — draft a command procedure.** Turn a goal into a `.COM`, DCL
   command procedure, or CMS `EXEC`. Generate into a preview buffer or new
   file; do not execute it automatically.
6. **Contextual completion.** After `DELETE`, completion can explain the VMS
   version requirement; after `PIP`, it can suggest destination-first syntax.
   A small local model may be enough, and deterministic completion remains
   the default.
7. **The historian.** A grounded Q&A command over bundled, cited notes about
   CP/M, VMS and CMS. Answers should distinguish original behaviour, Emix's
   approximation and modern host behaviour.
8. **Personality workshop.** A developer command that reads a short system
   description and drafts a new personality module, tests and golden
   transcript. This belongs in development tooling, not the installed shell.

### Playful experiments

- A simulated system operator who answers in the active machine's house style.
- Natural-language release notes rendered as a period memo, operator bulletin
  or login notice.
- OCR for photographed manuals, producing searchable local notes for the
  historian.
- A “what would this error look like elsewhere?” command that translates an
  Emix error code across all installed personalities.
- A local naming assistant that proposes reversible 8.3 names while showing
  exactly what will appear on the host.

## Guardrails and shape

- AI is optional. Emix should keep zero runtime dependencies and work fully
  offline without it.
- Start with a small provider protocol: prompt in, text out. Provider packages
  can be optional extras or external commands, with a deterministic fake used
  by tests.
- Never send file contents, paths, usernames or command history to a remote
  provider without an explicit per-feature opt-in and a visible preview of the
  scope.
- Treat model output as untrusted input. Parse proposed commands through the
  normal personality parser and drive layer; never pass generated text to a
  host shell.
- Read-only proposals can be convenient. Writes, renames, deletions and host
  execution must remain obvious and use the same safety checks as typed
  commands.
- Label generated explanations as Emix output so nobody mistakes invented
  prose for an authentic historical diagnostic.
- Cache only with permission, keep it outside mounted drives by default, and
  make deletion simple.

## A sensible first experiment

Build `EXPLAIN` before `ASK`. It needs only the last parsed invocation, result
code and a compact description of the active personality. It is read-only,
useful to newcomers, easy to test with a fake provider, and cannot silently
turn prose into an operation. If that feels native, `ASK` can reuse the same
provider boundary while adding command preview and validation.

For humour, begin even smaller: a bundled, deterministic `JOKE` command with
tags for `general`, `cpm`, `vms` and `cms`. No network, no model, and no random
changes to normal command output.
