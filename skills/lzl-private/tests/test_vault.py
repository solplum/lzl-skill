"""User-visible initialization, storage and credential-use regression tests."""

from contextlib import contextmanager, redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import private_store as store
import private_vault as cli
from private_credentials import CredentialError, CredentialNotFound


class FakeCredentials:
    def __init__(self):
        self.values = {}

    def describe(self):
        return {"available": True, "backend": "test.fake"}

    def set(self, service, account, value):
        self.values[(service, account)] = value

    def get(self, service, account):
        try:
            return self.values[(service, account)]
        except KeyError:
            raise CredentialNotFound("missing test credential") from None

    def delete(self, service, account):
        if (service, account) not in self.values:
            raise CredentialError("missing test credential")
        del self.values[(service, account)]


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="lzl-private-tests-")
        self.root = Path(self.temporary.name).resolve()
        self.data = self.root / "custom data"
        self.default = self.root / "default data"
        self.config = self.root / "configuration" / "config.json"
        self.fake = FakeCredentials()
        self.paths = patch.object(store, "system_paths", return_value=(self.default, self.config))
        self.backend = patch.object(cli, "SystemCredentials", return_value=self.fake)
        self.paths.start()
        self.backend.start()
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(self.paths.stop)
        self.addCleanup(self.backend.stop)

    def command(self, *args, stdin=""):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), patch.object(sys, "stdin", io.StringIO(stdin)):
            code = cli.main(["--config", str(self.config), *args])
        return code, out.getvalue(), err.getvalue()

    def initialize(self, default=False):
        args = () if default else ("--path", str(self.data))
        code, out, _ = self.command("init", *args)
        self.assertEqual(code, 0, out)
        return json.loads(out)

    def secret(self, name="example-dev", value="only-a-fake-test-secret"):
        with patch.object(cli, "secret_input", return_value=value):
            code, out, _ = self.command("secret-set", name)
        self.assertEqual(code, 0, out)
        self.assertNotIn(value, out)
        return json.loads(out)

    @contextmanager
    def failing_commit(self, path, readonly=False):
        with store.connection(path, readonly=readonly) as conn:
            proxy = Mock(wraps=conn)
            proxy.commit.side_effect = sqlite3.OperationalError("simulated commit failure")
            yield proxy

    def test_fresh_discovery_has_absolute_paths_and_no_reuse_or_writes(self):
        code, out, _ = self.command("discover")
        result = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual([item["id"] for item in result["options"]], ["default", "custom"])
        self.assertTrue(Path(result["default_path"]).is_absolute())
        self.assertTrue(Path(result["config_path"]).is_absolute())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_default_initialization_and_lost_config_discovery(self):
        self.initialize(default=True)
        self.config.unlink()
        result = json.loads(self.command("discover")[1])
        self.assertEqual(result["options"][-1]["id"], "reuse")
        self.assertEqual(result["existing_vaults"][0]["path"], str(self.default))
        reused = self.initialize(default=True)
        self.assertTrue(reused["reused"])

    def test_custom_location_is_persisted_and_reused_with_data(self):
        first = self.initialize()
        self.command("put", "endpoint", "--stdin", stdin="https://example.invalid/api")
        again = self.initialize()
        self.assertTrue(again["reused"])
        self.assertEqual(first["vault_id"], again["vault_id"])
        self.assertEqual(json.loads(self.command("show", "endpoint")[1])["content"], "https://example.invalid/api")
        result = json.loads(self.command("discover")[1])
        self.assertEqual(result["configured_path"], str(self.data))

    def test_invalid_default_database_is_not_offered_for_reuse(self):
        self.default.mkdir()
        (self.default / store.DATABASE).write_text("not a database")
        result = json.loads(self.command("discover")[1])
        self.assertEqual(result["existing_vaults"], [])
        self.assertEqual(self.command("init")[0], 1)
        self.assertEqual((self.default / store.DATABASE).read_text(), "not a database")

    def test_relative_path_and_unrelated_nonempty_directory_are_rejected(self):
        self.assertEqual(self.command("init", "--path", "relative/path")[0], 1)
        self.data.mkdir()
        (self.data / "existing.txt").write_text("keep")
        self.assertEqual(self.command("init", "--path", str(self.data))[0], 1)
        self.assertFalse((self.data / store.DATABASE).exists())

    def test_git_workspace_cannot_hold_private_database_or_config(self):
        (self.root / ".git").mkdir()
        self.assertEqual(self.command("init", "--path", str(self.data))[0], 1)
        self.assertFalse(self.data.exists())

    def test_config_cannot_replace_database_or_journal(self):
        for suffix in ("", "-journal", "-wal", "-shm"):
            with self.subTest(suffix=suffix):
                bad_config = self.data / (store.DATABASE + suffix)
                with self.assertRaises(store.VaultError):
                    store.initialize(bad_config, str(self.data))
                self.assertFalse(self.data.exists())

    def test_broken_config_and_missing_database_never_create_replacement(self):
        self.initialize()
        (self.data / store.DATABASE).unlink()
        self.assertEqual(self.command("list")[0], 1)
        self.assertEqual(self.command("init")[0], 1)
        self.assertFalse(self.default.exists())
        self.config.write_text("broken config")
        result = json.loads(self.command("discover")[1])
        self.assertTrue(result["config_error"])
        self.assertEqual(self.command("init")[0], 1)

    def test_identity_mismatch_is_rejected(self):
        self.initialize()
        content = json.loads(self.config.read_text())
        content["vault_id"] = "00000000-0000-0000-0000-000000000000"
        self.config.write_text(json.dumps(content))
        self.assertEqual(self.command("list")[0], 1)
        self.assertEqual(self.command("init", "--path", str(self.data))[0], 1)

    def test_note_lifecycle_preserves_metadata_on_update_and_limits_search(self):
        self.initialize()
        code, _, _ = self.command("put", "接口地址", "--stdin", "--description", "开发接口", "--project", "Example", stdin="sensitive ordinary note")
        self.assertEqual(code, 0)
        self.assertEqual(self.command("put", "接口地址", "--stdin", stdin="updated note")[0], 0)
        found = json.loads(self.command("list", "--query", "EXAMPLE")[1])
        self.assertEqual(len(found), 1)
        self.assertNotIn("content", found[0])
        self.assertEqual(found[0]["description"], "开发接口")
        self.assertEqual(self.command("delete", "接口地址")[0], 0)
        self.assertEqual(self.command("show", "接口地址")[0], 1)

    def test_secret_values_stay_out_of_database_show_and_status(self):
        self.initialize()
        value = "only-a-fake-test-secret"
        item = self.secret(value=value)
        raw = (self.data / store.DATABASE).read_bytes()
        self.assertNotIn(value.encode(), raw)
        self.assertNotIn(value, self.command("show", "example-dev")[1])
        self.assertNotIn(value, self.command("status")[1])
        self.assertNotIn("content", item)
        self.assertEqual(self.command("put", "example-dev", "--stdin", stdin="replacement")[0], 1)

    def test_piped_secret_input_is_rejected_without_saving(self):
        self.initialize()
        code, out, _ = self.command("secret-set", "example", stdin="pretend-secret\n")
        self.assertEqual(code, 1)
        self.assertNotIn("pretend-secret", out)
        self.assertEqual(self.fake.values, {})
        self.assertEqual(json.loads(self.command("list")[1]), [])

    def test_missing_credential_backend_does_not_block_notes(self):
        self.initialize()
        with patch.object(self.fake, "describe", return_value={"available": False, "error": "no backend"}), patch.object(cli, "secret_input") as input_mock:
            self.assertEqual(self.command("secret-set", "example")[0], 1)
            input_mock.assert_not_called()
            self.assertEqual(self.command("put", "note", "--stdin", stdin="hello")[0], 0)

    def test_run_injects_one_child_env_redacts_both_streams_and_preserves_exit_code(self):
        self.initialize()
        self.secret()
        program = "import os,sys; print(os.environ['EXAMPLE_API_KEY']); print(os.environ['EXAMPLE_API_KEY'], file=sys.stderr); sys.exit(7)"
        code, out, err = self.command("run", "example-dev", "--env", "EXAMPLE_API_KEY", "--", sys.executable, "-c", program)
        self.assertEqual(code, 7)
        self.assertEqual(out.strip(), "[REDACTED]")
        self.assertEqual(err.strip(), "[REDACTED]")
        self.assertNotIn("EXAMPLE_API_KEY", os.environ)

    def test_run_missing_secret_or_command_and_note_type_fail(self):
        self.initialize()
        self.secret()
        self.fake.values.clear()
        self.assertEqual(self.command("run", "example-dev", "--env", "KEY", "--", sys.executable, "-c", "print('unexpected')")[0], 1)
        self.assertEqual(self.command("run", "example-dev", "--env", "KEY")[0], 1)
        self.command("put", "note", "--stdin", stdin="text")
        self.assertEqual(self.command("run", "note", "--env", "KEY", "--", sys.executable)[0], 1)

    def test_failed_secret_delete_keeps_index(self):
        self.initialize()
        self.secret()
        with patch.object(self.fake, "delete", side_effect=CredentialError("locked")):
            self.assertEqual(self.command("delete", "example-dev")[0], 1)
        self.assertEqual(len(json.loads(self.command("list")[1])), 1)
        self.assertEqual(self.command("delete", "example-dev")[0], 0)
        self.assertEqual(self.fake.values, {})

    def test_sql_staging_failure_does_not_change_existing_secret(self):
        self.initialize()
        self.secret(value="old-value")
        old_values = dict(self.fake.values)
        with patch.object(cli, "save_entry", side_effect=sqlite3.OperationalError("disk full")), patch.object(cli, "secret_input", return_value="new-value"):
            code, out, _ = self.command("secret-set", "example-dev")
        self.assertEqual(code, 1)
        self.assertEqual(self.fake.values, old_values)
        self.assertNotIn("old-value", out)
        self.assertNotIn("new-value", out)

    def test_commit_failure_restores_updated_secret_and_index(self):
        self.initialize()
        self.secret(value="old-value")
        old_values = dict(self.fake.values)
        with patch.object(cli, "connection", side_effect=self.failing_commit), patch.object(cli, "secret_input", return_value="new-value"):
            code, out, _ = self.command("secret-set", "example-dev", "--description", "new description")
        self.assertEqual(code, 1)
        self.assertEqual(self.fake.values, old_values)
        self.assertEqual(json.loads(self.command("show", "example-dev")[1])["description"], "")
        self.assertNotIn("old-value", out)
        self.assertNotIn("new-value", out)

    def test_commit_failure_cleans_new_secret(self):
        self.initialize()
        with patch.object(cli, "connection", side_effect=self.failing_commit), patch.object(cli, "secret_input", return_value="new-value"):
            self.assertEqual(self.command("secret-set", "example-dev")[0], 1)
        self.assertEqual(self.fake.values, {})
        self.assertEqual(json.loads(self.command("list")[1]), [])

    def test_commit_failure_restores_deleted_secret(self):
        self.initialize()
        self.secret(value="old-value")
        old_values = dict(self.fake.values)
        with patch.object(cli, "connection", side_effect=self.failing_commit):
            self.assertEqual(self.command("delete", "example-dev")[0], 1)
        self.assertEqual(self.fake.values, old_values)
        self.assertEqual(len(json.loads(self.command("list")[1])), 1)

    def test_backend_write_then_verification_failure_restores_old_secret(self):
        self.initialize()
        self.secret(value="old-value")
        original_set = self.fake.set

        def write_then_fail(service, account, value):
            original_set(service, account, value)
            if value == "new-value":
                raise CredentialError("verification failed")

        with patch.object(self.fake, "set", side_effect=write_then_fail), patch.object(cli, "secret_input", return_value="new-value"):
            self.assertEqual(self.command("secret-set", "example-dev")[0], 1)
        self.assertEqual(list(self.fake.values.values()), ["old-value"])

    def test_failed_compensation_reports_uncertain_credential_state(self):
        self.initialize()
        self.secret(value="old-value")
        original_set = self.fake.set

        def failing_set(service, account, value):
            if value == "old-value":
                raise CredentialError("locked")
            original_set(service, account, value)

        with patch.object(self.fake, "set", side_effect=failing_set), patch.object(cli, "connection", side_effect=self.failing_commit), patch.object(cli, "secret_input", return_value="new-value"):
            code, out, _ = self.command("secret-set", "example-dev")
        self.assertEqual(code, 1)
        self.assertIn("恢复或清理也未得到确认", out)
        self.assertNotIn("old-value", out)
        self.assertNotIn("new-value", out)

    def test_missing_credential_after_migration_can_be_rerecorded_or_removed(self):
        self.initialize()
        self.secret()
        self.fake.values.clear()
        self.secret(value="new-on-this-machine")
        self.assertEqual(list(self.fake.values.values()), ["new-on-this-machine"])
        self.fake.values.clear()
        self.assertEqual(self.command("delete", "example-dev")[0], 0)
        self.assertEqual(json.loads(self.command("list")[1]), [])

    def test_failed_note_commit_does_not_emit_success(self):
        self.initialize()
        with patch.object(cli, "connection", side_effect=self.failing_commit):
            code, out, _ = self.command("put", "note", "--stdin", stdin="text")
        self.assertEqual(code, 1)
        self.assertIn("error", json.loads(out))
        self.assertNotIn('"kind"', out)
        self.assertEqual(json.loads(self.command("list")[1]), [])

    @unittest.skipIf(os.name == "nt", "POSIX file modes")
    def test_new_files_are_owner_only(self):
        self.initialize()
        self.assertEqual((self.data.stat().st_mode & 0o777), 0o700)
        self.assertEqual(((self.data / store.DATABASE).stat().st_mode & 0o777), 0o600)
        self.assertEqual((self.config.stat().st_mode & 0o777), 0o600)

    def test_cli_works_from_other_directory_with_spaces_in_path(self):
        self.initialize()
        result = subprocess.run([sys.executable, str(SCRIPTS / "private_vault.py"), "--config", str(self.config), "list"], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), [])


if __name__ == "__main__":
    unittest.main()
