# Emix Shell

Emix lets a modern Unix machine pretend to be an older computer. It is not a
CPU emulator and it does not run historical binaries: it presents historical
commands and conventions while using ordinary host files and programs beneath
them.

The first personality is a deliberately small CP/M-inspired shell. It runs on
macOS and Linux, including Apple silicon Macs and Raspberry Pi, and has no
third-party runtime dependencies.

## Try it

Python 3.10 or newer is required.

```sh
cd ~/dev/emix
./emix cpm
```

The current directory becomes CP/M drive `A:`. Use `--root` to expose a
different directory:

```sh
./emix cpm --root ~/Documents
```

An example session:

```text
EMIX 0.1.0
CP/M 2.2 PERSONALITY
A: /Users/rob/dev/emix
TYPE HELP FOR AVAILABLE COMMANDS.
A>DIR *.MD
A>TYPE README.MD
A>COPY README.MD NOTES.TXT
A>REN OLDNOTES.TXT=NOTES.TXT
A>UNIX uname -a
A>EXIT
RETURNING TO UNIX.
```

Install the `emix` command into a virtual environment if preferred:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
emix cpm
```

## Commands

| Emix command | Effect |
| --- | --- |
| `DIR [PATTERN]` | List files, with case-insensitive wildcards |
| `TYPE FILE` | Display a UTF-8 text file |
| `COPY SOURCE DEST` | Copy a file |
| `REN NEW=OLD` | Rename a file in CP/M argument order |
| `ERA PATTERN` | Erase matching files after confirmation |
| `STAT` | Show free host disk space |
| `UNIX COMMAND [ARGS]` | Run a host executable explicitly |
| `CLS` | Clear the terminal |
| `VER` | Show the Emix version |
| `HELP [COMMAND]` | Show help |
| `EXIT`, `BYE`, `QUIT` | Return to Unix |

Unknown commands are offered directly to the host as executables, so commands
such as `python3 hello.py` work without the `UNIX` prefix. Emix separates the
command into arguments and never invokes a shell implicitly. Consequently,
shell operators such as pipes, redirection, `&&`, and variable expansion are
not interpreted. Exit Emix when a full Unix shell is wanted.

For safety, CP/M file operations are confined to the selected drive root and
do not accept directory separators. `ERA` always requests confirmation. Files
are real host files: changing or erasing one in Emix changes or erases it on
the host too.

## Development

Run the tests from a checkout:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The implementation currently uses only Python's standard library. The command
engine lives in `src/emix/cpm.py`; `src/emix/cli.py` selects and starts a
personality.

See [PLAN.md](PLAN.md) for the intended path from this proof of concept to a
useful multi-personality shell.

## Status

Emix is an early experiment. Its CP/M personality favours safe, useful host
integration over exact emulation. In particular, it does not yet enforce 8.3
filenames, emulate CP/M user areas, mount multiple drives, or execute CP/M
binaries.

