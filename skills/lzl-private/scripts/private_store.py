"""Local paths, discovery and transactional storage for lzl-private."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from uuid import UUID, uuid4

APP = "lzl-private"
DATABASE = "vault.sqlite3"
APPLICATION_ID = 0x4C5A4C50
VERSION = 1


class VaultError(Exception):
    pass


def absolute_path(value):
    path = Path(value)
    if not path.is_absolute():
        raise VaultError("请提供完整绝对路径。")
    return path.resolve()


def system_paths():
    home = Path.home()
    if sys.platform == "darwin":
        data = home / "Library" / "Application Support" / APP
        config = data / "config.json"
    elif sys.platform == "win32":
        data = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local")) / APP
        config = data / "config.json"
    else:
        data = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share")) / APP
        config = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / APP / "config.json"
    return absolute_path(data), absolute_path(config)


def config_path(override=None):
    return absolute_path(override) if override else system_paths()[1]


def read_config(path):
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["version"] != VERSION:
            raise ValueError()
        data["data_path"] = str(absolute_path(data["data_path"]))
        UUID(data["vault_id"])
        return data
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise VaultError(f"配置无法读取，请检查 {path}；没有创建替代资料库。") from exc


def vault_id(path):
    db = path / DATABASE
    if not db.is_file():
        raise VaultError(f"此目录没有有效资料库：{path}")
    try:
        with connection(path, readonly=True) as conn:
            if conn.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID:
                raise ValueError()
            if conn.execute("PRAGMA user_version").fetchone()[0] != VERSION:
                raise ValueError()
            identity = conn.execute("SELECT value FROM meta WHERE key='vault_id'").fetchone()[0]
            UUID(identity)
            conn.execute("SELECT name, kind, content, credential_id, description, project, updated_at FROM entries LIMIT 0")
            return identity
    except (sqlite3.Error, ValueError, TypeError, IndexError) as exc:
        raise VaultError(f"资料库格式无效或版本不支持：{path}") from exc


@contextmanager
def connection(path, readonly=False):
    mode = "ro" if readonly else "rw"
    conn = sqlite3.connect((path / DATABASE).as_uri() + f"?mode={mode}", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA trusted_schema=OFF")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def discover(config):
    default = system_paths()[0]
    candidates = [default]
    configured = None
    config_error = None
    try:
        saved = read_config(config)
        if saved:
            configured = saved["data_path"]
            candidates.insert(0, Path(configured))
            if vault_id(Path(configured)) != saved["vault_id"]:
                raise VaultError("已配置路径的资料库身份不匹配；请检查目录或备份。")
    except VaultError as exc:
        config_error = str(exc)
    existing = []
    seen = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            identity = vault_id(candidate)
        except (VaultError, OSError):
            continue
        existing.append({"path": str(candidate), "vault_id": identity})
    options = [
        {"id": "default", "label": "系统默认目录（推荐）", "path": str(default)},
        {"id": "custom", "label": "自己指定目录", "requires_absolute_path": True},
    ]
    if existing:
        options.append({"id": "reuse", "label": "使用已检测到的资料库", "vaults": existing})
    return {
        "default_path": str(default), "config_path": str(config),
        "configured_path": configured, "config_error": config_error,
        "existing_vaults": existing, "options": options,
    }


def check_private_destination(path):
    skill_dir = Path(__file__).resolve().parents[1]
    if path == skill_dir or skill_dir in path.parents:
        raise VaultError("资料目录必须与技能安装目录分开。")
    if any((parent / ".git").exists() for parent in (path, *path.parents)):
        raise VaultError("资料目录不能位于 Git 工作区内，请选择个人数据目录。")


def write_config(path, data):
    check_private_destination(path.parent)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".config-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def initialize(config, requested=None):
    target = absolute_path(requested) if requested else system_paths()[0]
    reserved = {target} | {target / (DATABASE + suffix) for suffix in ("", "-journal", "-wal", "-shm")}
    if config in reserved:
        raise VaultError("配置文件路径不能与资料目录、数据库或其日志文件重合。")
    check_private_destination(target)
    check_private_destination(config.parent)
    # A broken configuration requires repair rather than an accidental fresh start.
    saved = read_config(config)
    if saved:
        current_id = vault_id(Path(saved["data_path"]))
        if current_id != saved["vault_id"]:
            raise VaultError("已配置的资料库身份不匹配，请先修复配置。")
    reused = (target / DATABASE).exists()
    if reused:
        identity = vault_id(target)
    else:
        if target.exists() and not target.is_dir():
            raise VaultError("资料路径必须是目录。")
        if target.exists() and any(item.resolve() != config for item in target.iterdir()):
            raise VaultError("所选目录非空且不是有效资料库，请选择空目录或已有资料库。")
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
        db = target / DATABASE
        identity = str(uuid4())
        descriptor = os.open(db, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        try:
            with connection(target) as conn:
                conn.executescript(f"""
                    PRAGMA application_id={APPLICATION_ID};
                    PRAGMA user_version={VERSION};
                    CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                    CREATE TABLE entries (
                        name TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('note','secret')),
                        content TEXT, credential_id TEXT UNIQUE,
                        description TEXT NOT NULL, project TEXT NOT NULL, updated_at TEXT NOT NULL,
                        CHECK ((kind='note' AND content IS NOT NULL AND credential_id IS NULL)
                            OR (kind='secret' AND content IS NULL AND credential_id IS NOT NULL))
                    );
                """)
                conn.execute("INSERT INTO meta VALUES ('vault_id', ?)", (identity,))
        except Exception:
            db.unlink(missing_ok=True)
            raise
    write_config(config, {"version": VERSION, "data_path": str(target), "vault_id": identity})
    return {"data_path": str(target), "config_path": str(config), "vault_id": identity, "reused": reused}


def configured_vault(config):
    saved = read_config(config)
    if not saved:
        raise VaultError("尚未配置。请先运行 discover，选择保存位置后再运行 init。")
    path = Path(saved["data_path"])
    if vault_id(path) != saved["vault_id"]:
        raise VaultError("资料库身份与本机配置不符，请检查保存位置。")
    return path, saved["vault_id"]


def entry(conn, name):
    result = conn.execute("SELECT * FROM entries WHERE name=?", (name,)).fetchone()
    if result is None:
        raise VaultError(f"找不到条目：{name}")
    return dict(result)


def metadata(item):
    return {key: value for key, value in dict(item).items() if key != "content"}


def valid_name(name):
    if not name.strip() or len(name) > 256 or any(ord(char) < 32 for char in name):
        raise VaultError("名称应为 1–256 个字符，且不包含控制字符。")


def save_entry(conn, name, kind, content=None, credential_id=None, description=None, project=None):
    valid_name(name)
    old = conn.execute("SELECT * FROM entries WHERE name=?", (name,)).fetchone()
    if old and old["kind"] != kind:
        raise VaultError("同名条目属于另一种类型，请另取名称或明确删除旧条目。")
    description = description if description is not None else (old["description"] if old else "")
    project = project if project is not None else (old["project"] if old else "")
    conn.execute(
        "INSERT INTO entries VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(name) DO UPDATE SET content=excluded.content, "
        "credential_id=excluded.credential_id, description=excluded.description, "
        "project=excluded.project, updated_at=excluded.updated_at",
        (name, kind, content, credential_id, description, project, datetime.now(timezone.utc).isoformat()),
    )
    return metadata(entry(conn, name))
