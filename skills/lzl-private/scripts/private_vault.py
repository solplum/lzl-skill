#!/usr/bin/env python3
"""CLI for personal notes and OS-backed credentials; never prints secret values."""

import argparse
import getpass
import json
import os
import re
import sqlite3
import subprocess
import sys
import warnings
from uuid import uuid4

from private_credentials import CredentialError, CredentialNotFound, SystemCredentials
from private_store import (
    VaultError, absolute_path, config_path, configured_vault, connection, discover,
    entry, initialize, metadata, save_entry, valid_name,
)


def parser():
    root = argparse.ArgumentParser(description="lzl-private：本地个人资料与系统凭据库")
    root.add_argument("--config", metavar="ABS", help="指定本机配置文件的绝对路径")
    commands = root.add_subparsers(dest="action", required=True)
    commands.add_parser("discover", help="只读检测路径和可用的首次配置选项")
    init = commands.add_parser("init", help="选择目录后初始化或复用资料库，并保存配置")
    init.add_argument("--path", metavar="ABS", help="资料目录的完整绝对路径")
    commands.add_parser("status", help="显示当前保存位置与凭据后端状态")
    listing = commands.add_parser("list", help="按名称、项目、说明查找元数据")
    listing.add_argument("--query", default="")
    put = commands.add_parser("put", help="添加或更新普通资料；密钥请用 secret-set")
    put.add_argument("name")
    source = put.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", metavar="ABS")
    source.add_argument("--stdin", action="store_true")
    put.add_argument("--description")
    put.add_argument("--project")
    show = commands.add_parser("show", help="读取普通资料；密钥条目仅返回元数据")
    show.add_argument("name")
    delete = commands.add_parser("delete", help="删除指定条目及其系统凭据（如有）")
    delete.add_argument("name")
    secret = commands.add_parser("secret-set", help="由用户在自己的交互终端隐藏输入密钥")
    secret.add_argument("name")
    secret.add_argument("--description")
    secret.add_argument("--project")
    run = commands.add_parser("run", help="通过环境变量使用密钥：run 名称 --env 变量 -- 程序 参数")
    run.add_argument("name")
    run.add_argument("--env", required=True, metavar="VARIABLE")
    return root


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def secret_input():
    if not sys.stdin.isatty():
        raise VaultError("密钥须由用户在自己的交互终端录入；不能通过聊天、命令参数或管道输入。")
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            value = getpass.getpass("输入密钥（隐藏输入）：")
            repeated = getpass.getpass("再次输入密钥：")
        except (getpass.GetPassWarning, EOFError) as exc:
            raise VaultError("无法安全隐藏输入，请在本机交互终端重试。") from exc
    if not value or value != repeated:
        raise VaultError("密钥为空或两次输入不一致，未保存。")
    return value


def run_with_secret(credentials, service, account, variable, command):
    if not command:
        raise VaultError("请在 -- 后指定要运行的程序及参数。")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", variable):
        raise VaultError("环境变量名称无效。")
    if variable in {"HOME", "home", "CODEX_HOME", "PATH", "PYTHONPATH", "LD_PRELOAD", "DYLD_INSERT_LIBRARIES"}:
        raise VaultError("请使用专门的密钥环境变量，不覆盖系统配置变量。")
    value = credentials.get(service, account)
    env = os.environ.copy()
    env[variable] = value
    try:
        result = subprocess.run(command, env=env, capture_output=True, check=False)
    except OSError as exc:
        raise VaultError("无法启动目标程序，请检查程序路径和执行权限。") from exc
    needle = value.encode("utf-8")
    for output, stream in ((result.stdout, sys.stdout), (result.stderr, sys.stderr)):
        stream.write(output.replace(needle, b"[REDACTED]").decode("utf-8", errors="replace"))
        stream.flush()
    return result.returncode if result.returncode >= 0 else 128 - result.returncode


def previous_secret(credentials, service, account):
    try:
        return credentials.get(service, account)
    except CredentialNotFound:
        return None


def restore_secret(credentials, service, account, previous):
    try:
        if previous is not None:
            credentials.set(service, account, previous)
        elif previous_secret(credentials, service, account) is not None:
            credentials.delete(service, account)
    except CredentialError:
        raise VaultError(
            "操作失败，系统凭据的恢复或清理也未得到确认。"
            f"请检查凭据库中的服务 {service}、账户 {account}，必要时重新录入；没有报告成功。"
        ) from None


def dispatch(args, command):
    config = config_path(args.config)
    if args.action == "discover":
        emit(discover(config))
        return 0
    if args.action == "init":
        emit(initialize(config, args.path))
        return 0
    path, identity = configured_vault(config)
    credentials = SystemCredentials()
    service = "lzl-private:" + identity
    if args.action == "status":
        emit({"data_path": str(path), "config_path": str(config), "credentials": credentials.describe()})
        return 0
    with connection(path, readonly=args.action in {"list", "show", "run"}) as conn:
        if args.action == "list":
            query = args.query.casefold()
            items = conn.execute("SELECT name, kind, credential_id, description, project, updated_at FROM entries ORDER BY name").fetchall()
            emit([metadata(item) for item in items if any(query in item[field].casefold() for field in ("name", "project", "description"))])
        elif args.action == "show":
            item = entry(conn, args.name)
            emit(item if item["kind"] == "note" else metadata(item))
        elif args.action == "put":
            content = absolute_path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
            item = save_entry(conn, args.name, "note", content=content, description=args.description, project=args.project)
            conn.commit()
            emit(item)
        elif args.action == "secret-set":
            valid_name(args.name)
            conn.execute("BEGIN IMMEDIATE")
            old = conn.execute("SELECT * FROM entries WHERE name=?", (args.name,)).fetchone()
            if old and old["kind"] != "secret":
                raise VaultError("同名条目是普通资料，请另取名称或明确删除旧条目。")
            backend = credentials.describe()
            if not backend["available"]:
                raise CredentialError(backend["error"])
            value = secret_input()
            account = old["credential_id"] if old else str(uuid4())
            previous = previous_secret(credentials, service, account) if old else None
            item = save_entry(conn, args.name, "secret", credential_id=account, description=args.description, project=args.project)
            # Stage SQL first; compensate the OS store if its write or SQL commit fails.
            try:
                credentials.set(service, account, value)
                conn.commit()
            except BaseException:
                restore_secret(credentials, service, account, previous)
                raise
            emit(item)
        elif args.action == "delete":
            conn.execute("BEGIN IMMEDIATE")
            item = entry(conn, args.name)
            conn.execute("DELETE FROM entries WHERE name=?", (args.name,))
            if item["kind"] == "secret":
                previous = previous_secret(credentials, service, item["credential_id"])
                try:
                    if previous is not None:
                        credentials.delete(service, item["credential_id"])
                    conn.commit()
                except BaseException:
                    restore_secret(credentials, service, item["credential_id"], previous)
                    raise
            else:
                conn.commit()
            emit({"deleted": args.name})
        elif args.action == "run":
            item = entry(conn, args.name)
            if item["kind"] != "secret":
                raise VaultError("该条目是普通资料，不能作为密钥使用。")
            return run_with_secret(credentials, service, item["credential_id"], args.env, command)
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    command = []
    if "--" in argv:
        separator = argv.index("--")
        command, argv = argv[separator + 1:], argv[:separator]
    cli = parser()
    args = cli.parse_args(argv)
    if command and args.action != "run":
        cli.error("只有 run 命令接受 -- 后的程序参数")
    try:
        return dispatch(args, command)
    except (VaultError, CredentialError) as exc:
        emit({"error": str(exc)})
        return 1
    except (OSError, UnicodeError, sqlite3.Error):
        emit({"error": "文件或数据库操作失败，请检查保存路径、访问权限和可用空间；未报告成功。"})
        return 1
    except KeyboardInterrupt:
        emit({"error": "操作已取消。"})
        return 130


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
