# The Emix manual

Emix lets you try older computer systems — CP/M, VAX/VMS DCL, and VM/CMS — on
your own computer and your own files. You don't need disk images, and you
don't move your files into a virtual machine.

Emix runs on **macOS, Linux and Windows** with Python 3.11 or newer. On a
Raspberry Pi it runs on the Pi's own console as happily as over SSH.

You do not need to know any of the old systems before you start. This manual
explains the odd parts as they appear.

## 1. Try it in a spare folder

The quickest trial does not install anything permanently:

```sh
mkdir -p ~/emix-playground
cd ~/emix-playground
printf 'Hello from a modern file.\n' > NOTES.TXT
uvx --from emix-shell emix cpm
```

You will see a CP/M-style prompt:

```text
A>DIR
A: NOTES    TXT

A>TYPE NOTES.TXT
Hello from a modern file.

A>EXIT
RETURNING TO UNIX.
```

`NOTES.TXT` is still the normal file you created on macOS or Linux. Emix did
not copy it into a disk image. In this example, the current folder became
CP/M drive A:.

Use a spare folder for your first session. Personality commands work on real
host files, so `ERA NOTES.TXT` really deletes that file after asking you to
confirm.

## 2. Personality, simulation, and emulation

These words are easy to mix up. Emix uses them in a specific way.

| Mode | What runs | What it is good for | Available now |
| --- | --- | --- | --- |
| Personality | Emix's Python code | Learning an old command language while working with modern files | CP/M, VMS, CMS |
| Emulator-backed application | A real historical program inside `RunCPM` | Using software such as `ED`, `TE`, or `MBASIC` | CP/M applications |
| Full-machine emulation | A whole old computer and operating system | Hardware, booting, devices, and complete system behaviour | Not provided by Emix |

### A personality recreates the command line

When you run `emix cpm`, there is no Z80 processor and no copy of CP/M in
memory. Emix reads `DIR`, runs its own Python implementation, and formats the
answer in a CP/M style.

The VMS and CMS personalities work the same way. They reproduce useful
commands, naming rules, prompts, and errors. They do not boot VMS or VM/CMS.

It is fair to say that a personality *simulates the interaction*. It does not
simulate the whole machine. Timing, hardware, memory layout, device drivers,
and most operating-system internals are outside its scope.

### A real application uses an emulator

When a configured CP/M personality launches `ED.COM` or `TE.COM`, the program
is real. [RunCPM](https://github.com/MockbaTheBorg/RunCPM) executes its Z80
instructions. Emix builds a private workspace around the emulator, gives the
guest a staged copy of your document, and reviews the result before anything
comes back.

`RunCPM` is the emulator. `ED` or `TE` is the application. Emix supplies the bridge
between them and your host files.

### Emix is not a full virtual machine

Emix does not currently boot CP/M, VMS, or CMS as complete operating systems.
It does not manage SIMH or another full-system emulator. If you need exact
hardware or a complete historical installation, use a specialist emulator.
Emix is aimed at the command-line experience and, where useful, individual
historical applications.

## 3. Install Emix

### Supported systems

Emix is tested in continuous integration on:

- macOS;
- Linux, including case-sensitive filesystems;
- Windows; and
- Python 3.11, 3.12, 3.13, and 3.14.

You need a normal terminal. On Windows, use **Windows Terminal** if you have
it — the classic console window works, but Emix has to ask it for permission
to use colour at all, and older builds may refuse.

Two things are missing on Windows and nowhere else:

- **Tab completion and command history** need the `readline` module, which
  Windows does not ship. Emix runs without them; you lose the completion that
  teaches you each system's vocabulary. Installing `pyreadline3` restores
  both.
- **Real CP/M applications** need RunCPM, which builds on Windows but is not
  yet covered by these instructions.

Emix will not run a `.bat` or `.cmd` from a personality prompt. Windows runs
batch files through its command processor, which would re-read your arguments
as shell syntax — and Emix never uses a shell. The personality reports the
failure in its own words and Emix explains why underneath, unless you are in
strict mode. Call the `.exe` directly, or use WSL.

The **green phosphor is off by default on Windows**, because Emix cannot find
out what colour your console is: there is no way to ask, and the answer the
console can give does not describe a Windows Terminal background. Rather than
paint green onto a light screen, Emix leaves it alone. Turn it on with
`--screen bright-green`, or put `screen = "bright-green"` in your settings.

If either matters to you, **WSL** gives you the Linux experience unchanged,
and Emix cannot tell the difference.

### Install with `uv` or `pipx`

```sh
uv tool install emix-shell
```

or:

```sh
pipx install emix-shell
```

The package is named `emix-shell`, but the command is `emix`:

```sh
emix --version
emix cpm
```

If `uv` says that `~/.local/bin` is missing from your `PATH`, run:

```sh
uv tool update-shell
```

Then open a new terminal.

### Keep it up to date

```sh
emix --update
```

Emix works out how this copy was installed and offers the command that
matches — `uv tool upgrade`, `pipx upgrade`, `pip install --upgrade`, or
`git pull` for a source checkout. It shows the command, asks, and only then
runs it; nothing is executed on a guess.

It also names the newest published version. That check is the only network
request Emix ever makes, and it happens only when you ask for an update. If
the package index cannot be reached, Emix says so rather than guessing.

### Run from a source checkout

```sh
git clone https://github.com/rdubar/emix
cd emix
./emix cpm
```

Emix has no runtime packages beyond the Python standard library.

## 4. Folders become historical drives

Without a mount option, the current folder becomes the first drive:

```sh
cd ~/Documents
emix cpm
```

You can be more explicit:

```sh
emix cpm --mount ~/Documents
emix vms --mount ~/Documents
emix cms --mount ~/Documents
```

The same folder receives a different historical name in each personality:

| Mount order | CP/M | VMS | CMS |
| --- | --- | --- | --- |
| First folder | `A:` | `DKA0:` | filemode `A` |
| Second folder | `B:` | `DKA100:` | filemode `B` |
| Third folder | `C:` | `DKA200:` | filemode `C` |

Mount options can be repeated:

```sh
emix cpm --mount ~/Documents --mount ~/src
```

Here, `~/Documents` is A: and `~/src` is B:.

Run one command without opening an interactive session with `-c`:

```sh
emix cpm --mount ~/Documents -c "DIR *.TXT"
emix vms --mount ~/Documents -c DIRECTORY
emix cms --mount ~/Documents -c LISTFILE
```

A failed command returns a non-zero process status, so this mode works in
scripts.

### Save your usual settings

Emix reads a configuration file from wherever your system keeps such things —
`~/.config/emix/emix.toml` on macOS and Linux, `%APPDATA%\emix\emix.toml` on
Windows. `EMIX_CONFIG` overrides it anywhere:

```toml
[emix]
personality = "cpm"
strict = false
screen = "bright-green"        # main text
hint-colour = "bright-yellow"  # Emix's own lines

[drives]
default = ["~/Documents"]
cpm = ["~/Documents", "~/src"]
```

Every setting is optional. Command-line options win over this file.

On Windows, **write paths in single quotes**:

```toml
[drives]
default = ['C:\Users\me\Documents']
```

TOML reads a backslash inside *double* quotes as an escape, so `"C:\Users\me"`
fails with a message about an invalid hex value — `\U` is the start of a
Unicode escape. Single quotes take the path exactly as written. Doubling the
backslashes or using forward slashes both work too. Emix says as much if you
get it wrong.

## 5. Choose a personality

The personalities share one file engine, but they teach different ways of
thinking about commands and filenames.

### The same job in three command languages

| Job | CP/M | VMS DCL | VM/CMS |
| --- | --- | --- | --- |
| List files | `DIR` | `DIRECTORY` | `LISTFILE` |
| Read a file | `TYPE NOTES.TXT` | `TYPE NOTES.TXT` | `TYPE NOTES TXT A` |
| Copy a file | `PIP COPY.TXT=NOTES.TXT` | `COPY NOTES.TXT COPY.TXT` | `COPYFILE NOTES TXT A COPY TXT A` |
| Rename a file | `REN NEW.TXT=OLD.TXT` | `RENAME OLD.TXT NEW.TXT` | `RENAME OLD TXT A NEW TXT A` |
| Delete a file | `ERA NOTES.TXT` | `DELETE NOTES.TXT;1` | `ERASE NOTES TXT A` |
| Run a host command | `UNIX command` | `SPAWN command` | `CMS command` |
| Leave | `EXIT` | `LOGOUT` | `LOGOFF` |

The differences are intentional. Emix is not translating everything into
Unix commands behind the scenes.

### CP/M 2.2: short commands and drive letters

Start it with:

```sh
emix cpm
```

CP/M was used on small 8-bit computers. Its command processor, the CCP, used
drive letters and short filenames. The prompt shows the active drive:

```text
A>DIR
A: LETTER_1 TXT A: NOTES    TXT A: PYPROJ_1 TOM

A>TYPE NOTES.TXT
hello

A>PIP BACKUP.TXT=NOTES.TXT
```

Things to remember:

- CP/M filenames are normally limited to eight characters, a dot, and three
  more characters.
- `PIP` and `REN` put the destination first: `NEW=OLD`.
- The original CCP had six built-in commands. Emix directly provides `DIR`,
  `ERA`, `REN`, `TYPE`, and `USER`. `SAVE` depended on a memory area Emix does
  not have, so it returns `SAVE?` and explains why when assistance is on.
- `PIP` and `STAT` were separate `.COM` programs on CP/M. The personality
  simulates their useful file behaviour; it is not running those binaries.
- User area 0 is the only user area currently modelled.

CP/M also has host-command fallthrough. If a word is not a CP/M or Emix
command, Emix tries it as a host executable without using a shell. This means
`ls` can run on macOS or Linux. Use `UNIX command` when you want to be clear
about leaving the CP/M vocabulary.

### VAX/VMS DCL: verbs, devices, and qualifiers

Start it with:

```sh
emix vms
```

DCL uses command verbs such as `DIRECTORY`, `COPY`, and `DELETE`. The prompt
is `$`, and mounted folders look like devices:

```text
$ DIRECTORY

Directory DKA0:[000000]

NOTES.TXT;1
REPORT.TXT;1

Total of 2 files.

$ DELETE NOTES.TXT
%DELETE-W-NOVER, explicit version number required
```

Things to remember:

- A verb can be shortened as long as the result is unambiguous. `DIR`, `DIRE`,
  and `DIRECTORY` refer to the same command.
- Options begin with `/`, as in `/SIZE`.
- Filenames display a version such as `;1`. Emix stores only one host file; it
  does not yet keep real VMS file versions.
- `DELETE` requires the displayed version number.
- VMS does not run unknown host commands automatically. Use `RUN` or `SPAWN`.

This is a DCL personality, not a booted OpenVMS system. RMS record formats,
accounts, processes, devices, and most DCL commands are not simulated.

### VM/CMS: three-part file IDs and `Ready;`

Start it with:

```sh
emix cms
```

CMS names a file with separate filename, filetype, and filemode words:

```text
LISTFILE
NOTES    TXT      A1
REPORT   TXT      A1
Ready; T=0.01/0.01 15:44:02

TYPE NOTES TXT A
hello
Ready; T=0.01/0.01 15:44:05
```

Things to remember:

- `NOTES TXT A` means the file `NOTES.TXT` on mounted filemode A.
- Listings show `A1`, following CMS style.
- There is no visible prompt. CMS prints `Ready;` after a successful command
  and `Ready(nnnnn);` after an error.
- Unknown words do not fall through to the host. Use `CMS command` explicitly.

This personality does not boot VM or provide a virtual mainframe. `EXEC` and
`XEDIT` are not implemented.

## 6. Modern filenames in old systems

Old naming rules do not fit files such as `pyproject.toml` or
`Meeting notes.txt`. Emix creates a reversible display name:

```text
A>DIR
A: NOTES    TXT A: PYPROJ_1 TOM A: REPORT   TXT

A>TYPE PYPROJ_1.TOM
[build-system]
requires = ["hatchling"]
```

The real file stays named `pyproject.toml`. Emix does not rename it. The alias
only gives the personality a name it can display and accept again.

Name matching ignores case when there is one clear answer. On a
case-sensitive Linux folder containing both `readme.txt` and `README.TXT`,
Emix reports the ambiguity instead of choosing one.

Paths are checked after symbolic links are resolved. A link that points
outside a mounted folder cannot be used to escape the drive.

## 7. Help without changing the old output

Interactive sessions start with assistance enabled. Emix prints the original
style of error first, then adds a clearly marked hint:

```text
$ ls
%DCL-W-IVVERB, unrecognized command verb - check validity and spelling
Emix: OpenVMS has no ls. To list the files, use DIRECTORY.

$ DELETE FOO.TXT
%DELETE-W-NOVER, explicit version number required

$ EXPLAIN
Emix: DELETE needs an explicit version, as in FILE.TXT;1.
```

The rules are simple:

1. The historical-style response comes first and is not rewritten.
2. Every added hint line begins with `Emix:`.
3. A suggestion is never executed for you. You decide what to type next.

Useful shared commands include:

- `HELP` — list commands or explain one command;
- `EXPLAIN` — describe the previous command or error;
- `ABOUT` — say what Emix is and which personality is active;
- `CREDIT` — show authorship and licence information;
- `APPS` — list applications available to the current personality; and
- `STRICT ON` — turn off all Emix-added assistance.

CP/M did not originally have `HELP`; VMS did. Emix marks its additions so the
difference remains visible.

### Strict mode, colour, and scripts

Use `STRICT ON` inside a session or start with `--strict`:

```sh
emix vms --strict
```

Scripts and pipes are strict by default. For a predictable one-command run,
use `-c` with `--strict`; output sent through a pipe becomes strict
automatically and contains no terminal colour codes.

Colour comes in two parts. The **screen** is the main text: green phosphor
where Emix can tell the terminal is dark, and nothing at all where it cannot,
since green on a light background is unreadable. Set it yourself with
`--screen amber` or `EMIX_SCREEN=amber`, and `--screen none` for plain text on
a dark terminal.

**Hints** are Emix's own voice, and must not be mistaken for the machine's.
They are amber against the green — unless the screen is itself amber, when
there is no hue left to separate the two and they become white instead.

Both defaults use the bright half of the ANSI sixteen. Many colour schemes
render the dim green as a muddy yellow-green that sits too close to amber to
tell apart at a glance. Set your own with `--hint-colour bright-white` or
`EMIX_HINT_COLOUR=bright-white`; every colour has a `bright-` twin.

Set `NO_COLOR=1` to disable both, and terminal colour probing with them.

Tab completion and per-personality command history remain available in strict
mode because they affect what you type, not what Emix runs.

## 8. Run real CP/M applications

This part is optional. The personalities work without an emulator.

Real CP/M applications currently use RunCPM. Emix does not bundle RunCPM,
CP/M, or application binaries. Install only software you have permission to
use.

### The short way: ask an AI agent

Every step below is public, scripted and checkable — a good chore to hand over
if you already use a coding agent. Ask it:

> Clone https://github.com/rdubar/emix, follow its AGENTS.md section "Setting
> this up for a user who asked an agent to do it", and verify with a real
> `emix open` session before telling me it works.

`AGENTS.md` holds the details it needs, including the build flag that is easy
to miss. Read what it proposes before letting it run: it is building software
on your machine. It sets up the emulator and its sample disk only — other
CP/M software is yours to supply, and Emix will drive it once you write a
profile.

Otherwise the steps are below, and take about ten minutes.

### Build RunCPM on macOS or Linux

You need Git, `make`, a C compiler, and `unzip`. On macOS, the Xcode Command
Line Tools provide the compiler and `make`. On Linux, install your
distribution's normal build tools.

Clone RunCPM:

```sh
git clone https://github.com/MockbaTheBorg/RunCPM ~/dev/RunCPM
cd ~/dev/RunCPM/RunCPM
```

Build on macOS:

```sh
make macosx CCP=INTERNAL build
```

Build on Linux:

```sh
make posix CCP=INTERNAL build
```

Then unpack the sample A: drive:

```sh
cd ~/dev/RunCPM
unzip -o DISK/A0.zip -d DISK
```

`CCP=INTERNAL` is important. Other RunCPM CCP choices need an extra CCP binary
at runtime. If RunCPM changes its build process, follow the instructions in
its own repository.

### Add an application profile

Create `apps.toml` beside your settings file — `~/.config/emix/apps.toml`
on macOS and Linux. `emix apps` prints the right path for your machine along
with a template:

```toml
[app.ed-cpm]
system = "cpm"
command = "ED"
backend = "runcpm"
program = "ED.COM"
application = "~/dev/RunCPM/DISK/A/0"
executable = "~/dev/RunCPM/RunCPM/RunCPM"
terminal = "vt100"
timeout = 60
notes = """
ED is Digital Research's CP/M line editor. It does not use a full screen.
  #A  read the file     I  insert text     Control-Z  finish inserting
  #T  show the buffer   E  save and exit   Q          quit
"""
exit = "Use E to save and exit, or Q to leave without saving."
```

Check the profile:

```sh
emix apps
```

This lists configured applications, verifies the emulator path, and reports a
missing application drive.

### Start an application

From a CP/M personality:

```text
A>ED NOTES.TXT
```

An editor may also create a new file:

```text
A>ED NEW.TXT
```

Or open a host file directly:

```sh
emix open ~/Documents/NOTES.TXT --with ed-cpm
```

Useful `emix open` options are:

- `--yes` or `-y` — copy changes back without asking; use this carefully;
- `--keep` — keep the private session workspace after a successful run; and
- `--stay` — remain at the real CP/M prompt after the application exits.

When `EXIT.COM` is present, Emix normally chains it after the application, so
leaving the application returns you to Emix instead of dropping you at an
unfamiliar guest prompt.

### What a document session does

For one application run, Emix:

1. creates a private session folder;
2. copies only the selected document into guest drive B:;
3. copies the configured application drive into guest drive A:;
4. writes a manifest before launching the emulator;
5. runs the real program in RunCPM;
6. compares the guest files with the staged originals;
7. reports modified, created, deleted, and ignored files; and
8. asks before copying approved changes to the host.

Typical output looks like this:

```text
A>TE LETTER.TXT
Preparing te-cpm...
  ESC opens the menu: S save, A save-as, X exit, H help.
  Movement is the WordStar diamond: ^E up, ^X down, ^S left, ^D right.
LETTER.TXT is available as B:LETTER.TXT

    [ the real editor runs ]

DOCUMENT SESSION COMPLETE

  MODIFIED  LETTER.TXT
  IGNORED   TE.BKP  (the application's own backup)

Save these changes to the host? [Y/n]
```

Editor backup and scratch files are shown but are not copied into your
documents folder. If the guest deletes the staged document, Emix reports the
deletion but does not delete the host original.

If the emulator crashes, times out, is interrupted, or exits unexpectedly,
Emix does not copy guest output back. It keeps the workspace and prints its
path.

### A short ED example

ED is a line editor, not a screen editor:

```text
B0>A:ED NEW.TXT

NEW FILE
     : *I
    1:  Dear Gary,
    2:  The BDOS is a triumph.
    3:
     : *E
```

### A short MBASIC example

With an MBASIC profile, a real session can look like this:

```text
BASIC-85 Rev. 5.29
[CP/M Version]
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

Application profiles are a good place to record keys and exit commands that a
new user would not guess.

## 9. Safety: know which mode you are in

Personality commands and emulator-backed applications handle files
differently.

| Action | When the host file changes |
| --- | --- |
| Personality command such as `PIP`, `COPY`, or `ERASE` | Directly, as soon as the command runs and any confirmation is accepted |
| Real application such as ED or TE | After a staged session, a change report, conflict checks, and confirmation |

### Personality safety

- Every file path stays inside a mounted drive after symbolic links are
  resolved.
- Ambiguous case matches are refused.
- Destructive commands ask for confirmation. Only `Y` or `YES` means yes.
- Unknown CP/M commands may run as host executables, but Emix never starts a
  shell. Characters such as `|`, `>`, `&&`, `$VAR`, and backticks are passed as
  ordinary arguments, not interpreted as shell operators.
- VMS and CMS never run an unknown word automatically. Their explicit host
  commands are `RUN`/`SPAWN` and `CMS`.

### Application-session safety

- The guest sees the staged document and copied application drive, not the
  rest of the document's folder.
- A failed guest never reaches the copy-back step.
- Emix checks whether the host file changed while the guest was open. It
  checks before writing and once more immediately before each replacement.
- If a commit fails, Emix attempts to roll back the whole set. It reports any
  file it could not restore, keeps available originals, and always keeps the
  workspace.

There is one important limit. Conflict detection is best-effort, not a lock.
A host write that lands in the very small gap between the last check and the
final rename can still be lost. After a successful commit, the temporary
workspace is removed. Avoid editing the same document in another program while
it is open in a guest application.

The exact transaction contract and recovery design are documented in
[APPLICATIONS.md](APPLICATIONS.md).

RunCPM itself is trusted host software. Emix protects host files from the guest
program's view of the drives; it is not a sandbox against a malicious emulator.

## 10. What is faithful, changed, or missing

### Faithful parts

- CP/M drive letters, short names, destination-first `REN` and `PIP`, and the
  built-in/transient distinction.
- DCL verbs, unambiguous abbreviations, qualifiers, and the explicit-version
  rule for `DELETE`.
- CMS three-part file IDs and `Ready;` responses.
- Error messages and command output shaped for each personality.
- Real Z80 application execution when using the RunCPM backend.

### Changes made for modern host files

- Destructive commands confirm more often than the original systems did.
- Long filenames receive reversible aliases instead of being silently
  truncated.
- VMS files display `;1`, but Emix stores only one host copy.
- Commands added by Emix are labelled and their output is kept separate from
  historical-style output.
- Guest documents are staged and reviewed instead of exposing a whole folder
  directly to an external emulator.

### Not built yet

- CP/M user areas other than 0.
- A working CP/M `SAVE`; Emix has no Transient Program Area to copy.
- Real VMS file versions and full VMS directory syntax.
- CMS `EXEC` and `XEDIT`.
- Real VMS or CMS applications.
- A built-in Z80 core or a complete machine emulator.
- Durable session recovery and an `emix sessions` command.

## 11. Common problems

### `emix: command not found`

Run `uv tool update-shell`, open a new terminal, and try `emix --version`.

### Emix is out of date

Run `emix --update`. It reports the installed version, the newest published
one, and the command that would update this particular copy.
You can also use `uvx --from emix-shell emix cpm` without installing the
command.

### `No applications configured`

The personalities do not need application profiles. If you want real CP/M
software, run `emix apps` — it prints both the path it wants and a
template to put there.

### RunCPM is unavailable

Check the `executable` path in `apps.toml`. It should point to the built
RunCPM executable, not its source folder. Also check that `application` points
to the extracted `DISK/A/0` directory.

### The screen layout looks wrong

Many CP/M programs assume an 80-column VT100-style terminal. Enlarge the
terminal and check the profile's `terminal`, `columns`, and `rows` values.

### TE changed tabs or unusual characters

TE does not preserve every byte. It expands tabs and may replace characters it
cannot represent. Use a scratch copy for tab-indented source code or any file
where exact bytes matter.

### Emix kept a workspace

This happens after guest failure, a copy-back conflict, a declined commit, or
when `--keep` is set. Emix prints the path. Check the host files and anything
under the workspace's `rollback/` folder before deleting it.

The workspace currently lives in the operating system's temporary directory.
It is useful evidence, not durable backup storage, and Emix does not prune it
automatically.

### Hints or colours are not wanted

Use `--strict`, `STRICT ON`, or `NO_COLOR=1`, depending on whether you want to
remove assistance, colour, or both. To keep the hints but lose the green,
`--screen none` leaves the main text as your terminal's own colour.

## 12. Credits and further reading

- [RunCPM](https://github.com/MockbaTheBorg/RunCPM), by Marcelo Dantas, runs
  the real CP/M applications used by the current backend.
- TE, by Miguel Garcia / FloppySoftware, is the full-screen CP/M editor used in
  the examples.
- Digital Research created CP/M and tools such as ED, PIP, STAT, and DDT.
- DEC created VMS and DCL; IBM created VM/CMS.

Emix was created by Roger Dubar and is released under the MIT License. The
`CREDIT` command shows the same information inside any personality.

For implementation details about the real-application bridge, read
[APPLICATIONS.md](APPLICATIONS.md). Future work is tracked in
[ROADMAP.md](ROADMAP.md), and less settled ideas live in [IDEAS.md](IDEAS.md).

Bug reports and historical corrections are welcome at
<https://github.com/rdubar/emix/issues>.
