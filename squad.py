#!/usr/bin/env python3
"""Sync coding-agent skills and instructions across machines.

    python squad.py sync [--as NAME] [--dry-run]   pull, then install skills + instructions here
    python squad.py autosync on|off                 run sync every 2 minutes in the background
    python squad.py new [TEMPLATE] [DEST]           copy a template (no name: list them)

The folder path is the routing. Every folder between skills/ and a skill is a
filter, and all of them must match this machine:

    skills/universal/unslop         every machine, every harness
    skills/claude/foo               Claude Code only
    skills/desktop/foo              only the machine named "desktop"
    skills/work/codex/foo           machines tagged "work", Codex only

A filter is "universal", a harness name, a machine name, a tag, or windows/mac/linux.
instructions/ follows the same rule, with the file name as the last filter.

Standard library only, Python 3.9+, so it runs anywhere git does.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent
OS_TAG = {"win32": "windows", "darwin": "mac"}.get(sys.platform, "linux")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # stops the background task flashing a console on Windows

# harness: (folder that means it's installed, global instructions file, skill folders it reads).
# Paths are relative to ~. We install into the first skill folder; the rest are read too,
# so a skill already placed in one of them is not copied again.
# These are the default paths. Custom config directories are outside this table.
HARNESSES = {
    "claude": (".claude", ".claude/CLAUDE.md", [".claude/skills"]),
    "codex": (".codex", ".codex/AGENTS.md", [".agents/skills", ".codex/skills"]),
    "antigravity": (".gemini/antigravity", ".gemini/GEMINI.md", [".gemini/antigravity/skills"]),
    "antigravity-cli": (".gemini/antigravity-cli", ".gemini/GEMINI.md", [".gemini/antigravity-cli/skills"]),
    "cursor": (".cursor", None, [".cursor/skills"]),
    # After native readers: these harnesses also read shared folders, so they rarely need their own copy.
    "opencode": (".config/opencode", ".config/opencode/AGENTS.md",
                 [".config/opencode/skills", ".claude/skills", ".agents/skills"]),
    "muse": (".config/muse", ".config/muse/AGENTS.md",
             [".config/muse/skills", ".agents/skills", ".claude/skills", ".codex/skills"]),
}


def toolbox_name(repo: Path) -> str:
    name = json.loads((repo / "toolbox.json").read_text(encoding="utf-8")).get("name")
    if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,47}", name):
        sys.exit("toolbox.json name must start with a lowercase letter and use up to 48 lowercase letters, digits, or hyphens")
    if re.fullmatch(r"con|prn|aux|nul|com[0-9]|lpt[0-9]", name):
        sys.exit(f"toolbox.json name '{name}' is reserved on Windows")
    return name


def state_path(home: Path, name: str) -> Path:
    return home / ".agent-toolboxes" / name


def find_skills(repo: Path):
    """Yield (name, folder, filters) for every folder under skills/ that holds a SKILL.md."""
    root = repo / "skills"
    for dirpath, dirs, files in os.walk(root):
        dirs.sort()
        if "SKILL.md" in files:
            folder = Path(dirpath)
            yield folder.name, folder, folder.relative_to(root).parts[:-1]
            dirs.clear()  # a skill's own subfolders are not more skills


def find_instructions(repo: Path):
    """Yield (file, filters) for every instructions/**/*.md, universal.md first."""
    root = repo / "instructions"
    for f in sorted(root.rglob("*.md"), key=lambda p: (p != root / "universal.md", str(p))):
        yield f, f.relative_to(root).parts[:-1] + (f.stem,)


def digest(folder: Path) -> str:
    """Fingerprint of every file and folder in a folder, to tell if a copy changed."""
    h = hashlib.sha256()
    for f in sorted(folder.rglob("*")):
        rel = f.relative_to(folder).as_posix()
        if f.is_dir():
            h.update(hashlib.sha256(rel.encode() + b"/").digest())
        elif f.is_file():
            h.update(hashlib.sha256(rel.encode()).digest())
            h.update(hashlib.sha256(f.read_bytes()).digest())
    return h.hexdigest()


def is_real_dir(p: Path) -> bool:
    """A plain folder: not a symlink and not a Windows junction (the skills CLI makes junctions)."""
    return p.is_dir() and not p.is_symlink() and not getattr(p, "is_junction", lambda: False)()


def make_room(target: Path, expected: str | None, backup_root: Path, home: Path, dry: bool) -> bool:
    """Empty target's spot. Our own untouched copy is deleted; anything else goes to backups. True if backed up."""
    if not os.path.lexists(target):  # lexists also sees dangling links and junctions
        return False
    if expected and is_real_dir(target) and digest(target) == expected:
        if not dry:
            shutil.rmtree(target)
        return False
    if not dry:
        dest = backup_root / target.relative_to(home)
        dest.parent.mkdir(parents=True, exist_ok=True)
        target.rename(dest)  # never fall back to copy-and-delete if Windows has the folder open
    return True


def with_block(old: str, body: str, name: str) -> str:
    """old with our marked block replaced (or appended). Everything outside the markers is untouched."""
    start, end = f"<!-- {name}:start -->", f"<!-- {name}:end -->"
    block = f"{start}\n{body.strip()}\n{end}"
    if start in old and end in old:
        head, rest = old.split(start, 1)
        return head + block + rest.split(end, 1)[1]
    return (old.rstrip() + "\n\n" if old.strip() else "") + block + "\n"


def write_atomic(path: Path, text: str) -> None:
    """Write a temp file, then swap it in, so a crash never leaves half a file.

    resolve() means a symlinked file stays a symlink. Links that point AT this path
    (T3 Code's other Codex homes -> ~/.codex/AGENTS.md) keep working too.
    """
    real = path.resolve()
    real.parent.mkdir(parents=True, exist_ok=True)
    tmp = real.with_name(real.name + ".toolbox-tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, real)


@contextlib.contextmanager
def locked(state: Path):
    """One sync at a time. A lock older than 10 minutes is left over from a crash, so it's taken over."""
    state.mkdir(parents=True, exist_ok=True)
    lock = state / "sync.lock"
    if lock.exists() and time.time() - lock.stat().st_mtime > 600:
        lock.unlink(missing_ok=True)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        sys.exit(f"another sync is running. If it isn't, remove {lock}")
    try:
        yield
    finally:
        os.close(fd)
        lock.unlink(missing_ok=True)


def git_pull(repo: Path, strict: bool = False) -> None:
    """Fast-forward; background runs stop on failure, manual runs can install local work."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}  # don't ask for a login
    try:
        r = subprocess.run(["git", "-C", str(repo), "pull", "--ff-only", "--quiet"], capture_output=True,
                           text=True, errors="replace", env=env, creationflags=NO_WINDOW, timeout=120)
        err = r.stderr.strip() or "unknown error" if r.returncode else ""
    except (OSError, subprocess.SubprocessError) as e:  # includes the timeout, in case a login prompt hangs anyway
        err = str(e)
    if err:
        if strict:
            sys.exit(f"sync blocked: git pull failed: {err.splitlines()[-1]}")
        print(f"! git pull failed, using the files on disk: {err.splitlines()[-1]}")
    if strict:
        r = subprocess.run(["git", "-C", str(repo), "rev-list", "--count", "@{upstream}..HEAD"],
                           capture_output=True, text=True, creationflags=NO_WINDOW, timeout=15)
        if r.returncode or r.stdout.strip() != "0":
            sys.exit("sync blocked: local commits are not on the upstream branch")


def repo_status(repo: Path) -> dict:
    """Identify the source being installed, including unfinished local work."""
    def git(*args, allow_missing=False):
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                                text=True, errors="replace", creationflags=NO_WINDOW, timeout=15)
        if allow_missing and result.returncode == 1:
            return None
        if result.returncode:
            sys.exit(f"sync blocked: {result.stderr.strip() or 'cannot read Git state'}")
        return result.stdout.strip()
    return {
        "dirty": bool(git("status", "--porcelain", "--untracked-files=normal")),
        "revision": git("rev-parse", "--verify", "--quiet", "HEAD", allow_missing=True),
    }


def has_upstream(repo: Path) -> bool:
    result = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "@{upstream}"],
                            capture_output=True, creationflags=NO_WINDOW, timeout=15)
    return result.returncode == 0


def sync(home: Path, repo: Path = REPO, machine: str | None = None, dry: bool = False,
         pull: bool = True, background: bool = False) -> list[str]:
    """Install local files, pulling first when the checkout is clean and tracks a remote."""
    name = toolbox_name(repo)
    state = state_path(home, name)
    if dry:
        return install(home, repo, machine, name, dry=True)
    with locked(state):
        source = repo_status(repo) if pull else None
        if source is not None:
            if background and source["dirty"]:
                sys.exit("sync blocked: uncommitted files in the source repo; local work left untouched")
            tracked = has_upstream(repo)
            if background and not tracked:
                sys.exit("sync blocked: set a Git upstream before running background sync")
            if tracked and not source["dirty"]:
                git_pull(repo, strict=background)
                if toolbox_name(repo) != name:
                    sys.exit("sync blocked: toolbox.json name changed during pull; keep the installed name stable")
                source = repo_status(repo)
            if background and source["dirty"]:
                sys.exit("sync blocked: source repo changed during pull; local work left untouched")
        changes = install(home, repo, machine, name)
        if source is not None:
            if repo_status(repo) != source:
                sys.exit("source changed during installation; installed revision not recorded, rerun sync")
            source["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            write_atomic(state / "sync.json", json.dumps(source, indent=2) + "\n")
            revision = source["revision"] or "(no commits yet)"
            print(f"installed revision: {revision} ({'local edits' if source['dirty'] else 'clean'})")
        return changes


def install(home: Path, repo: Path, machine: str | None, toolbox: str, dry: bool = False) -> list[str]:
    """Install this repo's skills and instructions into every harness found in home. Returns the changes."""
    state = state_path(home, toolbox)
    machines = json.loads((repo / "machines.json").read_text(encoding="utf-8"))
    if machine and machine not in machines:
        sys.exit(f"'{machine}' is not in machines.json. Add it there first. Known: {', '.join(machines)}")
    if machine and not dry:
        state.mkdir(parents=True, exist_ok=True)
        (state / "machine").write_text(machine, encoding="utf-8")
    saved = state / "machine"
    name = machine or (saved.read_text(encoding="utf-8").strip() if saved.exists() else None)
    tags = [*machines.get(name, {}).get("tags", []), OS_TAG]
    me = {"universal", *tags, *([name] if name else [])}
    known = {"universal", "windows", "mac", "linux", *HARNESSES, *machines,
             *(t for m in machines.values() for t in m.get("tags", []))}
    here = [h for h, (marker, _, _) in HARNESSES.items() if (home / marker).is_dir()]

    print(f"{toolbox} | machine: {name or '(unnamed)'} [{', '.join(tags)}] | harnesses: {', '.join(here) or 'none found'}")
    if not here:
        print("! no supported agent folders found. Open your coding agent once, then retry.")
    if name and name not in machines:
        print(f"! saved machine '{name}' is missing from machines.json. Use sync --as to select its replacement.")
    changes: list[str] = []
    report: dict[str, dict[str, list[str]]] = {}  # folder -> what happened -> skill names

    def change(d: str, what: str, skill: str) -> None:
        changes.append(f"{what}: ~/{d}/{skill}")
        report.setdefault(d, {}).setdefault(what, []).append(skill)

    def unknown(where: str, filters) -> bool:
        bad = [f for f in filters if f not in known]
        if bad:
            print(f"! {where}: {', '.join(bad)} is not a harness, machine, or tag, so it's skipped. Typo, or add it to machines.json?")
        return bool(bad)

    # Plan: which skill goes in which folder. Fewest copies that still reach every harness that wants it.
    want: dict[str, dict[str, Path]] = {}
    plan = []
    for skill, folder, filters in find_skills(repo):
        if unknown(f"skills/{'/'.join(filters)}/{skill}", filters):
            continue
        wanting = [h for h in here if all(f in me or f == h for f in filters)]
        placed: list[str] = []
        for h in wanting:
            reads = HARNESSES[h][2]
            if not set(placed) & set(reads):
                placed.append(reads[0])
        for d in placed:
            if skill in want.setdefault(d, {}):
                print(f"! two skills named {skill} want ~/{d}, keeping {want[d][skill].relative_to(repo)}")
            else:
                want[d][skill] = folder
        plan.append((skill, wanting, placed))

    # Apply. installed.json remembers what we put where, so we only ever remove our own things.
    installed_file = state / "installed.json"
    owned: dict[str, dict[str, str]] = json.loads(installed_file.read_text(encoding="utf-8")) if installed_file.exists() else {}
    backup_root = state / "backups" / f"{time.strftime('%Y-%m-%d_%H%M%S')}-{os.getpid()}"
    now: dict[str, dict[str, str]] = {}
    edited: list[str] = []

    for d in sorted(set(owned) | set(want)):
        mine, wanted = owned.get(d, {}), want.get(d, {})
        for skill in sorted(set(mine) - set(wanted)):
            target = home / d / skill
            if os.path.lexists(target):
                change(d, "removed", skill)
                if make_room(target, mine[skill], backup_root, home, dry):
                    change(d, "backed up first", skill)
                    edited.append(f"~/{d}/{skill}")
        for skill, src in sorted(wanted.items()):
            target = home / d / skill
            fresh = digest(src)
            now.setdefault(d, {})[skill] = fresh
            if skill in mine and is_real_dir(target) and digest(target) == fresh:
                continue
            ours = skill in mine and os.path.lexists(target)
            if make_room(target, mine.get(skill), backup_root, home, dry):
                change(d, "backed up first", skill)
                if ours:
                    edited.append(f"~/{d}/{skill}")
            change(d, "updated" if ours else "added", skill)
            if not dry:
                shutil.copytree(src, target)

    for d, happened in report.items():
        print(f"  ~/{d}")
        for what in ("removed", "backed up first", "updated", "added"):
            if what in happened:
                print(f"    {what}: {', '.join(happened[what])}")
    if any("backed up first" in happened for happened in report.values()):
        print(f"  backups {'would go' if dry else 'are'} in {backup_root}")
    for path in edited:
        print(f"! {path} was edited outside this repo. Your version is in the backup; copy it into the repo to keep it.")

    # Same name sitting in another folder a harness reads means that harness sees it twice.
    dupes = {(d, skill) for skill, wanting, placed in plan for h in wanting for d in HARNESSES[h][2]
             if d not in placed and os.path.lexists(home / d / skill) and skill not in now.get(d, {})}
    for d, skill in sorted(dupes):
        print(f"! ~/{d}/{skill} duplicates a skill from {toolbox}. Review both copies before keeping one.")

    # Instructions: one managed block per file. Harnesses that share a file get it once.
    footer = (f"Machine: `{name or 'unnamed'}` ({', '.join(tags)}). Skills, global instructions, "
              f"and templates are managed by `{repo}`. Edit the source there, then run `python squad.py sync`.")
    docs = [(f, filters) for f, filters in find_instructions(repo)
            if not unknown(f"instructions/{f.relative_to(repo / 'instructions').as_posix()}", filters)]
    files: dict[str, list[str]] = {}
    for h in here:
        if HARNESSES[h][1]:
            files.setdefault(HARNESSES[h][1], []).append(h)
    for rel, sharing in files.items():
        parts = [f.read_text(encoding="utf-8").strip() for f, filters in docs
                 if all(x in me or x in sharing for x in filters)]
        path = home / rel
        old = path.read_text(encoding="utf-8") if path.exists() else ""
        new = with_block(old, "\n\n".join(parts + [footer]), toolbox)
        if new == old:
            continue
        changes.append(f"instructions: ~/{rel}")
        print(f"  ~/{rel}: instructions updated")
        if not dry:
            if old.strip():  # keep the previous version, in case someone edited the block by hand
                saved = backup_root / path.relative_to(home)
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, saved)
            write_atomic(path, new)

    if not dry:
        write_atomic(installed_file, json.dumps(now, indent=2, sort_keys=True))
    return changes


def autosync(on: bool, home: Path | None = None, repo: Path = REPO) -> None:
    """Register (or remove) a background job that runs `sync --log` every 2 minutes."""
    home = home or Path.home()
    script = str(repo / "squad.py")
    name = toolbox_name(repo)
    job = f"AgentToolbox-{name}"
    if sys.platform == "win32":
        exe = Path(sys.executable).with_name("pythonw.exe")  # the windowless Python, so nothing pops up
        if not exe.exists():
            print("! no pythonw.exe next to this Python, so the background run may flash a console window")
            exe = Path(sys.executable)
        cmd = (["schtasks", "/Create", "/F", "/SC", "MINUTE", "/MO", "2", "/TN", job,
                "/TR", f'"{exe}" "{script}" sync --log'] if on else ["schtasks", "/Delete", "/F", "/TN", job])
        if subprocess.run(cmd).returncode:
            sys.exit("schtasks failed, see the message above")
        if on:
            settings = (f"Set-ScheduledTask -TaskName {job} -Settings "
                        "(New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries "
                        "-DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew) | Out-Null")
            subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                            "-Command", "$ErrorActionPreference = 'Stop'; " + settings],
                           check=True, creationflags=NO_WINDOW)
    else:
        old = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
        marker = f"# {job}"
        lines = [line for line in old.splitlines() if not line.endswith(marker)]
        if on:
            command = shlex.join([sys.executable, script, "sync", "--log"]).replace("%", r"\%")
            lines.append(f"*/2 * * * * {command} {marker}")
        subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True, check=True)
    log = state_path(home, name) / "sync.log"
    print(f"autosync {'on, every 2 minutes' if on else 'off'}. Last background run: {log}")


def new(template: str | None, dest: str) -> None:
    """Copy templates/<template> into dest. Never overwrites a file that already exists."""
    root = REPO / "templates"
    names = sorted(p.name for p in root.iterdir() if p.is_dir())
    if not template:
        print("templates:", ", ".join(names))
        return
    if template not in names:
        sys.exit(f"no template named '{template}'. Run `python squad.py new` to list them.")
    src = root / template
    for f in sorted(src.rglob("*")):
        if f.is_file():
            out = Path(dest) / f.relative_to(src)
            if out.exists():
                print(f"! {out} already exists, left it alone")
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, out)
            print(f"+ {out}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="squad", description="Sync coding-agent skills and instructions across machines.")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync", help="install skills and instructions on this machine")
    s.add_argument("--as", dest="machine", help="name this machine from machines.json (remembered after the first time)")
    s.add_argument("--dry-run", action="store_true", help="show what would change without pulling or writing")
    s.add_argument("--log", action="store_true", help=argparse.SUPPRESS)  # used by the background job
    a = sub.add_parser("autosync", help="sync every 2 minutes in the background")
    a.add_argument("state", choices=["on", "off"])
    n = sub.add_parser("new", help="copy a template (no name lists them)")
    n.add_argument("template", nargs="?")
    n.add_argument("dest", nargs="?", default=".")
    args = p.parse_args(argv)

    home = Path.home()
    if args.cmd == "sync":
        started = time.monotonic()
        if args.log and not args.dry_run:
            state = state_path(home, toolbox_name(REPO))
            state.mkdir(parents=True, exist_ok=True)
            with (state / "sync.log").open("w", encoding="utf-8") as log:
                with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                    print(time.strftime("%Y-%m-%d %H:%M:%S"))
                    try:
                        changes = sync(home, background=True)
                    except SystemExit as exc:
                        print(exc)
                        raise SystemExit(1) from None
                    print(f"made {len(changes)} change(s) in {time.monotonic() - started:.1f}s")
            return
        changes = sync(home, machine=args.machine, dry=args.dry_run)
        print(f"{'would make' if args.dry_run else 'made'} {len(changes)} change(s)")
        print(f"finished in {time.monotonic() - started:.1f}s")
    elif args.cmd == "autosync":
        autosync(args.state == "on")
    else:
        new(args.template, args.dest)


if __name__ == "__main__":
    main()
