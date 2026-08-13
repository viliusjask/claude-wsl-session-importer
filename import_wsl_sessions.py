#!/usr/bin/env python3
"""Import Claude Code CLI sessions (WSL) into the Claude Desktop app's session list.

Claude Desktop (Windows) lists sessions from small metadata files at
  %APPDATA%\\Claude\\claude-code-sessions\\<account>\\<org>\\local_<uuid>.json
Entries created by Desktop for WSL-backed sessions carry `wslConfig` and
`sshRemoteTranscriptPath`, which point straight at a transcript INSIDE the WSL
filesystem — no copying required. Headless/CLI sessions never get such an
entry, so they are invisible in Desktop. This tool synthesizes one per CLI
session, modeled on a genuine Desktop-created entry.

Run FROM WSL. Dry-run by default; `--apply` refuses while Desktop is running.
Additive only: it never modifies or deletes existing metadata or transcripts.

Usage:
  python3 import_wsl_sessions.py --list                 # untracked CLI sessions
  python3 import_wsl_sessions.py --session bec1564a     # dry-run one session
  python3 import_wsl_sessions.py --session bec1564a --apply
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

CLI_PROJECTS = Path.home() / ".claude" / "projects"
TASKLIST = "/mnt/c/Windows/System32/tasklist.exe"


@dataclass
class SessionFacts:
    cli_session_id: str
    transcript: Path
    cwd: str | None = None
    title: str | None = None
    first_ms: int | None = None
    last_ms: int | None = None
    model: str | None = None
    effort: str | None = None
    permission_mode: str | None = None
    user_turns: int = 0


def iso_to_ms(ts: str) -> int:
    return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)


def read_facts(transcript: Path) -> SessionFacts:
    f = SessionFacts(cli_session_id=transcript.stem, transcript=transcript)
    fallback_title = None
    with open(transcript, errors="replace") as fh:
        for line in fh:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = e.get("timestamp")
            if ts:
                ms = iso_to_ms(ts)
                f.first_ms = f.first_ms or ms
                f.last_ms = ms
            if e.get("type") == "ai-title" and e.get("aiTitle"):
                f.title = e["aiTitle"]
            f.cwd = e.get("cwd") or f.cwd
            f.effort = e.get("effort") or f.effort
            f.permission_mode = e.get("permissionMode") or f.permission_mode
            msg = e.get("message") or {}
            if msg.get("model"):
                f.model = msg["model"]
            if e.get("type") == "user" and not e.get("isSidechain") and not e.get("isMeta"):
                content = msg.get("content")
                text = content if isinstance(content, str) else next(
                    (b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text"), "")
                if text.strip() and not text.lstrip().startswith("<"):
                    f.user_turns += 1
                    fallback_title = fallback_title or " ".join(text.split())[:80]
    f.title = f.title or fallback_title
    return f


def find_metadata_dir() -> Path:
    """The Desktop app's <account>/<org> metadata dir — the one holding local_*.json."""
    hits = glob.glob("/mnt/c/Users/*/AppData/Roaming/Claude/claude-code-sessions/*/*/")
    if not hits:
        sys.exit("No Claude Desktop claude-code-sessions directory found under /mnt/c — "
                 "is the Desktop app installed on Windows?")
    if len(hits) > 1:  # account/org rotation leaves stale pairs; take the most recently used
        hits.sort(key=os.path.getmtime, reverse=True)
    return Path(hits[0])


def known_cli_ids(meta_dir: Path) -> set[str]:
    ids = set()
    for p in meta_dir.glob("local_*.json"):
        try:
            ids.add(json.loads(p.read_text())["cliSessionId"])
        except (json.JSONDecodeError, KeyError, OSError):
            continue
    return ids


def desktop_running() -> bool:
    """Fail closed: any error counts as running."""
    try:
        out = subprocess.run([TASKLIST, "/FI", "IMAGENAME eq claude.exe"],
                             capture_output=True, text=True, timeout=15).stdout
        return "claude.exe" in out.lower()
    except (OSError, subprocess.TimeoutExpired):
        return True


def build_entry(f: SessionFacts) -> dict:
    if f.first_ms is None or f.last_ms is None:
        # A null timestamp in metadata is documented to blank Desktop's whole
        # session list — refuse rather than write one.
        sys.exit(f"REFUSED {f.cli_session_id}: transcript has no parseable timestamps.")
    if not f.cwd:
        sys.exit(f"REFUSED {f.cli_session_id}: transcript has no cwd record.")
    return {
        "sessionId": f"local_{uuid.uuid4()}",
        "cliSessionId": f.cli_session_id,
        "cwd": f.cwd,
        "originCwd": f.cwd,
        "lastFocusedAt": f.last_ms,
        "createdAt": f.first_ms,
        "lastActivityAt": f.last_ms,
        "model": f.model or "claude-sonnet-5",
        "effort": f.effort or "high",
        "isArchived": False,
        "title": f.title or f"CLI session {f.cli_session_id[:8]}",
        "titleSource": "auto",
        "permissionMode": f.permission_mode or "default",
        "remoteMcpServersConfig": [],
        "wslConfig": {"distro": os.environ.get("WSL_DISTRO_NAME", "Ubuntu")},
        "sshRemoteTranscriptPath": str(f.transcript),
        "completedTurns": f.user_turns,
        "alwaysAllowedReasons": [],
        "sessionPermissionUpdates": [],
        "spawnSeed": {},
    }


def write_entry(meta_dir: Path, entry: dict) -> Path:
    dest = meta_dir / f"{entry['sessionId']}.json"
    tmp = dest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(entry, indent=2))
    json.loads(tmp.read_text())  # verify what landed on the Windows FS parses
    os.replace(tmp, dest)
    return dest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--session", action="append", default=[],
                    help="CLI session id prefix to import (repeatable)")
    ap.add_argument("--list", action="store_true", help="list untracked CLI sessions and exit")
    ap.add_argument("--min-kb", type=int, default=10,
                    help="--list: hide transcripts smaller than this (default 10)")
    ap.add_argument("--apply", action="store_true", help="actually write (default: dry-run)")
    args = ap.parse_args()

    meta_dir = find_metadata_dir()
    known = known_cli_ids(meta_dir)
    transcripts = [Path(p) for p in glob.glob(str(CLI_PROJECTS / "*" / "*.jsonl"))]

    if args.list:
        rows = sorted((p for p in transcripts if p.stem not in known),
                      key=os.path.getmtime, reverse=True)
        for p in rows:
            kb = p.stat().st_size // 1024
            if kb < args.min_kb:
                continue
            print(f"{p.stem}  {kb:>6} KB  {p.parent.name}")
        return

    if not args.session:
        ap.error("pass --session <prefix> (repeatable) or --list")

    targets = []
    for prefix in args.session:
        matches = [p for p in transcripts if p.stem.startswith(prefix)]
        if len(matches) != 1:
            sys.exit(f"--session {prefix}: {len(matches)} matches, need exactly 1.")
        if matches[0].stem in known:
            sys.exit(f"--session {prefix}: already tracked by Desktop, nothing to do.")
        targets.append(matches[0])

    entries = [build_entry(read_facts(t)) for t in targets]
    for entry in entries:
        print(json.dumps(entry, indent=2))

    if not args.apply:
        print(f"\nDRY-RUN: {len(entries)} entr{'y' if len(entries) == 1 else 'ies'} "
              f"would be written to {meta_dir}\nRe-run with --apply to write.")
        return
    if desktop_running():
        sys.exit("REFUSED: Claude Desktop is running (claude.exe found). "
                 "Quit it fully (system tray too), then re-run with --apply.")
    for entry in entries:
        print(f"wrote {write_entry(meta_dir, entry)}")
    print("Done. Start Claude Desktop and check the session list. "
          "To undo, delete the file(s) above.")


if __name__ == "__main__":
    main()
