"""Run from the repo root: python -m unittest discover tests"""
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import squad  # noqa: E402


def write(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class SyncTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo, self.home = Path(tmp.name, "repo"), Path(tmp.name, "home")
        write(self.repo / "toolbox.json", '{"name": "test-toolbox"}')
        write(self.repo / "machines.json", json.dumps({"desktop": {"tags": ["home"]}, "work-vm": {"tags": ["work"]}}))
        for path in ["universal/shared", "claude/only-claude", "desktop/only-desktop", "work/codex/work-codex", "destkop/typo"]:
            write(self.repo / "skills" / path / "SKILL.md", path)
        write(self.repo / "skills/universal/shared/references/more.md", "nested file, not a skill")
        write(self.repo / "instructions/universal.md", "be brief")
        write(self.repo / "instructions/codex.md", "codex sandbox note")
        for marker in [".claude", ".codex", ".config/opencode"]:
            (self.home / marker).mkdir(parents=True)

    def sync(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return squad.sync(self.home, self.repo, pull=False, **kw)

    def ls(self, d):
        p = self.home / d
        return sorted(x.name for x in p.iterdir()) if p.exists() else []

    def backups(self):
        return sorted(b.read_text() for b in (self.home / ".agent-toolboxes/test-toolbox/backups").rglob("SKILL.md"))

    def test_routes_by_folder(self):
        self.sync(machine="desktop")
        self.assertEqual(self.ls(".claude/skills"), ["only-claude", "only-desktop", "shared"])
        self.assertEqual(self.ls(".agents/skills"), ["only-desktop", "shared"])
        self.assertEqual(self.ls(".config/opencode/skills"), [])  # OpenCode already reads the two above
        self.assertTrue((self.home / ".claude/skills/shared/references/more.md").exists())

    def test_tag_and_harness_filters_combine(self):
        self.sync(machine="work-vm")
        self.assertEqual(self.ls(".agents/skills"), ["shared", "work-codex"])
        self.assertEqual(self.ls(".claude/skills"), ["only-claude", "shared"])

    def test_muse_reuses_shared_skills_and_routes_its_own(self):
        (self.home / ".config/muse").mkdir(parents=True)
        write(self.repo / "skills/muse/only-muse/SKILL.md", "muse workflow")
        write(self.repo / "instructions/muse.md", "muse note")
        write(self.home / ".config/muse/AGENTS.md", "my muse notes\n")
        self.sync(machine="desktop")
        self.assertEqual(self.ls(".config/muse/skills"), ["only-muse"])
        self.assertEqual(self.ls(".agents/skills"), ["only-desktop", "shared"])
        rules = (self.home / ".config/muse/AGENTS.md").read_text()
        self.assertTrue(rules.startswith("my muse notes\n"))
        self.assertIn("be brief", rules)
        self.assertIn("muse note", rules)
        self.assertNotIn("codex sandbox note", rules)
        self.assertNotIn("muse note", (self.home / ".codex/AGENTS.md").read_text())
        self.assertEqual(self.sync(), [])

    def test_muse_alone_gets_skills_in_its_native_folder(self):
        for marker in (".claude", ".codex", ".config/opencode"):
            shutil.rmtree(self.home / marker)
        (self.home / ".config/muse").mkdir(parents=True)
        self.sync(machine="desktop")
        self.assertEqual(self.ls(".config/muse/skills"), ["only-desktop", "shared"])
        self.assertFalse((self.home / ".agents/skills").exists())
        self.assertIn("be brief", (self.home / ".config/muse/AGENTS.md").read_text())
        self.assertEqual(self.sync(), [])

    def test_unnamed_machine_gets_shared_skills_only(self):
        self.sync()
        self.assertEqual(self.ls(".agents/skills"), ["shared"])

    def test_keeps_unrelated_and_backs_up_same_name(self):
        write(self.home / ".claude/skills/mine/SKILL.md", "not from the repo")
        write(self.home / ".claude/skills/shared/SKILL.md", "old hand copy")
        self.sync(machine="desktop")
        self.assertEqual((self.home / ".claude/skills/mine/SKILL.md").read_text(), "not from the repo")
        self.assertEqual((self.home / ".claude/skills/shared/SKILL.md").read_text(), "universal/shared")
        self.assertEqual(self.backups(), ["old hand copy"])

    def test_prunes_only_what_it_installed(self):
        write(self.home / ".claude/skills/mine/SKILL.md")
        self.sync(machine="desktop")
        shutil.rmtree(self.repo / "skills/universal/shared")
        self.sync()  # the machine name was remembered
        self.assertEqual(self.ls(".claude/skills"), ["mine", "only-claude", "only-desktop"])
        self.assertEqual(self.ls(".agents/skills"), ["only-desktop"])
        self.assertEqual(self.backups(), [])  # untouched copies of ours are just deleted

    def test_local_edits_are_backed_up_not_lost(self):
        self.sync(machine="desktop")
        write(self.home / ".claude/skills/shared/SKILL.md", "edited in place")
        write(self.repo / "skills/universal/shared/SKILL.md", "new version")
        self.sync()
        self.assertEqual((self.home / ".claude/skills/shared/SKILL.md").read_text(), "new version")
        self.assertEqual(self.backups(), ["edited in place"])

    def test_instructions_block_keeps_other_text_and_is_idempotent(self):
        write(self.home / ".codex/AGENTS.md", "my own notes\n")
        self.sync(machine="desktop")
        codex = (self.home / ".codex/AGENTS.md").read_text()
        self.assertTrue(codex.startswith("my own notes"))
        self.assertIn("be brief", codex)
        self.assertIn("codex sandbox note", codex)
        self.assertNotIn("codex sandbox note", (self.home / ".claude/CLAUDE.md").read_text())
        self.assertIn("be brief", (self.home / ".config/opencode/AGENTS.md").read_text())
        self.assertEqual(self.sync(), [])  # second run changes nothing
        self.assertEqual((self.home / ".codex/AGENTS.md").read_text(), codex)

    def test_hand_edit_inside_block_is_backed_up(self):
        self.sync(machine="desktop")
        claude = self.home / ".claude/CLAUDE.md"
        claude.write_text(claude.read_text().replace("be brief", "be brief, hand edit"), encoding="utf-8")
        write(self.repo / "instructions/universal.md", "be very brief")
        self.sync()
        self.assertIn("be very brief", claude.read_text())
        saved = [p.read_text() for p in (self.home / ".agent-toolboxes/test-toolbox/backups").rglob("CLAUDE.md")]
        self.assertTrue(any("hand edit" in s for s in saved))

    def test_one_sync_at_a_time(self):
        write(self.home / ".agent-toolboxes/test-toolbox/sync.lock", "")
        with self.assertRaises(SystemExit):
            self.sync(machine="desktop")
        self.assertFalse((self.home / ".claude/skills").exists())

    def test_keeps_other_toolbox_instructions_and_plugin_files(self):
        rules = self.home / ".codex/AGENTS.md"
        other_block = "<!-- other-toolbox:start -->\nother instructions\n<!-- other-toolbox:end -->\n"
        write(rules, other_block)
        config = self.home / ".claude/settings.json"
        write(config, '{"enabledPlugins": {"caveman@plugins": true}}')
        unrelated = self.home / ".claude/skills/cavecrew/SKILL.md"
        write(unrelated, "some other installer owns this")
        self.sync(machine="desktop")
        self.assertTrue(rules.read_text().startswith(other_block))
        self.assertIn("<!-- test-toolbox:start -->", rules.read_text())
        self.assertIn("caveman@plugins", config.read_text())
        self.assertTrue(unrelated.is_file())

    def test_dry_run_writes_nothing(self):
        self.assertTrue(self.sync(machine="desktop", dry=True))
        self.assertFalse((self.home / ".claude/skills").exists())
        self.assertFalse((self.home / ".claude/CLAUDE.md").exists())
        self.assertFalse((self.home / ".agent-toolboxes").exists())


if __name__ == "__main__":
    unittest.main()
