# Emix roadmap

## Aim

A pleasant retro-computing shell that stays genuinely useful on a current Mac,
Linux box or Raspberry Pi. Emix reproduces the vocabulary and feel of
historical systems without pretending to be binary-accurate hardware
emulation — until, deliberately and in one clearly bounded place, it does.

## Principles

1. **The host stays real.** Files and programs belong to Unix. A personality
   is another way to reach them, not a container around them.
2. **Authenticity should teach.** Prompts, syntax, help, errors and output
   formats should be recognisable, and where Emix departs from history it
   should say so rather than quietly inventing.
3. **Safety is visible.** Destructive commands confirm, drives are sealed
   after symlink resolution, and no host command runs through a shell.
4. **Personalities share an engine.** Vocabulary and house style are the only
   things a personality should have to write.
5. **Mac and Pi are first-class.** Small install, no runtime dependencies.
   Windows joined them in 0.4 and is held to the same bar, with one stated
   exception recorded below.

Principle 2 has a corollary learned in 0.2: **authenticity yields when it
hides useful host data.** A CP/M directory listing that truncates
`pyproject.toml` to `PYPROJEC TOM` is authentic and useless, because the name
it prints cannot be typed back. Emix prints the full name and records the
compromise here.

## Where we are

**0.1 — working CP/M shell.** Done. Interactive prompt, host directory as
drive A:, the core file commands, safe host execution.

**0.2 — the engine, and three personalities.** Done.

**0.3 — real applications, and assistance that teaches.** Done. See the
changelog; 0.4 adds Windows and moves the phosphor to the main text.

- [x] Shared drive layer (`host.py`): containment enforced *after* symlink
      resolution, case-insensitive lookup, loud failure on case ambiguity
- [x] Shared REPL and verb table (`shell.py`), replacing `cmd.Cmd`, which
      could not express DCL abbreviation or `/QUALIFIER` syntax
- [x] Symbolic error codes worded per personality (`NO FILE` vs `%RMS-E-FNF`
      vs `DMSxxx002E`)
- [x] Multiple drives, mounted with repeatable `--mount`
- [x] CP/M corrected to its real six CCP built-ins, with `PIP` and `STAT`
      shown as the transient programs they were
- [x] VAX/VMS DCL personality: abbreviation, qualifiers, `DELETE` version rule
- [x] IBM VM/CMS personality: three-token fileids, `Ready;` responses
- [x] `uv`-based workflow, ruff, strict mypy, CI on macOS and Linux
- [x] Persistent readline history per personality

## Assistance, and the line it must not cross

Emix helps, under three rules that keep the help from eating the product:

1. **The authentic response comes first, verbatim.** A hint is added below it,
   never in place of it, and never reworded. There is a test asserting that
   assisted output starts with exactly the strict output.
2. **Hints carry the `Emix:` marker**, so invented prose is never mistaken for
   a period diagnostic.
3. **Nothing is executed on a guess.** A hint names the real command; the user
   types it. That is what makes a convenience a lesson.

Strict mode (`--strict`, or `STRICT ON`) removes tiers 2 and 3 entirely. It is
on by default for scripts and pipes, because a script must not depend on a
guess, and it is the deterministic baseline the golden-transcript tests need.

Completion is exempt: it changes what you type, never what runs, so it stays on
even in strict mode — and completing `DIR` to `DIRECTORY` is itself a way of
learning the vocabulary.

## Depth in the personalities we have

> The numbered milestones below are plans, not a schedule. Windows took 0.4
> while several of these were still open, which is normal and worth saying
> once rather than renumbering headings after every release.

- [ ] CP/M user areas (`USER 0`–`15`) as a real, optional view
- [x] Reversible 8.3 aliases: `DIR` shows `PYPROJ_1.TOM`, `TYPE` accepts it
      back, and the host file is never renamed
- [ ] VMS directory syntax — `[DIR.SUB]`, `[-]`, `SET DEFAULT` across devices
- [ ] VMS file versions backed by the host, opt-in, with a retention limit
- [ ] CMS `EXEC` files and a minimal `XEDIT`
- [x] Golden-session tests: feed a script, compare a full transcript
- [ ] `MOUNT` at runtime (a config file now persists drives, colour and
      strictness: `~/.config/emix/emix.toml`)
- [x] Tab completion that offers names in the personality's own casing

## The next personality

Candidates, in order of preference:

1. **TOPS-20 / TENEX.** The recogniser (`ESC` completes, `?` lists options)
   is the most interesting UI idea any of these systems had, and would be a
   genuine test of the engine's input layer rather than its formatter.
2. **MS-DOS 3.3.** The most recognisable to the most people. Cheap, because
   the file model is nearly CP/M's.
3. **Unix v7.** The joke being that the retro personality is a *smaller*
   Unix. `ed`, no job control, terse errors.

## Windows, and the one dependency it costs

Windows is supported and covered by CI. Four things needed saying, and only
one of them was a real decision:

- **The console must be asked.** A Windows console starts in a mode where
  `ESC[92m` is five characters to print rather than an instruction.
  `SetConsoleMode` turns that off, via `ctypes` and no dependency. If the
  console refuses, Emix falls back to plain text rather than printing escape
  sequences at somebody.
- **The screen colour stays off.** Windows can neither answer OSC 11 nor
  describe a Windows Terminal profile's RGB background through the legacy
  attribute word, so the background is unknown and unknown means plain — the
  same rule as a terminal that will not say. Windows users opt in by name.
- **Settings go where Windows keeps settings**, `%APPDATA%\emix\`, with
  history under `%LOCALAPPDATA%`. A setting the user cannot find is a setting
  that does not work.
- **`CreateProcess` only appends `.exe`.** Host fallthrough could not reach a
  program a Windows prompt runs happily, so names now resolve through
  `shutil.which`, which honours `PATHEXT`. **Batch files stay unreachable, on
  purpose.** Windows runs a `.bat` through `cmd.exe` even when Python is told
  not to use a shell, and re-parses the arguments by shell rules Python does
  not escape — a file named `a&b` would become a second command. Principle 3
  says no host command runs through a shell, so Emix refuses with a message
  saying why rather than quietly making the principle false on one platform.
- **`readline` does not exist there**, and that is the real decision.

Tab completion is not a convenience in Emix — the roadmap exempts it from
strict mode precisely because completing `DIR` to `DIRECTORY` teaches the
vocabulary. Losing it on Windows loses a teaching feature, not a nicety. So
`pyreadline3` is an **optional extra**, `emix-shell[windows]`, which keeps
Principle 5 true where it is claimed rather than quietly false everywhere.
Writing a line editor to avoid one optional dependency would be a far worse
trade than taking it.

Still open: RunCPM builds on Windows, but the application bridge is neither
documented nor tested there. Until it is, the manual says so.

## An application catalogue, not an application bundle

Emix would be far easier to try if `emix apps` could offer software rather
than assume it. The obvious version of that — bundle the freeware, ship ELIZA
and an editor and a spreadsheet in the wheel — is the wrong one, and it is
worth writing down why, because the argument for it is genuinely appealing.

**It contradicts the product.** `profiles.py` opens with "a profile carries
configuration and compatibility knowledge, never a copyrighted byte", and the
README's second paragraph says Emix ships no operating systems and no
applications. Those are not disclaimers, they are the reason the licence is
unambiguous and the reason nobody has to ask what is in the package.

**"Essentially freeware" hides three different legal situations:**

| Category | Examples | Shippable |
| --- | --- | --- |
| Explicit grant | CP/M itself, `TE.COM`, VDE | Yes, with the grant alongside |
| Public domain by origin | Ahl's *101 BASIC Computer Games*, most ELIZA ports | Yes |
| Abandonware, no grant | WordStar, SuperCalc, dBASE II, Multiplan | No |

The third row is the one people mean and the one that cannot ship. It is
mirrored everywhere and nobody is litigating, but PyPI is a far more visible
distribution point than a hobbyist FTP site, and a package index is where a
rights holder would actually look. Turbo Pascal is the trap inside the first
row: Borland's "antique software" release is *personal use only*, which does
not survive contact with an MIT repository even though everyone calls it free.

### What to build instead

Extend profiles into a catalogue. A catalogue entry is the profile that
already exists plus provenance — upstream URL, checksum, licence — so:

```sh
emix apps --list-available
emix apps --install te
```

fetches from whoever already distributes the software, verifies it, and writes
the profile. Emix still ships nothing, so the README's claim stays literally
true, and the install stops being the hardest step for a new user.

This is also where the value actually is. WordStar is mirrored in a dozen
archives; the knowledge that TE's `Delete` is bound to `^G` because that is the
WordStar diamond exists nowhere but the `notes` field of a profile. The bytes
are a commodity. The catalogue is not.

Open questions: whether fetching over the network belongs in a tool whose
pitch is having no dependencies (`urllib` is standard library, so the honest
answer is probably yes); and whether a checksum mismatch should refuse or warn.

If a real bundle is ever wanted, it belongs in a **separate repository** with a
licence file per artifact, never in `emix-shell`.

## 0.5 — running real CP/M binaries

> **Reordered, not abandoned.** [APPLICATIONS.md](APPLICATIONS.md) reaches the
> same destination through an external emulator first, because that answers
> the product question — does this feel delightful? — before the expensive
> work starts. The two arguments below still hold, and the staging machinery
> that an external backend requires is the measured cost of deferring them.
> Two corrections recorded there: the performance worry below targets games
> rather than editors, and a BDOS should be written against RunCPM's
> accumulated compatibility fixes, not the specification alone.

This is the point where Emix stops being only a compatibility shell, and the
one place binary emulation earns its cost. The plan is smaller than it sounds,
for two reasons.

**The emulator is the sandbox.** An 8080 interpreter has no access to
anything except the 64 KB memory array it is given and the BDOS calls the host
chooses to implement. There is no syscall surface to escape through, because
there are no syscalls — only a `CALL 5` that lands in Python. No seccomp, no
container, no ptrace. The security boundary is a `match` statement.

**The BDOS is the drive layer we already built.** CP/M's file functions
(open, close, search-first, search-next, read, write, delete, rename) operate
on File Control Blocks holding an 8.3 name and a drive number. Mapping an FCB
onto a host file is exactly what `host.DriveSet` does today, containment
check included. A `.COM` binary running under Emix would reach the host
through the same sealed drives, with the same confirmations, as a typed `ERA`.

Sketch:

```
emix/machine/
  cpu8080.py      the interpreter: ~250 opcodes, no undocumented behaviour
  memory.py       64 KB, with the zero page and TPA laid out correctly
  bdos.py         functions 0-40, each one calling into host.DriveSet
  bios.py         the jump table: console in/out, disk select
  loader.py       read a .COM file into 0x0100 and jump there
```

Work:

- [ ] 8080 core with a passing `8080EXM`/`CPUTEST` exerciser suite
- [ ] BDOS functions 0–40 over the existing drive layer
- [ ] Console redirection so an emulated program reads and writes the real
      terminal
- [ ] `A>PROGRAM.COM` dispatches to the machine when the file exists, keeping
      the current host-executable fallthrough for everything else
- [ ] A resource ceiling: instruction budget and wall-clock timeout, so a
      wild binary cannot spin forever
- [ ] Optional Z80 opcodes, which unlocks most interesting CP/M software

Explicitly **not** in scope: disk image formats, CP/M 3 banked memory, MP/M,
or cycle-accurate timing. Emix mounts host directories; it does not mount
`.dsk` files.

## 1.0

- [ ] Three or more personalities, each with a golden-session suite
- [ ] Published on PyPI, installable with `uv tool install emix`
- [ ] A written guide to adding a personality
- [ ] CP/M binaries running well enough for `ZORK1.COM`

---

## Implementation language

Worth settling now, before there is more to rewrite.

### The question

Emix is two workloads wearing one coat.

**The personality layer** — parsing command lines, folding case, formatting
columns, wording errors, mapping file specifications — is string manipulation
with heavy iteration on *taste*. Getting `%DCL-W-IVVERB` right is a matter of
trying it, reading it, and changing it. Python is close to ideal here, and the
whole of 0.2 is 1,400 lines with no dependencies.

**The machine layer** (0.5) is a tight interpreter loop, the one part of the
system where constant factors matter.

### The numbers

An 8080 at 2 MHz retires roughly 290,000 instructions per second; a 4 MHz Z80
about a million. A dictionary-dispatch interpreter in CPython 3.13 manages
somewhere between 300,000 and 1,000,000 emulated instructions per second,
depending how carefully the inner loop is written.

So CPython lands at *approximately period-authentic speed*. That is a
delightful result and an uncomfortable engineering position: enough to be
honest, with no headroom for a Z80, a slow terminal, or an interpreted
language running on top.

Go or Rust would deliver 50–200 million instructions per second — two to three
orders of magnitude more than needed, which is another way of saying the
extra performance buys nothing that matters here.

### Distribution

The strongest historical argument for Go was the single static binary: one
file, `scp` it to the Pi, done. That argument has weakened. `uv tool install
emix` and `uvx emix cpm` install the interpreter as well as the package, from
one command, on macOS and Linux and Raspberry Pi OS alike. It is not quite a
static binary, but it is no longer a story about virtualenvs.

Against that, Python costs about 40 ms of interpreter startup per invocation.
For a shell you start once and sit inside, this is irrelevant.

### Decision: stay on Python

1. The value of Emix is in the personality layer, and that layer is where
   Python is strongest and a rewrite would hurt most.
2. `uv` has closed most of the distribution gap that would have justified Go.
3. The performance-critical component is small, isolated, and does not exist
   yet. Choosing a language today for code not yet written, at the cost of the
   code that already works, is the wrong trade.
4. Contributors who want to add a personality are more likely to write Python.

### The trigger for revisiting

This is a decision with an exit condition, not a conviction.

**If** the 8080 core in Python cannot sustain 4 MHz Z80 equivalent
(~1M instructions/second) after a reasonable optimisation pass, **then**
extract `emix/machine/cpu8080.py` alone into a Rust extension built with
maturin and PyO3, keeping BDOS, BIOS and every personality in Python.

That is a few hundred lines behind a stable interface — `step()`,
`run(budget)`, and a memory view — not a rewrite. The `machine/` package
boundary in the 0.5 sketch exists to make that swap cheap, and it should be
designed to be replaceable even if it never is replaced.

A full port to Go would only make sense if the goal changed from "a pleasant
shell that can also run binaries" to "a serious multi-system emulator." That
would be a different project, and it should be honest about being one.

## Questions still open

~~- Is Emix a playful daily shell or an educational environment?~~
  **Answered.** Emix is a serious way to explore how these systems felt.
  Convenience is scaffolding, and scaffolding has to teach rather than
  substitute — which is why `ls` prints CP/M's own `LS?` and *then* names
  `DIR`, instead of quietly running `DIR`. See "Assistance" below.
- Should a personality be able to ship small built-in programs, so `STAT`
  becomes a transient rather than a verb? Required before 0.5 makes `.COM`
  dispatch natural.
- Should drives be mountable from an archive or disk image, read-only, so
  historical software can be browsed without unpacking it?
- How much of a personality can be data rather than code? CMS proved the
  engine handles a genuinely different file model, but each personality still
  writes its own `split_spec`. Is that irreducible?
