# Starter skills

Each of these lives in `universal/` and can be moved to another filter. Keep its supporting files with it.

| Skill | Use it for |
|---|---|
| [babysit-pr](universal/babysit-pr/SKILL.md) | Monitor a pull request |
| [codebase-design](universal/codebase-design/SKILL.md) | Work through module design |
| [diagnosing-bugs](universal/diagnosing-bugs/SKILL.md) | Diagnose a bug or slowdown |
| [file-pr](universal/file-pr/SKILL.md) | File a pull request |
| [find-docs](universal/find-docs/SKILL.md) | Look up current developer documentation |
| [grill-with-docs](universal/grill-with-docs/SKILL.md) | Stress-test a design and record decisions |
| [grilling](universal/grilling/SKILL.md) | Stress-test a plan through questions |
| [how](universal/how/SKILL.md) | Explain how code works |
| [html-communication](universal/html-communication/SKILL.md) | Write a self-contained HTML explanation |
| [improve-codebase-architecture](universal/improve-codebase-architecture/SKILL.md) | Find refactors that improve module design |
| [leaving-pr-comments](universal/leaving-pr-comments/SKILL.md) | Leave GitHub pull request comments |
| [unslop](universal/unslop/SKILL.md) | Edit writing for clarity and natural phrasing |
| [why](universal/why/SKILL.md) | Research the reasons behind a decision |
| [wizard](universal/wizard/SKILL.md) | Guide a person through hands-on setup |
| [writing-for-agents](universal/writing-for-agents/SKILL.md) | Write instructions that agents can follow |

Skill discovery and commands depend on the coding agent. If a skill lacks a slash command, ask your agent to read its `SKILL.md` and follow it. GitHub workflows need access to the repo and use T3 pull request tools when available or an authenticated GitHub CLI. The fallback `babysit-pr` watcher needs Python 3.10+ on a Unix environment, such as WSL. `find-docs` uses Context7. Source and license notices travel with the folders where supplied.

Source families include [Matt Pocock's skills](https://github.com/mattpocock/skills), [pstack](https://github.com/cursor/plugins/tree/main/pstack/skills), [tstack](https://github.com/t3dotgg/tstack), and [Postplan](https://postplan.dev/). The architecture and grilling workflows have inline glossary and decision guidance so their starter versions work without a separate domain-modeling skill.
