#!/usr/bin/env python3
"""Exercise the pre-push hook with local repositories; no network or installs."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
VALID = 'name: "No Actions expressions inside run: blocks"\non: push\njobs: {}\n'
INVALID = VALID.replace('"No Actions expressions inside run: blocks"', 'No Actions expressions inside run: blocks')


class PushValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.remote = Path(self.tmp.name) / "remote.git"
        self.repo.mkdir()
        self.env = os.environ | {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
        configured = subprocess.run(["git", "config", "--get", "box.yq"], cwd=ROOT, capture_output=True, text=True)
        self.env["YQ"] = os.environ.get("YQ") or configured.stdout.strip() or "yq"
        self.git("init", "-q", "--initial-branch=main")
        self.git("config", "user.name", "test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "core.hooksPath", ".githooks")
        self.git("init", "--bare", "-q", str(self.remote))
        self.git("remote", "add", "origin", str(self.remote))
        for name in (".githooks/pre-push", "scripts/check-workflow-yaml.py"):
            target = self.repo / name
            target.parent.mkdir(exist_ok=True)
            shutil.copy2(ROOT / name, target)
        self.workflow = self.repo / ".github/workflows/build.yml"
        self.workflow.parent.mkdir(parents=True)
        self.workflow.write_text(VALID)
        self.workflow.with_name("other.yaml").write_text(VALID)
        self.commit()

    def git(self, *args, check=True):
        return subprocess.run(["git", *args], cwd=self.repo, env=self.env, capture_output=True, text=True, check=check)

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-qm", "fixture")

    def push(self, *refs):
        return self.git("push", "origin", *(refs or ("main",)), check=False)

    def test_valid_yml_and_yaml_push(self):
        result = self.push()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unquoted_colon_blocks_push_even_with_worktree_fix(self):
        self.workflow.write_text(INVALID)
        self.commit()
        self.workflow.write_text(VALID)
        result = self.push()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(".github/workflows/build.yml", result.stderr)
        self.assertIn("mapping values", result.stderr)
        self.assertEqual(self.git("ls-remote", "origin", "refs/heads/main").stdout, "")

    def test_bad_yaml_extension_on_non_head_branch_blocks_push(self):
        self.git("checkout", "-qb", "bad")
        self.workflow.with_name("other.yaml").write_text(INVALID)
        self.commit()
        self.git("checkout", "main")
        result = self.push("main", "bad")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(".github/workflows/other.yaml", result.stderr)
        self.assertEqual(self.git("ls-remote", "origin").stdout, "")

    def test_worktree_error_does_not_block_valid_commit(self):
        self.workflow.write_text(INVALID)
        result = self.push()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_deleted_ref_needs_no_parser(self):
        self.assertEqual(self.push().returncode, 0)
        self.env["YQ"] = str(self.repo / "missing-yq")
        result = self.push(":main")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_parser_blocks_push(self):
        self.env["YQ"] = str(self.repo / "missing-yq")
        result = self.push()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Cannot validate workflow YAML", result.stderr)


if __name__ == "__main__":
    unittest.main()
