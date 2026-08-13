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
(`claude -p`) and plain terminal sessions are the intended targets. A session
that was ever resumed in VS Code counts as cloud-synced (the tool keys off the
transcript's most recent `entrypoint`).

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
- Synthesized entries omit Desktop-internal fields with unknown semantics
  (`sshRemoteProcessId`, `bridgeSessionIds`). Browsing history is the goal;
  **resuming an imported session from Desktop is untested** — prefer
  `claude --resume` in the CLI for that.
- Entries are local to the Windows machine; they do not sync to claude.ai.
