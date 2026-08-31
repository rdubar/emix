# The Emix manual

Emix lets a modern Unix machine present itself as an older computer — and,
when you want it to, run that computer's actual software on your actual files.

Every transcript in this manual was captured from a real session. Nothing here
is a mock-up.

---

## 1. What Emix is, and what it is not

Emix is two things that are easy to confuse, so they are stated separately.

**A personality is not an emulator.** `emix cpm` gives you CP/M's commands,
syntax, output formats and error messages, implemented in Python over ordinary
host files. No 8080 is involved. `DIR` is not CP/M's `DIR`; it is Emix's, and
it is written to answer the way CP/M's did.

**An application is an emulator.** `A>TE LETTER.TXT` loads a real `TE.COM` and
executes real Z80 instructions, via [RunCPM](https://github.com/MockbaTheBorg/RunCPM).
The bytes running are the bytes from 1985.

Emix owns the experience around that: which drives exist, what your file is
called inside the guest, and what comes back out. It does not own the CPU, and
does not want to.

**Emix ships no operating systems and no applications.** You supply CP/M
software you already have, lawfully. Emix supplies configuration and the
knowledge of how to use it.

---

## 2. Getting started

```sh
uv tool install emix-shell     # or: pipx install emix-shell
emix cpm
```

The current directory becomes drive A:. Mount more with `--mount`, which is
repeatable and names drives in each personality's own style.

```sh
emix cpm --mount ~/Documents --mount ~/src   # A: and B:
emix vms --mount ~/Documents                 # DKA0:
emix cms --mount ~/Documents                 # filemode A
```

Settings persist in `~/.config/emix/emix.toml`; the command line always wins.

```toml
[emix]
personality = "cpm"
hint-colour = "yellow"

[drives]
default = ["~/Documents"]
```

---

## 3. The personalities

### CP/M 2.2

```text
EMIX 0.2.1
CP/M 2.2 PERSONALITY
A: /private/tmp/letters
TYPE HELP FOR AVAILABLE COMMANDS.

A>DIR
A: LETTER_1 TXT A: NOTES    TXT A: PYPROJ_1 TOM

A>STAT
A: R/W, SPACE: 94,126,604K

A>TYPE NOTES.TXT
hello

A>PIP BACKUP.TXT=NOTES.TXT

A>DIR
A: BACKUP   TXT A: LETTER_1 TXT A: NOTES    TXT A: PYPROJ_1 TOM
```

The CCP's six built-ins are exactly the six it had — `DIR`, `ERA`, `REN`,
`SAVE`, `TYPE`, `USER`. `PIP` and `STAT` are listed separately in `HELP`,
because they were transient `.COM` programs loaded from disk, not built-ins.
`PIP` and `REN` keep their destination-first argument order.

### VAX/VMS DCL

```text
$ DIRECTORY

Directory A:[000000]

NOTES.TXT;1
PYPROJECT.TOML;1
REPORT.TXT;1

Total of 3 files.

$ DELETE NOTES.TXT
%DELETE-W-NOVER, explicit version number required
```

Verbs abbreviate to any unambiguous prefix, `/QUALIFIERS` parse, and `DELETE`
insists on a version number the way VMS did.

### VM/CMS

```text
LISTFILE
NOTES    TXT      A1
PYPROJECT TOML     A1
REPORT   TXT      A1
Ready; T=0.01/0.01 15:44:02

ERASE NOSUCH TXT A
DMSxxx002E File 'NOSUCH.TXT' not found
Ready(00028); T=0.01/0.01 15:44:02
```

A file is three words — filename, filetype, filemode — and CMS answers
`Ready;` with processor times, or `Ready(nnnnn);` after a failure.

---

## 4. Running real CP/M software

This is the part that runs actual binaries.

### Setting it up

Emix needs an emulator and some CP/M software. RunCPM provides both — it is
MIT-licensed, and its sample disk carries a usable CP/M system:

```sh
git clone https://github.com/MockbaTheBorg/RunCPM ~/dev/RunCPM
cd ~/dev/RunCPM/RunCPM && make -f Makefile.macosx CCP=INTERNAL
unzip -o ~/dev/RunCPM/DISK/A0.zip -d ~/dev/RunCPM/DISK/
```

`CCP=INTERNAL` matters: the other CCP options need an external `CCP-*.60K`
file at runtime.

Then describe the programs in `~/.config/emix/apps.toml`:

```toml
[app.ed-cpm]
backend = "runcpm"
program = "ED.COM"
application = "~/dev/RunCPM/DISK/A/0"
executable = "~/dev/RunCPM/RunCPM/RunCPM"
notes = """
ED, Digital Research's original CP/M line editor. There is no screen.
  #A  read the file in     I  insert     ^Z end insert
  #T  type the buffer      E  save and exit    Q  quit
"""
```

`emix apps` lists what is configured and checks that each backend is present.

### From inside the personality

```text
A>APPS
DDT        DDT.COM        DDT
ED         ED.COM         ED-CPM
LU         LU.COM         LU
MBASIC     MBASIC.COM     MBASIC
TE         TE.COM         TE-CPM
ZEXDOC     ZEXDOC.COM     ZEXDOC

A>ED LETTER.TXT
```

The name is resolved through Emix's drive layer first, so an application
reaches exactly the files a typed `TYPE` would — inside the drive, after
symlinks are followed, matched without regard to case.

### ED, for real

```text
B0>A:ED NEW.TXT

NEW FILE
     : *I
    1:  Dear Gary,
    2:  The BDOS is a triumph.
    3:
     : *
     : *E
```

### MBASIC, for real

```text
BASIC-85 Rev. 5.29
[CP/M Version]
Copyright 1985-1986  $  by Microsoft
Created: 28-Jul-85
39224 Bytes free
Ok
10 FOR I=1 TO 3
20 PRINT "CP/M";I
30 NEXT
RUN
CP/M 1
CP/M 2
CP/M 3
Ok
SYSTEM
```

`SYSTEM` returns to CP/M and ends the session. Every profile can carry that
kind of knowledge in its `notes`, shown before the program starts.

### What happens to your file

Emix stages the document, runs the program, then shows you what changed and
asks before writing anything:

```text
A>TE LETTER.TXT
Preparing te-cpm...
  ESC opens the menu: S save, A save-as, X exit, H help.
  Movement is the WordStar diamond: ^E up, ^X down, ^S left, ^D right.
  Delete removes the character to the RIGHT; use ^H to delete to the left.
LETTER.TXT is available as B:LETTER.TXT

    [ the editor runs ]

DOCUMENT SESSION COMPLETE

  MODIFIED  LETTER.TXT
  IGNORED   TE.BKP  (the application's own backup)

Save these changes to the host? [Y/n]
```

Only the document you named is staged, so the program cannot read the rest of
the folder. The editor's own backup is named but not committed. The write is
atomic, and is refused outright if the host file changed while the guest was
running.

---

## 5. Files, names and drives

A drive is a host directory. Nothing is a disk image; nothing is unpacked.

CP/M has eight characters, a dot, and three more. Modern names do not fit, and
a listing that prints `PYPROJEC.TOM` names a file you cannot type back. Emix
prints a reversible alias instead, and accepts it:

```text
A>DIR
A: NOTES    TXT A: PYPROJ_1 TOM A: REPORT   TXT

A>TYPE PYPROJ_1.TOM
[build-system]
requires = ["hatchling"]
```

The host file is never renamed. A real host name always wins over an alias, so
this only ever adds a way to reach a file.

---

## 6. Safety

Emix runs on your real home directory, so the boundaries are explicit:

- **Drives are sealed.** Every path is checked against its drive root *after*
  symlinks are resolved, so a symlink pointing out of a drive is neither
  readable nor listed. Applications go through the same layer.
- **No shell is ever invoked.** Host commands are run with an argument list,
  so `|`, `>`, `&&` and `$VAR` are literal text.
- **Case ambiguity fails loudly.** If `readme.txt` and `README.TXT` both
  exist, Emix says so rather than picking one.
- **Destructive commands confirm**, and anything but an explicit yes is no.
- **Guest changes are reviewed before they are committed**, written
  atomically, and refused if the host file moved underneath the session.

Erasing a file in Emix erases it on the host. That is the point of the
project, and the reason for everything above.

---

## 7. Assistance, and how to turn it off

Emix helps you find the period command without pretending to be a system that
accepted yours:

```text
A>ls
Emix: CP/M 2.2 has no ls. To list the files, use DIR.
LETTER.TXT
NOTES.TXT

A>DIRR
DIRR?
Emix: Did you mean the command DIR?

A>TYPE NOTEZ.TXT
NO FILE
Emix: Did you mean the file NOTES.TXT?
```

Note what `ls` does there: CP/M has host fallthrough, so the hint is printed
*and then the host `ls` runs*. Emix names the period command without blocking
the one you typed. Under VMS and CMS, which do not fall through, the same
line produces only the authentic error and the hint.

Three rules make this safe to leave on:

1. **The authentic response prints first, verbatim.** `DIRR?` is exactly what
   the CCP said. The hint goes below it, never instead of it.
2. **Every added line is marked `Emix:`** and coloured — green phosphor when
   Emix can tell the terminal is dark, amber otherwise — so nothing invented is
   mistaken for a period diagnostic. Output from commands the original system
   never had — `ABOUT`, and CP/M's `HELP` — is coloured for the same reason.
3. **Nothing is executed on a guess.** A hint names the command; you type it.

`EXPLAIN` describes the last command or failure, using bundled knowledge — no
model, no network:

```text
$ DELETE FOO.TXT
%DELETE-W-NOVER, explicit version number required
$ EXPLAIN
Emix: DELETE needs an explicit version, as in FILE.TXT;1. VMS kept every
Emix: version of a file, so a delete without one was too easy to get wrong.
```

`STRICT ON`, or `--strict`, removes all of it. **Scripts and pipes are strict
by default**, because a script must not depend on a guess. Tab completion
stays on either way: it changes what you type, never what runs.

---

## 8. Where Emix is faithful, and where it is not

**Faithful.** The CCP's six built-ins and the transient/built-in distinction.
`REN NEW=OLD` and `PIP NEW=OLD` argument order. DCL abbreviation, qualifiers,
and the `DELETE` version rule. CMS three-token fileids and `Ready;` with
processor times. Error messages in each system's house format.

**Deliberately not.** `ERA` confirms every erase, where CP/M only confirmed
for `ERA *.*` — these are your real files. Long names are shown as reversible
aliases rather than truncated. File versions display as `;1` but only one copy
is stored. `HELP`, `ABOUT`, `APPS`, `EXPLAIN` and `STRICT` are Emix additions,
and are coloured and listed as such.

**Not built.** CP/M user areas as a real view. VMS directory syntax and true
file versions. CMS `EXEC` and `XEDIT`. A native 8080/Z80 core — today, running
binaries means an external emulator, and that is why your document is staged
and reviewed rather than written live.

---

## 9. Credits

Emix stands on other people's work and tries to be clear about which parts.

- **[RunCPM](https://github.com/MockbaTheBorg/RunCPM)**, by Marcelo Dantas
  (MIT) — the Z80 and CP/M 2.2 emulator that actually runs the binaries. It
  keeps CP/M drives as ordinary host folders, which is what makes the whole
  approach possible.
- **TE**, by Miguel Garcia / FloppySoftware — a freely distributable
  full-screen editor for CP/M, and the reason Emix has something to
  demonstrate that anyone may redistribute.
- **Digital Research** — CP/M 2.2, `ED`, `PIP`, `STAT`, `DDT`, and the design
  that all of this is trying to be recognisable as.
- **DEC** and **IBM**, for VMS DCL and VM/CMS respectively.

Emix itself is MIT-licensed, by Roger Dubar.

---

## 10. Known limitations

- Applications need an emulator you install separately; Emix detects it and
  explains rather than bundling it.
- Guest changes are staged and reviewed, not written live. Mapping a folder
  directly as a guest drive is not safe while an external emulator owns the
  file calls — it would bypass the containment described in section 6.
- TE converts tabs to spaces when it reads a file, so a round trip through it
  is lossy for tab-indented text.
- macOS and Linux only. Interactive terminal attachment is the whole point,
  and `pty` is Unix-only.
- CP/M user areas are not modelled; area 0 is the only one.

Bug reports and corrections — especially from people who used these systems
when they were current — are welcome at
<https://github.com/rdubar/emix/issues>.
