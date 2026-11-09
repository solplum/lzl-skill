"""All credential tests use in-memory doubles; no OS credential access."""

import contextlib
import io
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from private_credentials import CredentialError, CredentialNotFound, SystemCredentials


SENTINEL = "test-only-secret-not-a-real-credential"


def backend_class(module_name="keyring.backends.macOS", class_name="Keyring", priority=5):
    class Backend:
        def __init__(self):
            self.values = {}
            self.calls = []

        def set_password(self, service, account, value):
            self.calls.append("set")
            self.values[(service, account)] = value

        def get_password(self, service, account):
            self.calls.append("get")
            return self.values.get((service, account))

        def delete_password(self, service, account):
            self.calls.append("delete")
            del self.values[(service, account)]

    Backend.__module__ = module_name
    Backend.__name__ = class_name
    Backend.priority = priority
    return Backend


class CredentialsTests(unittest.TestCase):
    def load_backend(self, platform="darwin", module="keyring.backends.macOS", name="Keyring", priority=5):
        backend_type = backend_class(module, name, priority)

        def importer(module_name):
            if module_name == "keyring":
                return types.SimpleNamespace()
            if module_name == module:
                return types.SimpleNamespace(**{name: backend_type})
            raise ImportError("not installed")

        patches = [
            patch("private_credentials.sys.platform", platform),
            patch("private_credentials.importlib.import_module", side_effect=importer),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        return SystemCredentials(), backend_type

    def test_constructor_is_lazy(self):
        with patch("private_credentials.importlib.import_module") as importer:
            SystemCredentials()
        importer.assert_not_called()

    def test_describe_never_reads_credentials(self):
        store, _ = self.load_backend()
        self.assertTrue(store.describe()["available"])
        self.assertEqual(store._selected.calls, [])

    def test_write_read_delete_roundtrip(self):
        store, _ = self.load_backend()
        store.set("test-service", "test-account", SENTINEL)
        self.assertEqual(store.get("test-service", "test-account"), SENTINEL)
        store.delete("test-service", "test-account")
        with self.assertRaises(CredentialError):
            store.get("test-service", "test-account")

    def test_missing_dependency_reports_setup(self):
        with patch("private_credentials.sys.platform", "darwin"), patch(
            "private_credentials.importlib.import_module", side_effect=ImportError(SENTINEL)
        ):
            result = SystemCredentials().describe()
        self.assertFalse(result["available"])
        self.assertIn("pip install keyring", result["error"])
        self.assertNotIn(SENTINEL, result["error"])

    def test_no_unsupported_platform_fallback(self):
        with patch("private_credentials.sys.platform", "unknown"), patch(
            "private_credentials.importlib.import_module"
        ) as importer:
            result = SystemCredentials().describe()
        self.assertFalse(result["available"])
        importer.assert_not_called()

    def test_unavailable_backend_does_not_report_success(self):
        store, _ = self.load_backend(priority=0)
        self.assertFalse(store.describe()["available"])
        with self.assertRaises(CredentialError):
            store.set("service", "account", SENTINEL)

    def test_backend_from_untrusted_module_is_rejected(self):
        untrusted = backend_class("keyrings.alt.file", "PlaintextKeyring")
        with patch("private_credentials.sys.platform", "darwin"), patch(
            "private_credentials.importlib.import_module",
            side_effect=lambda name: types.SimpleNamespace(Keyring=untrusted),
        ):
            store = SystemCredentials()
            self.assertFalse(store.describe()["available"])
            with self.assertRaises(CredentialError):
                store.set("service", "account", SENTINEL)

    def test_explicit_windows_backend(self):
        store, _ = self.load_backend("win32", "keyring.backends.Windows", "WinVaultKeyring")
        self.assertEqual(store.describe()["backend"], "keyring.backends.Windows.WinVaultKeyring")

    def test_explicit_linux_secret_service_backend(self):
        store, _ = self.load_backend("linux", "keyring.backends.SecretService", "Keyring")
        self.assertEqual(store.describe()["backend"], "keyring.backends.SecretService.Keyring")

    def test_explicit_linux_kwallet_backend(self):
        store, _ = self.load_backend("linux", "keyring.backends.kwallet", "DBusKeyring")
        self.assertEqual(store.describe()["backend"], "keyring.backends.kwallet.DBusKeyring")

    def test_operation_errors_never_echo_secret(self):
        store, _ = self.load_backend()
        store.describe()
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            for method_name, backend_name, args in [
                ("set", "set_password", ("service", "account", SENTINEL)),
                ("get", "get_password", ("service", "account")),
                ("delete", "delete_password", ("service", "account")),
            ]:
                with self.subTest(method=method_name), patch.object(
                    store._selected, backend_name, side_effect=RuntimeError(SENTINEL)
                ):
                    with self.assertRaises(CredentialError) as caught:
                        getattr(store, method_name)(*args)
                    self.assertNotIn(SENTINEL, str(caught.exception))
                    self.assertTrue(caught.exception.__suppress_context__)
        self.assertNotIn(SENTINEL, captured.getvalue())

    def test_silent_backend_write_failure_is_detected(self):
        store, _ = self.load_backend()
        store.describe()
        with patch.object(store._selected, "set_password"):
            with self.assertRaises(CredentialError):
                store.set("service", "account", SENTINEL)

    def test_silent_backend_delete_failure_is_detected(self):
        store, _ = self.load_backend()
        store.set("service", "account", SENTINEL)
        with patch.object(store._selected, "delete_password"):
            with self.assertRaises(CredentialError):
                store.delete("service", "account")

    def test_missing_delete_is_an_error(self):
        store, _ = self.load_backend()
        with self.assertRaises(CredentialError):
            store.delete("service", "account")

    def test_missing_get_has_specific_type(self):
        store, _ = self.load_backend()
        with self.assertRaises(CredentialNotFound) as caught:
            store.get("service", "account")
        self.assertIsInstance(caught.exception, CredentialError)

    def test_get_access_failure_is_not_missing(self):
        store, _ = self.load_backend()
        store.describe()
        with patch.object(store._selected, "get_password", side_effect=RuntimeError("locked")):
            with self.assertRaises(CredentialError) as caught:
                store.get("service", "account")
        self.assertNotIsInstance(caught.exception, CredentialNotFound)

    def test_empty_secret_is_rejected_before_access(self):
        store = SystemCredentials()
        with patch("private_credentials.importlib.import_module") as importer:
            with self.assertRaises(CredentialError):
                store.set("service", "account", "")
        importer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
