"""Lazy access to explicitly selected operating-system credential stores."""

from __future__ import annotations

import importlib
import os
import sys


class CredentialError(Exception):
    """A credential operation failed; the message never includes secret values."""


class CredentialNotFound(CredentialError):
    """The credential store is available but this account has no stored value."""


_INSTALL_HINT = "请在运行此脚本的 Python 环境安装 keyring：python -m pip install keyring。"
_STORE_HINT = "请检查系统凭据库是否可用、已解锁并允许此 Python 访问。"


class SystemCredentials:
    """Use only the platform's built-in keyring backends, never plugin fallback."""

    def __init__(self):
        self._selected = None

    def _backend(self):
        if self._selected is not None:
            return self._selected

        if sys.platform == "darwin":
            candidates = [("keyring.backends.macOS", "Keyring")]
            hint = "请确认 macOS 钥匙串可用。"
        elif sys.platform == "win32":
            candidates = [("keyring.backends.Windows", "WinVaultKeyring")]
            hint = "请确认 Windows 凭据管理器和 keyring 的 Windows 依赖可用。"
        elif sys.platform.startswith("linux"):
            candidates = [
                ("keyring.backends.SecretService", "Keyring"),
                ("keyring.backends.kwallet", "DBusKeyring"),
            ]
            if "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "").split(":"):
                candidates.reverse()
            hint = "请启动当前桌面的 Secret Service 或 KWallet，并确认 D-Bus 会话可用。"
        else:
            raise CredentialError("此系统暂不支持密钥存储；支持 macOS、Windows 和 Linux 桌面凭据库。")

        try:
            importlib.import_module("keyring")
        except ImportError:
            raise CredentialError("缺少 keyring 或其依赖。" + _INSTALL_HINT) from None
        except Exception:
            raise CredentialError("keyring 无法加载。" + _INSTALL_HINT) from None

        for module_name, class_name in candidates:
            try:
                backend_type = getattr(importlib.import_module(module_name), class_name)
                if (backend_type.__module__, backend_type.__name__) != (module_name, class_name):
                    continue
                if backend_type.priority <= 0:
                    continue
                self._selected = backend_type()
                return self._selected
            except Exception:
                # Backend discovery errors may contain sensitive third-party details.
                continue
        raise CredentialError("没有可用的系统凭据库。" + hint + _INSTALL_HINT)

    def describe(self) -> dict:
        """Check dependencies and service availability without reading credentials."""
        try:
            backend = self._backend()
        except CredentialError as exc:
            return {"available": False, "backend": None, "error": str(exc)}
        backend_type = type(backend)
        return {
            "available": True,
            "backend": backend_type.__module__ + "." + backend_type.__name__,
        }

    @staticmethod
    def _identity(service: str, account: str) -> None:
        if not isinstance(service, str) or not service.strip():
            raise CredentialError("凭据服务名不能为空。")
        if not isinstance(account, str) or not account.strip():
            raise CredentialError("凭据账户名不能为空。")

    def set(self, service: str, account: str, value: str) -> None:
        self._identity(service, account)
        if not isinstance(value, str) or not value:
            raise CredentialError("密钥不能为空。")
        backend = self._backend()
        try:
            backend.set_password(service, account, value)
            stored = backend.get_password(service, account)
        except Exception:
            raise CredentialError("密钥写入或确认失败。" + _STORE_HINT) from None
        if stored != value:
            raise CredentialError("系统凭据库未确认密钥写入，操作未完成。" + _STORE_HINT)

    def get(self, service: str, account: str) -> str:
        self._identity(service, account)
        backend = self._backend()
        try:
            value = backend.get_password(service, account)
        except Exception:
            raise CredentialError("密钥读取失败。" + _STORE_HINT) from None
        if value is None:
            raise CredentialNotFound("系统凭据库中没有这条密钥，请重新录入。")
        if not isinstance(value, str) or not value:
            raise CredentialError("系统凭据库中的密钥为空或格式无效，请重新录入。")
        return value

    def delete(self, service: str, account: str) -> None:
        self._identity(service, account)
        backend = self._backend()
        try:
            backend.delete_password(service, account)
            remaining = backend.get_password(service, account)
        except Exception:
            raise CredentialError("密钥删除失败，凭据可能不存在或凭据库不可访问。" + _STORE_HINT) from None
        if remaining is not None:
            raise CredentialError("系统凭据库未确认密钥删除，操作未完成。" + _STORE_HINT)
