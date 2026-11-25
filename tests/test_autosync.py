"""Exercise background deployment against real local Git repositories."""
import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import squad


class BackgroundSyncTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.repo, self.home = self.root / "repo", self.root / "home"
        self.repo.mkdir()
        (self.home / ".codex").mkdir(parents=True)
        self.git("init", "--initial-branch=main")
        self.git("config", "user.name", "Sync Test")
        self.git("config", "user.email", "sync@example.invalid")
        (self.repo / "toolbox.json").write_text('{"name": "test-toolbox"}', encoding="utf-8")
        (self.repo / "machines.json").write_text("{}", encoding="utf-8")
        skill = self.repo / "skills/universal/shared/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("published", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "initial")
        remote = self.root / "remote.git"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
        self.git("remote", "add", "origin", str(remote))
        self.git("push", "-u", "origin", "main")

    def git(self, *args):
        return subprocess.check_output(
            ["git", "-c", f"core.hooksPath={self.root / 'no-hooks'}", "-C", str(self.repo), *args],
            stderr=subprocess.STDOUT, text=True).strip()

    def sync(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return squad.sync(self.home, self.repo, background=True, **kwargs)

    def test_first_run_in_uncommitted_local_repo(self):
        fresh = self.root / "fresh"
        fresh.mkdir()
        subprocess.run(["git", "init", str(fresh)], check=True, capture_output=True)
        (fresh / "toolbox.json").write_text('{"name": "first-run"}', encoding="utf-8")
        (fresh / "machines.json").write_text("{}", encoding="utf-8")
        skill = fresh / "skills/universal/first/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("first skill", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(squad.sync(self.home, fresh, dry=True))
            self.assertFalse((self.home / ".agent-toolboxes").exists())
            squad.sync(self.home, fresh)
            self.assertEqual(squad.sync(self.home, fresh, dry=True), [])
        state = json.loads((self.home / ".agent-toolboxes/first-run/sync.json").read_text())
        self.assertIsNone(state["revision"])
        self.assertTrue(state["dirty"])
        self.assertTrue((self.home / ".agents/skills/first/SKILL.md").is_file())

    def test_background_sync_needs_an_upstream(self):
        self.git("branch", "--unset-upstream")
        with self.assertRaisesRegex(SystemExit, "set a Git upstream"):
            self.sync()
        self.assertFalse((self.home / ".agents/skills").exists())

    def test_clean_install_records_revision_and_unchanged_files_stay_put(self):
        self.sync()
        state = json.loads((self.home / ".agent-toolboxes/test-toolbox/sync.json").read_text())
        self.assertEqual(state["revision"], self.git("rev-parse", "HEAD"))
        self.assertFalse(state["dirty"])
        target = self.home / ".agents/skills/shared/SKILL.md"
        before = target.stat().st_mtime_ns
        self.assertEqual(self.sync(), [])
        self.assertEqual(target.stat().st_mtime_ns, before)

    def test_dirty_and_untracked_sources_preserve_installed_state(self):
        self.sync()
        state = (self.home / ".agent-toolboxes/test-toolbox/sync.json").read_bytes()
        source = self.repo / "skills/universal/shared/SKILL.md"
        source.write_text("unfinished", encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "uncommitted"):
            self.sync()
        self.assertEqual((self.home / ".agents/skills/shared/SKILL.md").read_text(), "published")
        self.assertEqual((self.home / ".agent-toolboxes/test-toolbox/sync.json").read_bytes(), state)
        source.write_text("published", encoding="utf-8")
        (self.repo / "unfinished.md").write_text("unfinished", encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "uncommitted"):
            self.sync()

    def test_failed_pull_does_not_install_or_claim_success(self):
        self.git("remote", "set-url", "origin", str(self.root / "missing.git"))
        with self.assertRaisesRegex(SystemExit, "pull failed"):
            self.sync()
        self.assertFalse((self.home / ".agents/skills").exists())
        self.assertFalse((self.home / ".agent-toolboxes/test-toolbox/sync.json").exists())
        self.assertFalse((self.home / ".agent-toolboxes/test-toolbox/sync.lock").exists())

    def test_unpushed_commit_is_not_deployed(self):
        source = self.repo / "skills/universal/shared/SKILL.md"
        source.write_text("unpublished", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "not pushed")
        with self.assertRaisesRegex(SystemExit, "not on the upstream"):
            self.sync()
        self.assertFalse((self.home / ".agents/skills").exists())

    def test_manual_sync_can_install_local_edits_and_marks_them(self):
        source = self.repo / "skills/universal/shared/SKILL.md"
        source.write_text("local test", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            squad.sync(self.home, self.repo)
        state = json.loads((self.home / ".agent-toolboxes/test-toolbox/sync.json").read_text())
        self.assertTrue(state["dirty"])
        self.assertEqual((self.home / ".agents/skills/shared/SKILL.md").read_text(), "local test")

    def test_pushed_update_is_pulled_and_installed(self):
        writer = self.root / "writer"
        subprocess.run(["git", "clone", "-b", "main", str(self.root / "remote.git"), str(writer)],
                       check=True, capture_output=True)
        self.sync()
        (writer / "skills/universal/shared/SKILL.md").write_text("update", encoding="utf-8")
        subprocess.run(["git", "-C", str(writer), "add", "."], check=True)
        subprocess.run(["git", "-c", f"core.hooksPath={self.root / 'no-hooks'}", "-C", str(writer),
                        "-c", "user.name=Sync Test", "-c", "user.email=sync@example.invalid",
                        "commit", "-m", "update"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(writer), "push"], check=True, capture_output=True)
        self.sync()
        self.assertEqual((self.home / ".agents/skills/shared/SKILL.md").read_text(), "update")
        state = json.loads((self.home / ".agent-toolboxes/test-toolbox/sync.json").read_text())
        self.assertEqual(state["revision"], self.git("rev-parse", "origin/main"))


class ScheduleTest(unittest.TestCase):
    def test_windows_and_unix_registration_and_removal_use_the_toolbox_name(self):
        for platform in ("win32", "linux", "darwin"):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as tmp:
                home = Path(tmp)
                repo = home / "a folder with spaces"
                repo.mkdir()
                (repo / "toolbox.json").write_text('{"name": "test-toolbox"}', encoding="utf-8")
                with patch.object(squad.sys, "platform", platform), \
                     patch.object(squad.subprocess, "run") as run, \
                     contextlib.redirect_stdout(io.StringIO()):
                    run.return_value.returncode = 0
                    other_job = "*/30 * * * * other # AgentToolbox-other"
                    old_job = "*/30 * * * * old # AgentToolbox-test-toolbox"
                    run.return_value.stdout = f"{other_job}\n{old_job}\n"
                    squad.autosync(True, home, repo)
                    if platform == "win32":
                        cmd = run.call_args_list[0].args[0]
                        self.assertEqual(cmd[cmd.index("/MO") + 1], "2")
                        self.assertEqual(cmd[cmd.index("/TN") + 1], "AgentToolbox-test-toolbox")
                        self.assertIn("sync --log", cmd[-1])
                        settings = run.call_args.args[0][-1]
                        self.assertIn("-AllowStartIfOnBatteries", settings)
                        self.assertIn("-StartWhenAvailable", settings)
                    else:
                        cron = run.call_args.kwargs["input"]
                        self.assertIn(other_job, cron)
                        self.assertIn("*/2 * * * *", cron)
                        self.assertIn("sync --log # AgentToolbox-test-toolbox", cron)
                        self.assertNotIn(old_job, cron)
                    squad.autosync(False, home, repo)
                    if platform == "win32":
                        self.assertEqual(run.call_args.args[0][-1], "AgentToolbox-test-toolbox")
                    else:
                        self.assertEqual(run.call_args.kwargs["input"], other_job + "\n")

    def test_background_sync_reports_failure_in_its_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            with patch.object(squad.Path, "home", return_value=home), \
                 patch.object(squad, "toolbox_name", return_value="test-toolbox"), \
                 patch.object(squad, "sync", side_effect=SystemExit("sync blocked: uncommitted files")) as sync:
                with self.assertRaisesRegex(SystemExit, "1"):
                    squad.main(["sync", "--log"])
                self.assertEqual(sync.call_args.kwargs, {"background": True})
            log = (home / ".agent-toolboxes/test-toolbox/sync.log").read_text(encoding="utf-8")
            self.assertIn("sync blocked: uncommitted files", log)
