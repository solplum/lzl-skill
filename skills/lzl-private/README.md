# lzl-private

按需保存、查找和更新个人重要资料，并通过系统凭据库使用 API Key、Token 等密钥。日常使用只需说明任务，无须重复提供信息或交代存储位置。

## 安装

需要 Python 3.10+ 和具备本机文件、命令执行能力的 Agent。普通资料功能只使用 Python 标准库。

从本仓库取得完整的 `skills/lzl-private/` 文件夹，放入所用 Agent 支持的用户技能目录。Codex 的一个用户级安装位置是 `$HOME/.agents/skills/lzl-private/`；安装时展开成自己的绝对路径。应保留 `scripts/`、`agents/` 和本说明，不能只复制 `SKILL.md`。

在 Agent 中使用 `$lzl-private`，或直接说：

> 用 lzl-private 保存我的项目配置，以后需要时再查。先检查是否已有资料库，首次使用让我选择保存位置。

安装目录只放公开代码和说明。用户资料保存在初始化时选择的独立目录，真实密钥保存在系统凭据库，不放进这个 GitHub 仓库。

## 首次使用

Agent 先运行只读的 `discover`。已配置有效资料库时直接沿用；尚未配置时提供：

1. **系统默认目录（推荐）**：展示当前机器上的完整绝对路径。
2. **自己指定目录**：输入绝对路径。
3. **使用已有资料库**：仅检测到有效资料库时展示，并列出它的完整绝对路径。

用户选择后才初始化。自定义目录必须为空或已含有效资料库，后者自动复用。资料和配置均不能放在 Git 工作区或技能安装目录，脚本会拒绝这些位置，避免随代码误上传。没有找到已有资料库时，第三项不会出现；其他位置的旧资料库可通过“自己指定目录”提供。检测范围是已保存配置和默认位置。

默认资料目录按系统生成：

| 系统 | 默认位置的生成规则 | 展示给用户的例子 |
| --- | --- | --- |
| macOS | 用户目录下 `Library/Application Support/lzl-private/` | `/Users/alex/Library/Application Support/lzl-private/` |
| Windows | `LOCALAPPDATA` 下 `lzl-private/` | `C:\Users\alex\AppData\Local\lzl-private\` |
| Linux | `XDG_DATA_HOME`，未设置时为用户目录下 `.local/share/lzl-private/` | `/home/alex/.local/share/lzl-private/` |

表中用户名仅作示例，实际选项由脚本计算。macOS 和 Windows 的默认配置文件是默认资料目录下的 `config.json`；Linux 使用 `XDG_CONFIG_HOME/lzl-private/config.json`，未设置时为用户目录下 `.config/lzl-private/config.json`。自定义资料目录只改变资料位置，配置文件仍保存在本机配置位置。

选择完成后显示最终资料目录与配置文件的绝对路径，以后自动沿用。原配置损坏、资料库丢失或没有访问权限时会明确报错，需要先修复配置或还原资料；`init` 不会绕过错误另建空库。

## 普通资料

可以说：

- “登记项目 A 的本地启动说明。”
- “查一下之前保存的项目 A 配置。”
- “更新这条资料的地址。”
- “删除这条过期信息。”

资料有名称、用途、所属项目和更新时间。检索先返回元数据，再按任务读取所需的普通正文。普通资料保存在未加密的本地 SQLite 资料库中，API Key、密码、Token、私钥应使用密钥功能。

本技能默认不写入 AI 长期记忆；需要参与任务的普通正文在读取后仍会进入当前模型上下文。

## 密钥功能

密钥功能额外需要 `requirements-keyring.txt` 中的 `keyring`。建议安装到已有的受控 Python 环境或独立虚拟环境，再用同一个解释器运行脚本：

```bash
python3 -m venv /absolute/path/to/lzl-private-runtime
/absolute/path/to/lzl-private-runtime/bin/python -m pip install -r /absolute/path/to/lzl-private/requirements-keyring.txt
```

以上 `/absolute/path/to/` 是需要替换的路径占位符。Windows 虚拟环境的解释器位于 `Scripts\python.exe`。后续命令使用所选解释器的实际绝对路径；不要修改全局 Python 环境来绕过系统的包管理限制。

使用系统支持的 macOS Keychain、Windows 凭据库、Linux Secret Service / KWallet。依赖缺失、后端不可用或锁定时会报错并提供指引；普通资料不受影响，不自动改存明文文件。Linux 无桌面或无 D-Bus 会话时可能需要先配置系统凭据服务。支持后端的安装要求见 [keyring 官方说明](https://keyring.readthedocs.io/en/stable/)。

录入时，Agent 给出包含实际脚本绝对路径的命令，用户在自己的本机交互终端执行，通过隐藏输入填写：

```bash
python3 /absolute/path/to/lzl-private/scripts/private_vault.py secret-set example-dev --description "某服务开发环境" --project "项目 A"
```

无需把密钥原文贴到聊天中。名称和用途存在索引里，原文只交给系统凭据库。录入完成后，可以说：

> 用我保存的 example-dev 凭据测试项目 A 的接口。

Agent 通过 `run` 临时向指定本地子进程注入环境变量。下面的人工检查只输出是否拿到凭据：

```bash
python3 /absolute/path/to/lzl-private/scripts/private_vault.py run example-dev --env EXAMPLE_API_KEY -- python3 -c 'import os; print("credential available:", bool(os.environ.get("EXAMPLE_API_KEY")))'
```

`show` 对密钥只返回元数据。`run` 会对标准输出、错误输出中的精确密钥字符串打码。它不是沙箱：子进程能读取注入的密钥，编码输出、拆分输出或主动外发不能靠字符串打码阻止；应只运行任务需要且可信的程序。拥有任意本机命令权限的 AI 也不因本技能获得隔离限制。

## 命令与维护

入口：`scripts/private_vault.py`。具体参数使用 `--help` 查看。需要隔离环境或独立配置时，使用全局参数 `--config ABS`，放在子命令前，例如 `python3 /absolute/path/to/lzl-private/scripts/private_vault.py --config /absolute/path/to/private-config.json discover`。该配置路径也必须位于 Git 工作区和技能安装目录之外。

| 命令 | 用途 |
| --- | --- |
| `discover` | 只读检测配置、默认位置和已有资料库，输出首次引导选项 |
| `init [--path ABS]` | 初始化或复用有效资料库；已有有效配置时可显式切换绑定 |
| `status` | 查看当前路径与凭据后端状态 |
| `list [--query TEXT]` | 检索条目元数据 |
| `put NAME --file ABS` / `put NAME --stdin` | 新增或更新普通资料 |
| `show NAME` | 查看普通正文或密钥元数据 |
| `secret-set NAME` | 用户在交互终端隐藏输入密钥，新增或更新凭据 |
| `run NAME --env ENV -- COMMAND...` | 向当前子进程注入指定凭据并执行命令 |
| `delete NAME` | 删除普通条目，或删除对应系统凭据及索引 |

同一服务的开发、生产环境使用不同名称或项目说明，避免误用。`init --path` 切换绑定会保留旧资料库，不会自动搬迁内容。更新技能时只替换安装文件；卸载技能不会自动清空独立资料目录和系统凭据。备份或迁移资料目录只包含普通正文和索引，换机需要重新录入凭据。清空资料、删除密钥应由用户明确提出。

密钥更新和删除在索引提交失败时会尝试恢复原凭据；如果系统凭据库连恢复也无法确认，命令会失败并给出服务与账户标识，需检查系统凭据库或重新录入，不把这种情况报告为成功。

在仓库根目录运行测试：

```bash
python3 -m unittest discover -s skills/lzl-private/tests -v
```

测试使用隔离临时目录和虚拟凭据后端，不读取用户已有密钥。它们不能替代各系统上真实凭据库、权限弹窗及解锁行为的验证。
