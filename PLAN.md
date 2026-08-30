# Emix project plan

## Aim

Create a pleasant retro-computing shell that remains useful on a current Mac
or Linux machine. Emix should reproduce the vocabulary and feel of historical
systems without pretending to provide binary-accurate hardware or operating
system emulation.

## Product principles

1. **The host stays real.** Files and programs belong to Unix; personalities
   provide another way to interact with them.
2. **Authenticity should teach.** Prompts, syntax, help, error messages, and
   display formats should be recognisable and documented.
3. **Safety is visible.** Destructive commands confirm, file mappings are
   bounded, and host-command execution does not silently invoke a shell.
4. **Personalities share an engine.** CP/M, VMS, and later systems should use
   common host, terminal, and command facilities without becoming one large
   conditional parser.
5. **Mac and Pi are first-class.** Keep the base install small and portable.

## Milestone 0.1: working CP/M shell

- [x] Interactive `A>` prompt
- [x] Current host directory exposed as drive A:
- [x] `DIR`, `TYPE`, `COPY`, `REN`, and confirmed `ERA`
- [x] `STAT`, `HELP`, `VER`, `CLS`, and exit commands
- [x] Safe direct execution of host programs
- [x] Case-insensitive CP/M-style lookup on case-sensitive hosts
- [x] Automated tests and source-checkout launcher

## Milestone 0.2: convincing CP/M personality

- [ ] Map additional host directories to drives B: through P:
- [ ] Add `MOUNT` and persistent drive configuration
- [ ] Add CP/M user areas as an optional view
- [ ] Present reversible 8.3 aliases without renaming host files
- [ ] Improve columnar `DIR` output and CP/M-style file attributes
- [ ] Add command history and completion without losing the period feel
- [ ] Test interactively on an M3 Mac and Raspberry Pi 5

## Milestone 0.3: reusable personality engine

- [ ] Extract shared REPL, host execution, filesystem mapping, and formatting
- [ ] Define a small personality interface rather than a data-only command map
- [ ] Add golden-session tests for prompts, errors, and command output
- [ ] Decide how personality-specific configuration is stored
- [ ] Package a convenient user-level installer

## Milestone 0.4: VAX/VMS personality

- [ ] Implement DCL-style command verbs and unambiguous abbreviation
- [ ] Translate `DIRECTORY`, `TYPE`, `COPY`, `DELETE`, and `SET DEFAULT`
- [ ] Render Unix paths as device and bracketed-directory specifications
- [ ] Model symbols and logical names
- [ ] Explore safe, optional host-backed file versions such as `REPORT.TXT;3`
- [ ] Add an authentic help hierarchy and error-message format

## Questions to answer through use

- Is Emix mainly a playful daily shell, an educational environment, or both?
- Should host directories be visible, hidden behind aliases, or selectable?
- How authentic should output be when authenticity obscures useful host data?
- Should a personality be able to provide small built-in programs as well as
  commands?
- Where is the boundary between a compatibility shell and a true emulator?

The immediate next step is to use the 0.1 shell for ordinary file browsing on
both target machines and record the first pieces of friction before expanding
the architecture.

