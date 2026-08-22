# SSH 远程文件 MCP 服务器

> 通过 Claude Code 像操作本地文件一样读写、编辑、运行远程服务器上的文件。

一个 [MCP](https://modelcontextprotocol.io/) 服务器，把远程 SSH 主机上的文件系统暴露成一组工具。注册到 Claude Code 后，你可以让它读取 `/home/you/proj/main.py`、改函数、跑 `pytest`、在远程目录里 grep —— 全部走 SSH，且全程受路径白名单和命令黑名单保护。

[English version →](README.md) ·
[GitHub →](https://github.com/zhangqi-eiq/server_mcp)

## 协议

MIT —— 详见 [LICENSE](LICENSE)。

---

## 功能一览

| 工具 | 作用 |
|------|------|
| `ssh_read_file` | 读取远程文件 |
| `ssh_write_file` | 创建 / 覆盖 / 追加写入远程文件 |
| `ssh_edit_file` | 在远程文件内做查找替换 |
| `ssh_list_directory` | 列出远程目录（含权限、大小、修改时间） |
| `ssh_run_command` | 在远程跑 Shell 命令（带安全过滤） |
| `ssh_search_files` | 按文件名或内容搜索文件 |
| `ssh_get_env_info` | OS / Python / 磁盘 / 内存 / CPU 快照 |
| `ssh_file_info` | 单个路径的详细 stat |

---

## 三步上手

```bash
# 1. 克隆并进入
git clone https://github.com/zhangqi-eiq/server_mcp.git
cd server_mcp

# 2. 安装
python install.py

# 3. 编辑你自己的凭据
#    默认位置: ~/.ssh-mcp-server/config.json

# 4. 重启 Claude Code，在对话里试试：
#    "看一下我这台机器的环境"
```

`install.py` 干三件事：

1. `pip install -e .` —— 安装包。
2. 把 `config.json`（带占位值）拷到 `~/.ssh-mcp-server/`。
3. 执行 `claude mcp add` 把服务器注册到 Claude Code。

如果 `claude` CLI 不在 PATH 里，跑 `python install.py --no-register`，然后按 [手动配置](#手动配置) 自己加。

---

## 手动配置

### 1. 安装包

```bash
pip install -e .
```

这会把 `ssh_mcp_server` 装到当前 Python 环境的 site-packages，
之后 `python -m ssh_mcp_server` 就能启动服务器。

### 2. 创建配置

把 `config.json` 拷到 `~/.ssh-mcp-server/config.json`（`SSH_MCP_CONFIG` 没设时加载器会找这里），再填上真实信息：

```bash
mkdir -p ~/.ssh-mcp-server
cp config.json ~/.ssh-mcp-server/config.json
$EDITOR ~/.ssh-mcp-server/config.json
```

### 3. 注册到 Claude Code

MCP 条目必须用你装包时的那个 Python 解释器。下面的 `<python>` 是
**绝对路径**（`sys.executable`，比如
Windows 下的 `C:\Users\you\.conda\envs\myenv\python.exe`，
Linux 下的 `/home/you/.venv/bin/python`）。

**方式 A —— 用户级，所有项目都能用：**

```bash
claude mcp add --scope user ssh-remote \
  -e SSH_MCP_CONFIG="$HOME/.ssh-mcp-server/config.json" \
  -- "<python>" -m ssh_mcp_server
```

**方式 B —— 项目级，只在当前项目生效：**

在项目根目录建 `.mcp.json`：

```json
{
  "mcpServers": {
    "ssh-remote": {
      "command": "<python 绝对路径>",
      "args": ["-m", "ssh_mcp_server"],
      "env": {
        "SSH_MCP_CONFIG": "/absolute/path/to/your/config.json"
      }
    }
  }
}
```

> 注意：Claude Code 从两个地方读 `mcpServers` —— `~/.claude.json`（CLI 管理的，
> `claude mcp add` 写到这里）和 `~/.claude/settings.json`（手编的）。上面用
> CLI 的方式会自动写到对的那个文件。

---

## 配置项参考

`config.json` 结构：

```json
{
  "ssh": {
    "host": "your-server.example.com",
    "port": 22,
    "username": "your-username",
    "auth": {
      "type": "password",
      "key_path": "",
      "password": "your-password",
      "key_password": ""
    },
    "connect_timeout": 10,
    "keepalive_interval": 30
  },
  "allowed_paths": [
    "/home/your-username/projects"
  ],
  "security": {
    "blocked_commands": ["rm -rf /", "mkfs", "..."],
    "max_file_size_mb": 50,
    "max_output_chars": 100000,
    "command_timeout": 30
  }
}
```

### SSH 连接 (`ssh`)

| 字段 | 说明 | 默认 |
|------|------|------|
| `ssh.host` | 服务器地址（IP 或域名） | 必填 |
| `ssh.port` | SSH 端口 | `22` |
| `ssh.username` | 登录用户名 | 必填 |
| `ssh.auth.type` | `"key"` 或 `"password"` | `"key"` |
| `ssh.auth.key_path` | 私钥路径（密钥认证时必填） | - |
| `ssh.auth.password` | 登录密码（密码认证时必填） | - |
| `ssh.auth.key_password` | 私钥本身的密码 | 空 |
| `ssh.connect_timeout` | 连接超时（秒） | `10` |
| `ssh.keepalive_interval` | 心跳间隔（秒） | `30` |

### 访问控制

- **`allowed_paths`** —— 允许访问的远程目录白名单。每个文件操作都会先做
  `..` 规范化再比对白名单，不在列表里的一律拒绝。子路径自动继承权限
  （例如 `/data/proj` 允许 `/data/proj/sub/file.py`）。
- **`security.blocked_commands`** —— `ssh_run_command` 拒绝执行的命令模式列表。
  默认已经拦了显而易见的危险命令（`rm -rf /`、`mkfs`、`shutdown`、fork bomb、
  直接写块设备、远程一键安装脚本）。可以扩展，**但不要为了"图方便"删掉**，
  详见 [安全模型](#安全模型)。

### 资源限制

| 字段 | 作用 | 默认 |
|------|------|------|
| `max_file_size_mb` | `ssh_read_file` 超过此大小的文件直接拒 | `50` |
| `max_output_chars` | `ssh_run_command` 输出截断长度 | `100000` |
| `command_timeout` | `ssh_run_command` 硬超时（秒） | `30` |

---

## 认证

### 密钥认证（推荐）

```bash
# 本地生成密钥对
ssh-keygen -t ed25519 -C "you@example.com"

# 把公钥推送到服务器
ssh-copy-id -i ~/.ssh/id_ed25519.pub user@server
```

然后 `config.json` 写：

```json
"auth": {
  "type": "key",
  "key_path": "~/.ssh/id_ed25519",
  "key_password": ""
}
```

`key_password` 只有私钥本身加密了才需要填。

### 密码认证

```json
"auth": {
  "type": "password",
  "password": "your-password"
}
```

密码是明文存在 `config.json` 里的，能用密钥就别用密码。

---

## GUI 管理器（可选）

自带的 Tk GUI 可以维护多台服务器的配置档案，一键切换：

```bash
# 直接从源码跑
python server_manager.py

# 或者打成 exe 放到 PATH（仅 Windows）
pip install -e ".[gui]"   # 安装 pyinstaller
python build.py
python setup_global.py
# 现在任意目录下 `SSH-Server-Manager` 就能起 GUI
```

档案存在 `profiles.json`；切换档案时会把它写进 `config.json`，MCP 服务器
下次启动时就读到新的了。

---

## 安全模型

这个服务器默认就偏保守。两层独立防护：

1. **路径白名单** —— 每个文件操作都先做路径规范化（解析 `..`、合并斜杠），
   再和 `allowed_paths` 比对。**没有办法绕出白名单**：校验在服务端，
   路径在远程解析。
2. **命令黑名单** —— `ssh_run_command` 拒绝任何子串命中
   `security.blocked_commands` 的命令。默认列表挡掉了递归删除、裸写块设备、
   系统关机、fork bomb、远程一键安装脚本（`curl … | sh`）。可以扩展，
   但**别为了"修一个合法需求"把整个黑名单删了**。

这个服务器**不**做的事：

- 不在远程以 root 跑。请用普通用户 SSH 登录。
- 不绕过 `sudo`。配置的用户不能 `sudo`，服务器也不行。
- 不提供交互式 Shell。长时间运行的进程会被 `command_timeout` 硬杀。

---

## 故障排查

| 现象 | 可能原因 | 修法 |
|------|----------|------|
| `claude mcp list` 啥也没有 | 注册到了错误的 scope，或 `claude` CLI 不读 `~/.claude/settings.json` | 用 `claude mcp add --scope user ...`（写到 `~/.claude.json`） |
| `ModuleNotFoundError: No module named 'mcp'` | 装到了一个 Python，Claude Code 用了另一个 | 用 Claude Code 实际调用的那个解释器跑 `install.py` |
| `ERROR: ssh.host is required` | 配置文件还是占位符 | 编辑 `~/.ssh-mcp-server/config.json`，把 `your-server.example.com`、`CHANGE_ME` 改成真实值 |
| `Access denied: outside allowed paths` | LLM 访问了不在白名单里的路径 | 把那个路径加到 `allowed_paths` |
| `Command blocked: dangerous pattern` | LLM 触发了黑名单 | 真的需要时再调 `security.blocked_commands` |
| `SSH authentication failed` | 用户名密码/密钥不对 | 先在普通 shell 里 `ssh user@host` 验证 |
| 服务器启动了但 Claude Code 看不到工具 | VSCode 扩展进程是旧的 | 完全退出 VSCode 再重开 |

---

## 目录结构

```
server/
├── ssh_mcp_server/         # MCP 服务器包（产品本体）
│   ├── server.py           #   工具定义
│   ├── ssh_client.py       #   paramiko 封装
│   ├── security.py         #   路径 + 命令校验
│   └── config.py           #   配置加载
├── server_manager.py       # Tk GUI（管理多台服务器）
├── profiles.json           # GUI 档案存储
├── config.json             # 运行配置模板（占位值）
├── setup.py                # pip 包元数据
├── install.py              # 一键安装脚本（装 + 注册）
├── setup_global.py         # 可选：把 GUI exe 部署到 PATH
├── build.py                # 可选：用 PyInstaller 打包 GUI
├── SSH-Server-Manager.spec # PyInstaller spec（细粒度打包用）
├── requirements.txt        # 原始依赖列表
├── LICENSE                 # MIT
├── README.md               # 英文文档
└── README.zh.md            # 中文文档（本文件）
```

---

## 协议

[MIT](LICENSE) —— 详见协议文件。
