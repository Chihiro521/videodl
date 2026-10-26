import hashlib
import json
import os
import sys
import tempfile
import unittest
from subprocess import CompletedProcess
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import desktop_automation as automation
import desktop_release as release


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="videodl-automation-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git("init", "-b", "master")
        self.git("config", "user.name", "test")
        self.git("config", "user.email", "test@example.test")
        # Avoid a detached Git maintenance process racing temporary cleanup.
        self.git("config", "gc.auto", "0")
        self.git("config", "maintenance.auto", "false")
        self.write("videodl/__init__.py", "__version__ = '0.9.1'\n")
        self.write("videodl/parser.py", "original = True\n")
        self.git("add", ".")
        self.git("commit", "-m", "upstream baseline")
        self.upstream_base = self.git("rev-parse", "HEAD")
        self.git("switch", "-c", "desktop")
        self.write("desktop/__init__.py", "__version__ = '0.4.0'\n")
        self.write("desktop/upstream.json", json.dumps({"upstream_revision": self.upstream_base}))
        self.write(".github/workflows/desktop-ci.yml", "trusted\n")
        self.write("scripts/desktop_automation.py", "trusted\n")
        self.git("add", ".")
        self.git("commit", "-m", "desktop files")
        self.base = self.git("rev-parse", "HEAD")

    def git(self, *args):
        return automation.git(self.root, *args).stdout.strip()

    def write(self, path, contents):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8")

    def upstream(self, changes):
        self.git("switch", "master")
        for path, text in changes.items():
            self.write(path, text)
        self.git("add", ".")
        self.git("commit", "-m", "upstream update")
        revision = self.git("rev-parse", "HEAD")
        self.git("switch", "desktop")
        return revision

    def test_merges_code_preserves_workflows_and_never_imports_upstream(self):
        revision = self.upstream({"videodl/parser.py": "updated = True\n",
                                  "videodl/__init__.py": "__version__ = '0.9.2'\nraise RuntimeError('must not execute')\n",
                                  ".github/workflows/desktop-ci.yml": "upstream replacement\n",
                                  ".github/workflows/new.yml": "unreviewed\n",
                                  "daily_test_results/new-report.json": "{}\n",
                                  "desktop/__init__.py": "__version__ = '99.0.0'\n"})
        result = automation.merge_upstream(self.root, revision)
        self.assertFalse(result["blocked"])
        self.assertEqual((self.root / ".github/workflows/desktop-ci.yml").read_text(), "trusted\n")
        self.assertFalse((self.root / ".github/workflows/new.yml").exists())
        self.assertFalse((self.root / "daily_test_results/new-report.json").exists())
        self.assertIn("updated", (self.root / "videodl/parser.py").read_text())
        metadata = json.loads((self.root / "desktop/upstream.json").read_text())
        self.assertEqual(metadata["core_version"], "0.9.2")
        self.assertEqual(metadata["upstream_revision"], revision)
        automation.guard(self.root, self.base, "codex/sync-upstream-test")

    def test_conflict_becomes_blocked_draft_without_partial_code(self):
        self.write("videodl/parser.py", "desktop change\n")
        self.git("add", ".")
        self.git("commit", "-m", "local adaptation")
        revision = self.upstream({"videodl/parser.py": "upstream change\n"})
        result = automation.merge_upstream(self.root, revision)
        self.assertTrue(result["blocked"])
        self.assertEqual((self.root / "videodl/parser.py").read_text(), "desktop change\n")
        with self.assertRaisesRegex(ValueError, "待处理"):
            automation.guard(self.root, self.base, "codex/sync-upstream-test")

    def test_executable_version_expression_is_rejected_without_execution(self):
        revision = self.upstream({"videodl/__init__.py": "__version__ = __import__('os').getcwd()\n"})
        self.assertTrue(automation.merge_upstream(self.root, revision)["blocked"])

    def test_sync_branch_cannot_modify_desktop_adapter(self):
        self.write("desktop/app.py", "changed\n")
        self.git("add", ".")
        self.git("commit", "-m", "unexpected adaptation")
        with self.assertRaisesRegex(ValueError, "桌面维护文件"):
            automation.guard(self.root, self.base, "codex/sync-upstream-test")
        automation.guard(self.root, self.base, "codex/normal-adaptation")

    def test_forged_upstream_record_is_rejected(self):
        self.write("desktop/upstream.json", json.dumps({"upstream_revision": "f" * 40}))
        with self.assertRaisesRegex(ValueError, "完整提交"):
            automation.guard(self.root, self.base, "desktop")

    def test_online_sync_pushes_a_draft_and_dispatches_preserved_workflows(self):
        revision = self.upstream({"videodl/parser.py": "new parser\n"})
        remote = self.root / "remote.git"
        automation.run(self.root, "git", "init", "--bare", str(remote))
        self.git("remote", "add", "origin", str(remote))
        self.git("push", "origin", "desktop")
        original_run, calls = automation.run, []
        def commands(root, *args, **kwargs):
            if args[0] != "gh":
                return original_run(root, *args, **kwargs)
            calls.append(args)
            if args[1:3] == ("pr", "list"):
                return CompletedProcess(args, 0, "[]", "")
            if args[1:3] == ("pr", "create"):
                self.assertIn("--draft", args)
                return CompletedProcess(args, 0, "https://github.com/fixture/repo/pull/1\n", "")
            return CompletedProcess(args, 0, "", "")
        with patch.object(automation, "UPSTREAM", str(self.root)), patch.object(automation, "run", commands):
            automation.sync(self.root, publish=True)
        branch = "codex/sync-upstream-" + revision[:12]
        self.assertEqual(self.git("branch", "--show-current"), branch)
        self.assertEqual(self.git("rev-parse", "origin/" + branch), self.git("rev-parse", "HEAD"))
        dispatches = [args for args in calls if args[1:3] == ("workflow", "run")]
        self.assertEqual([args[3] for args in dispatches], ["desktop-analysis.yml", "desktop-ci.yml"])
        self.assertTrue(all(args[-1] == branch for args in dispatches))

    def test_existing_sync_pr_is_left_untouched(self):
        self.upstream({"videodl/parser.py": "new upstream\n"})
        remote = self.root / "remote.git"
        automation.run(self.root, "git", "init", "--bare", str(remote))
        self.git("remote", "add", "origin", str(remote))
        self.git("push", "origin", "desktop")
        original_run = automation.run
        def commands(root, *args, **kwargs):
            if args[0] != "gh":
                return original_run(root, *args, **kwargs)
            self.assertEqual(args[1:3], ("pr", "list"))
            return CompletedProcess(args, 0, json.dumps([{"headRefName": "codex/sync-upstream-existing", "url": "https://github.com/fixture/repo/pull/2"}]), "")
        with patch.object(automation, "UPSTREAM", str(self.root)), patch.object(automation, "run", commands):
            automation.sync(self.root, publish=True)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.base)
        self.assertEqual(self.git("branch", "--show-current"), "desktop")

    def test_generated_reports_do_not_open_sync_prs(self):
        self.upstream({"daily_test_results/videodl_status.json": "{}\n"})
        remote = self.root / "remote.git"
        automation.run(self.root, "git", "init", "--bare", str(remote))
        self.git("remote", "add", "origin", str(remote))
        self.git("push", "origin", "desktop")
        original_run = automation.run
        def commands(root, *args, **kwargs):
            self.assertNotEqual(args[0], "gh", "generated reports must not call the PR API")
            return original_run(root, *args, **kwargs)
        with patch.object(automation, "UPSTREAM", str(self.root)), patch.object(automation, "run", commands):
            automation.sync(self.root, publish=True)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.base)

    def test_release_requires_reviewed_branch_and_matching_version(self):
        self.git("update-ref", "refs/remotes/origin/desktop", self.base)
        original_git = automation.git
        def local_git(root, *args, **kwargs):
            if args[:2] == ("fetch", "origin"):
                return None
            return original_git(root, *args, **kwargs)
        with patch.object(automation, "git", local_git):
            self.assertEqual(automation.release_target(self.root, "0.4.0", "refs/heads/desktop"), ("desktop-v0.4.0", self.base))
            with self.assertRaises(ValueError):
                automation.release_target(self.root, "0.5.0", "refs/heads/desktop")
            with self.assertRaises(ValueError):
                automation.release_target(self.root, "", "refs/heads/codex/unreviewed")
            with self.assertRaises(ValueError):
                automation.release_target(self.root, "", "refs/tags/desktop-v0.5.0")
            self.write("desktop/change.txt", "unmerged\n")
            self.git("add", ".")
            self.git("commit", "-m", "not yet reviewed")
            with self.assertRaisesRegex(ValueError, "尚未合入"):
                automation.release_target(self.root, "", "refs/heads/desktop")

    def test_publisher_rejects_tampered_artifact_and_wrong_revision(self):
        self.git("update-ref", "refs/remotes/origin/desktop", self.base)
        artifact = self.root / "artifact"
        artifact.mkdir()
        package = artifact / "VideoDL-Desktop-0.4.0-windows-x64.zip"
        package.write_bytes(b"fixture archive")
        digest = hashlib.sha256(package.read_bytes()).hexdigest()
        (artifact / "SHA256SUMS.txt").write_text(digest + "  " + package.name + "\n")
        (artifact / "build-info.json").write_text(json.dumps({"desktop_version": "0.4.0", "desktop_revision": self.base}))
        self.assertEqual(release.verify(self.root, artifact, "desktop-v0.4.0", self.base), package)
        package.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "校验值"):
            release.verify(self.root, artifact, "desktop-v0.4.0", self.base)
        with self.assertRaisesRegex(ValueError, "预期提交"):
            release.verify(self.root, artifact, "desktop-v0.4.0", "a" * 40)


if __name__ == "__main__":
    unittest.main()
