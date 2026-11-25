# Your agent toolbox

Keep your coding agents' skills, global instructions, and templates in one Git repo. Sync copies them into the agents you use on each machine.

## Start with one machine

1. Choose your repo name. Rename the starter folder if you want, change this README heading, and set the name in [toolbox.json](toolbox.json). Use a short lowercase Git-style name such as `my-agent-kit`. Choose it before the first install and keep it the same across clones. It identifies the local state, instruction blocks, and scheduled job.
2. Check `git --version` and `python --version`. You need Python 3.9 or newer. Use `python3` below if that's how your machine runs Python. Install, open, and sign in to one supported coding agent so its config directory exists.
3. Review [the 15 starter skills](skills/README.md) and personalize [instructions/universal.md](instructions/universal.md). Keep private notes and login details out of the repo.
4. Preview, install, and preview again from this folder.

```sh
python squad.py sync --dry-run
python squad.py sync
python squad.py sync --dry-run
```

Run the install once the first preview lists the agent and changes you expect. If it reports a same-name backup or duplicate, review both copies before proceeding. The last preview should show `0 change(s)`. Open a fresh session in the agent and confirm it sees one starter skill, such as `writing-for-agents`.

The starter is already a local Git repo. Local sync works before the first commit and without a remote. The record at `~/.agent-toolboxes/<name>/sync.json` shows `"revision": null` before the first commit. After committing your setup and syncing again, compare the recorded revision to `git rev-parse HEAD` and check `"dirty": false`.

## Have your coding agent set it up

Open your coding agent in this folder and paste this prompt.

> Follow [SETUP-FOR-LLMS.md](SETUP-FOR-LLMS.md). Help me name and personalize this repo, then set it up on this machine. Show me the sync preview and verify the setup in a fresh session.

## Choose what goes where

Each folder between `skills/` and a skill name is a filter. Every filter must match. Instruction files use the same filters, with the filename as the last filter.

| Path | Who receives it |
|---|---|
| `skills/universal/my-skill/` | Every detected agent |
| `skills/claude/my-skill/` | Claude Code |
| `skills/laptop/my-skill/` | The machine labeled `laptop` |
| `skills/work/codex/my-skill/` | Codex on machines tagged `work` |
| `instructions/windows.md` | Detected agents on Windows that accept global instructions |

`windows`, `mac`, and `linux` are automatic tags. When you want machine-specific rules, add entries like `{"laptop": {"tags": ["work"]}}` to [machines.json](machines.json). Use a distinct label, with no spaces, different from built-in filters and tags. Preview with `python squad.py sync --as laptop --dry-run`, then run `python squad.py sync --as laptop` to save it on that machine.

| Agent | Default skill folder | Global instructions |
|---|---|---|
| Claude Code (`claude`) | `~/.claude/skills` | `~/.claude/CLAUDE.md` |
| Codex (`codex`) | `~/.agents/skills` | `~/.codex/AGENTS.md` |
| Antigravity (`antigravity` or `antigravity-cli`) | `~/.gemini/<filter>/skills` | `~/.gemini/GEMINI.md` |
| OpenCode (`opencode`) | `~/.config/opencode/skills` or shared folders | `~/.config/opencode/AGENTS.md` |
| Cursor (`cursor`) | `~/.cursor/skills` | |
| Muse Code (`muse`) | `~/.config/muse/skills` or shared folders | `~/.config/muse/AGENTS.md` |

Sync detects agents using their default config directories. See `HARNESSES` in [squad.py](squad.py) for exact paths and shared folder rules. Sign-in, model settings, permissions, MCP servers, and custom config locations need separate setup.

Sync replaces its marked instruction block and preserves text around it. It backs up same-name skill folders and edited installed copies before replacing them. Backups are under `~/.agent-toolboxes/<name>/backups/`. Edit the source in this repo and sync again. Use one toolbox to manage a given installed skill.

## Add a second machine or turn on autosync

1. Make your first commit and push it to a remote you choose. A private remote is handy for personal instructions. On the second machine, clone that remote and repeat the agent setup and sync checks. On macOS, put the checkout in your home folder outside Desktop or Documents so the scheduler can read it.
2. Once the checkout is clean and tracks the remote branch, run `python squad.py autosync on` on each machine where you want it. This creates `AgentToolbox-<name>` in Windows Task Scheduler or a matching entry in `crontab -l` on macOS or Linux. It runs every two minutes while the machine can run it.
3. After a scheduled run, check that `completed_at` in `sync.json` advanced and its revision matches `git rev-parse "@{upstream}"`. Read `~/.agent-toolboxes/<name>/sync.log` for the latest background run. Background sync stops on local edits, unpublished commits, or a failed pull. Run `python squad.py autosync off` to remove the job.

## Reuse the templates

- `python squad.py new` lists templates.
- `python squad.py new skill skills/universal/my-skill` creates a skill scaffold. Set the frontmatter name to match the folder.
- `python squad.py new project-agents path/to/project` adds project instructions to a separate project. Existing files are kept.
- `python -m unittest discover tests` checks routing, backups, and sync against temporary setups.
