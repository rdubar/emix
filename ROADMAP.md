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

Principle 2 has a corollary learned in 0.2: **authenticity yields when it
hides useful host data.** A CP/M directory listing that truncates
`pyproject.toml` to `PYPROJEC TOM` is authentic and useless, because the name
it prints cannot be typed back. Emix prints the full name and records the
compromise here.

## Where we are

**0.1 — working CP/M shell.** Done. Interactive prompt, host directory as
drive A:, the core file commands, safe host execution.

**0.2 — the engine, and three personalities.** Done.

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
- [x] `uv`-based workflow, ruff, strict mypy, 62 tests, CI on macOS and Linux
- [x] Persistent readline history per personality

## 0.3 — depth in the personalities we have

- [ ] CP/M user areas (`USER 0`–`15`) as a real, optional view
- [ ] Reversible 8.3 aliases: show `PYPROJ~1.TOM`, accept it back, never
      rename the host file
- [ ] VMS directory syntax — `[DIR.SUB]`, `[-]`, `SET DEFAULT` across devices
- [ ] VMS file versions backed by the host, opt-in, with a retention limit
- [ ] CMS `EXEC` files and a minimal `XEDIT`
- [ ] Golden-session tests: feed a script, compare a full transcript
- [ ] `MOUNT` at runtime, and a config file so drives persist between sessions
- [ ] Tab completion that offers names in the personality's own casing

## 0.4 — the fourth personality

Candidates, in order of preference:

1. **TOPS-20 / TENEX.** The recogniser (`ESC` completes, `?` lists options)
   is the most interesting UI idea any of these systems had, and would be a
   genuine test of the engine's input layer rather than its formatter.
2. **MS-DOS 3.3.** The most recognisable to the most people. Cheap, because
   the file model is nearly CP/M's.
3. **Unix v7.** The joke being that the retro personality is a *smaller*
   Unix. `ed`, no job control, terse errors.

## 0.5 — running real CP/M binaries

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

- Is Emix a playful daily shell or an educational environment? The code has
  quietly answered "daily shell" — `UNIX`, host fallthrough and a `STAT` that
  reports real host bytes are not museum behaviour. Worth confirming, because
  it settles most of the authenticity trade-offs below it.
- Should a personality be able to ship small built-in programs, so `STAT`
  becomes a transient rather than a verb? Required before 0.5 makes `.COM`
  dispatch natural.
- Should drives be mountable from an archive or disk image, read-only, so
  historical software can be browsed without unpacking it?
- How much of a personality can be data rather than code? CMS proved the
  engine handles a genuinely different file model, but each personality still
  writes its own `split_spec`. Is that irreducible?
