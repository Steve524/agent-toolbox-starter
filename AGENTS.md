# AGENTS.md

- First-time setup or a new machine → follow [SETUP-FOR-LLMS.md](SETUP-FOR-LLMS.md).
- Edit this repo to change skills and global instructions. Sync manages the installed copies.
- Keep `squad.py` standard-library Python 3.9+. After edits, run `python squad.py sync --dry-run`. If the script changes, also run `python -m unittest discover tests`.
- When adding or removing a skill, update [skills/README.md](skills/README.md) and keep its folder and frontmatter name aligned.
- Get approval before publishing a Git remote, sharing changes, or enabling autosync.
