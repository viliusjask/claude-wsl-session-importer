# claude-wsl-session-importer

Makes Claude Code CLI sessions that ran **inside WSL** — including headless
`claude -p` runs — show up in the **Claude Desktop app** on Windows. You can
read them and continue them there. Nothing is copied or duplicated.

## Why the built-in import doesn't cover this

Desktop has **Help → Troubleshooting → "Import Claude Code CLI sessions…"**.
Try it first. It scans `C:\Users\<you>\.claude\projects\`, but WSL has its own
home directory, so sessions you ran in WSL are in
`\\wsl.localhost\<distro>\home\<you>\.claude\projects\` and it reports
"No CLI sessions to import".

(VS Code extension sessions *do* appear in Desktop even when the window is
connected to WSL. That's not about which account you're signed in with — the
CLI uses the same one. The extension uploads its sessions to your account, so
any signed-in surface can list them; you can see them on claude.ai in a
browser too. The plain CLI authenticates to call the API but never registers
the session anywhere, so nothing outside that machine knows it exists.)

## How it works

Desktop lists a local session when a small metadata file describes it:
`%APPDATA%\Claude\claude-code-sessions\<account>\<org>\local_<uuid>.json`.
Entries Desktop writes for WSL-backed sessions point *into* WSL:

```json
"wslConfig": { "distro": "Ubuntu" },
"sshRemoteTranscriptPath": "/home/you/.claude/projects/<slug>/<id>.jsonl"
```

Desktop treats a distro like a remote host, so this works fine. The script
reads a CLI transcript (title, model, timestamps, cwd) and writes one such
entry for it. That's the whole trick.

## Usage — run from WSL, Python 3.10+, stdlib only

```bash
python3 import_wsl_sessions.py --list                  # what's importable
python3 import_wsl_sessions.py --session <id-prefix>   # dry run
python3 import_wsl_sessions.py --session <id-prefix> --apply
```

Dry-run by default. Only ever creates new metadata files — never edits or
deletes anything, never touches transcripts. Refuses to write while Desktop is
running. Undo = delete the file it printed.

VS Code sessions are skipped by default (they're already in Desktop via sync,
so importing would duplicate them); `--include-vscode` overrides. The label
comes from an inherited env var, so it's occasionally wrong — if a session
isn't in your sidebar, the override is safe.

## Notes

- Verified on Desktop v1.30096.0 with Ubuntu-on-WSL2, 2026-08. The metadata
  format is undocumented and could change.
- Resuming an imported session from Desktop works: it appends to the same WSL
  transcript. Desktop mirrors a copy to `C:\Users\<you>\.claude\projects\ssh-<id>\`,
  but the WSL file stays the live one. Back it up before your first try.
- Imported entries are local to that Windows machine; they don't sync to claude.ai.
