# claude-wsl-session-importer

Make Claude Code **CLI sessions that live inside WSL** (including headless
`claude -p` runs) visible in the **Claude Desktop app's** session list on
Windows — no transcript copying, no forked snapshots.

## Why this exists

Claude Code CLI sessions and the Desktop app's session list are separate
worlds: the CLI writes transcripts to `~/.claude/projects/…/<session>.jsonl`
(inside WSL), while Desktop lists only sessions it has a metadata entry for,
under `%APPDATA%\Claude\claude-code-sessions\<account>\<org>\local_*.json`.
Headless and terminal CLI sessions never get such an entry, so they are
invisible in Desktop.

Existing recovery tools (e.g. claude-code-session-recovery) link metadata to
transcripts by ID against the *Windows-side* `~\.claude\projects` only — for
WSL transcripts they require a manual copy that immediately goes stale.

### Where the files actually live

WSL and Windows have **separate home directories**, so "`~/.claude`" means two
different places depending on which side you are on:

| Session started from | Transcript written to | Visible in Desktop by default |
|---|---|---|
| CLI inside WSL (`claude`, `claude -p`, tmux) | `\\wsl.localhost\<distro>\home\<user>\.claude\projects\<slug>\` | ❌ no |
| VS Code extension with the window connected to WSL | same WSL path (the extension runs in the WSL server) | ✅ yes — via **account sync**, not the local files |
| CLI on Windows (PowerShell/cmd) | `C:\Users\<user>\.claude\projects\<slug>\` | ❌ no (that's what the native importer scans) |
| Desktop opening a WSL session | authoritative copy stays in WSL; Desktop mirrors it to `C:\Users\<user>\.claude\projects\ssh-<sessionId>\` | ✅ yes |

Two independent mechanisms make a session appear in Desktop, and only one of
them involves your local files:

1. **Account sync** — the VS Code extension and Desktop register their
   sessions with your account, so they show up on any signed-in surface
   regardless of which filesystem the transcript sits on. This is why
   extension sessions appear even though their transcripts are in WSL.
2. **The local metadata index** — `local_*.json` files describing sessions on
   *this* machine. Nothing writes these for CLI sessions, which is the gap
   this tool fills.

Desktop treats a WSL distro as a **remote host** (note the `ssh-` prefix and
the `sshRemote*` fields), which is exactly why the trick below works: the
metadata may point at a path that does not exist on Windows at all.

## Prior art: the native import feature

Newer Claude Desktop builds (~July 2026) have **Help → Troubleshooting →
"Import Claude Code CLI sessions…"** (see
[claude-code#28791](https://github.com/anthropics/claude-code/issues/28791)).
**Try that first** — if it finds your sessions, you don't need this tool.
Reasons it may still earn its place:

- **WSL transcripts** — on Windows Desktop v1.30096.0 the native importer
  reported *"No CLI sessions to import"* twice while un-imported WSL sessions
  existed on disk (one of them in a folder Desktop already had sessions for,
  ruling out folder trust as the whole story); this tool then imported them
  successfully (2026-08-14). Structurally this is expected: the WSL
  transcripts are not under the Windows user profile the importer scans —
  see the table above.
- **Selectivity + dedup** — the native import is all-or-nothing; this tool
  imports chosen sessions and refuses cloud-synced VS Code sessions that
  would otherwise appear twice.
- **Scriptability** — usable from cron/CI/agent workflows, e.g. auto-indexing
  headless `claude -p` runs.

The insight this tool is built on: entries Desktop itself creates for
WSL-backed sessions carry two extra fields —

```json
"wslConfig": { "distro": "Ubuntu" },
"sshRemoteTranscriptPath": "/home/<user>/.claude/projects/<slug>/<id>.jsonl"
```

— i.e. Desktop can already resolve a transcript **inside the WSL filesystem**.
This tool synthesizes exactly such an entry for any CLI session, modeled on a
genuine Desktop-created one.

## Usage (run from WSL)

```bash
python3 import_wsl_sessions.py --list                  # untracked CLI sessions
python3 import_wsl_sessions.py --session <id-prefix>   # dry-run: prints the entry
python3 import_wsl_sessions.py --session <id-prefix> --apply
```

Requires Python 3.10+, stdlib only.

## Safety model

- **Dry-run by default.** `--apply` is the only writing path.
- **Additive only.** Creates new `local_*.json` files; never edits or deletes
  existing metadata, and never touches transcripts.
- **Refuses while Desktop runs** (`tasklist` probe, fails closed).
- **Refuses transcripts without parseable timestamps** — a null `createdAt`
  is known to blank Desktop's entire session list.
- **Skips sessions Desktop already tracks** (matched by `cliSessionId`).
- **Undo:** delete the printed `local_*.json` file(s).

## Which sessions it imports

Only sessions that are actually invisible in Desktop. Sessions started from
the **VS Code extension** (`entrypoint: claude-vscode`) already reach Desktop
through account cloud sync — importing them would list the same session twice,
so the tool refuses them unless you pass `--include-vscode`. Headless
(`claude -p`) and plain terminal sessions are the intended targets.

**This detection is a heuristic with a known false positive.** The label comes
from `CLAUDE_CODE_ENTRYPOINT`, which a `claude` process **inherits from its
parent**. A headless run spawned by the VS Code extension itself (e.g. an
agent running `claude -p`) is therefore labelled `claude-vscode` even though
nothing syncs it. Ordinary terminal launches — including `tmux` started by
hand — normally record `cli`/`sdk-cli` and are unaffected. No on-disk field
reliably separates the two (checked across ~50 transcripts: `trackingPath`,
snapshot keys and UI entry types all cross-cut). So the tool errs toward
skipping and tells you how to override. If a session isn't in Desktop's
sidebar, `--include-vscode` is safe — and a wrong import is undone by
deleting one file.

## Grouping in the sidebar

Desktop groups locally-imported entries **by their cwd path**, while
cloud-synced sessions in the same repo group **by the GitHub repo**. If both
kinds exist for one repo you'll see two adjacent groups with the same repo
name, disambiguated by path vs. owner (e.g. `myrepo · /home/user/projects`
and `myrepo · owner`). Cosmetic only; merging them would require
Desktop-internal fields that aren't documented.

## Caveats

- **Experimental.** Validated against the metadata format of Claude Desktop
  as of 2026-08; the format is undocumented and may change.
- **Resuming an imported session from Desktop works** (verified 2026-08-14,
  Desktop v1.30096.0, Ubuntu-on-WSL2): opening an imported headless session
  and sending a message appended to the **same** WSL transcript — no fork.
  Desktop filled in the one field this tool omits (`sshRemoteProcessId`) by
  itself on first open, and kept `wslConfig` and `sshRemoteTranscriptPath`
  intact. It also keeps a byte-identical mirror at
  `C:\Users\<user>\.claude\projects\ssh-<sessionId>\` (verified by md5); the
  WSL file remains the one that grows. Back up the `.jsonl` before your first
  try anyway.
- Entries are local to the Windows machine; they do not sync to claude.ai.
