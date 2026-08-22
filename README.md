# SSH Remote File MCP Server

> Read, edit, and run commands on a remote server through Claude Code — as if the
> files were local.

An [MCP](https://modelcontextprotocol.io/) server that exposes a remote SSH host as
a set of file-system tools. Once registered with Claude Code you can ask it to
read `/home/you/proj/main.py`, edit a function, run `pytest`, or grep across the
remote tree — and it talks to the server over SSH, with path-scoping and command
filtering on the way.

[中文文档 / Chinese version →](README.zh.md) ·
[GitHub →](https://github.com/zhangqi-eiq/server_mcp)

## License

MIT — see [LICENSE](LICENSE).

---

## Features

| Tool | Purpose |
|------|---------|
| `ssh_read_file` | Read a remote file |
| `ssh_write_file` | Create or overwrite (also append) a remote file |
| `ssh_edit_file` | Find-and-replace inside a remote file |
| `ssh_list_directory` | List a remote directory with permissions, size, mtime |
| `ssh_run_command` | Run a shell command on the remote (with safety filters) |
| `ssh_search_files` | Find files by name glob or content |
| `ssh_get_env_info` | OS / Python / disk / memory / CPU snapshot |
| `ssh_file_info` | Detailed stat for a single path |

---

## Quick start

```bash
# 1. Clone and enter
git clone https://github.com/zhangqi-eiq/server_mcp.git
cd server_mcp

# 2. Install (editable mode — picks up code changes immediately)
python install.py

# 3. Edit your real credentials
#    (file is at ~/.ssh-mcp-server/config.json by default)

# 4. Restart Claude Code, then in a chat:
#    "show me the env of my server"
```

That's it. `install.py` does three things:

1. `pip install -e .` — installs the package.
2. Copies `config.json` (with placeholder values) to `~/.ssh-mcp-server/`.
3. Runs `claude mcp add` so the server shows up in Claude Code.

If you do not have the `claude` CLI yet, run `python install.py --no-register`
and add the MCP entry by hand (see [Manual configuration](#manual-configuration)).

---

## Manual configuration

If you prefer to wire things up by hand, or `install.py` did not register
correctly:

### 1. Install the package

```bash
pip install -e .
```

This puts `ssh_mcp_server` on Python's import path so that
`python -m ssh_mcp_server` can launch the server.

### 2. Create your config

Copy `config.json` to `~/.ssh-mcp-server/config.json` (the loader looks here
when `SSH_MCP_CONFIG` is unset) and fill in real values:

```bash
mkdir -p ~/.ssh-mcp-server
cp config.json ~/.ssh-mcp-server/config.json
$EDITOR ~/.ssh-mcp-server/config.json
```

### 3. Register with Claude Code

The MCP entry must invoke the server via the Python interpreter you installed
into. `<python>` below should be the **absolute path** to that interpreter
(`sys.executable` from your activated env, e.g.
`C:\Users\you\.conda\envs\myenv\python.exe` on Windows or
`/home/you/.venv/bin/python` on Linux).

**Option A — user-scope, available in every project:**

```bash
claude mcp add --scope user ssh-remote \
  -e SSH_MCP_CONFIG="$HOME/.ssh-mcp-server/config.json" \
  -- "<python>" -m ssh_mcp_server
```

**Option B — project-scope, only this project:**

Create `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "ssh-remote": {
      "command": "<absolute path to python>",
      "args": ["-m", "ssh_mcp_server"],
      "env": {
        "SSH_MCP_CONFIG": "/absolute/path/to/your/config.json"
      }
    }
  }
}
```

> Note: Claude Code looks for `mcpServers` in two places — `~/.claude.json`
> (CLI-managed, written by `claude mcp add`) and `~/.claude/settings.json`
> (hand-edited). The CLI route above writes to the right one automatically.

---

## Configuration reference

`config.json` shape:

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
    "blocked_commands": ["rm -rf /", "mkfs", ...],
    "max_file_size_mb": 50,
    "max_output_chars": 100000,
    "command_timeout": 30
  }
}
```

### SSH connection

| Field | Description | Default |
|-------|-------------|---------|
| `ssh.host` | Server address (IP or domain) | required |
| `ssh.port` | SSH port | `22` |
| `ssh.username` | Login username | required |
| `ssh.auth.type` | `"key"` or `"password"` | `"key"` |
| `ssh.auth.key_path` | Path to private key (key auth) | required if `type=key` |
| `ssh.auth.password` | Login password (password auth) | required if `type=password` |
| `ssh.auth.key_password` | Passphrase for the key | empty |
| `ssh.connect_timeout` | Seconds | `10` |
| `ssh.keepalive_interval` | Seconds between keepalives | `30` |

### Access control

- **`allowed_paths`** — whitelist of remote directories. Every file operation is
  validated against this list after `..` normalization. Requests outside the
  list are rejected. Sub-paths inherit access (e.g. `/data/proj` allows
  `/data/proj/sub/file.py`).
- **`security.blocked_commands`** — list of shell command patterns that
  `ssh_run_command` refuses to execute. The defaults cover obvious foot-guns
  (`rm -rf /`, `mkfs`, `shutdown`, fork bombs, raw writes to block devices).
  You can extend the list, but **never weaken it to "fix" a legitimate need** —
  see [Security model](#security-model).

### Resource limits

| Field | Effect | Default |
|-------|--------|---------|
| `max_file_size_mb` | `ssh_read_file` refuses files larger than this | `50` |
| `max_output_chars` | `ssh_run_command` truncates output past this many chars | `100000` |
| `command_timeout` | `ssh_run_command` hard-kills after this many seconds | `30` |

---

## Authentication

### Key-based (recommended)

```bash
# On your local machine
ssh-keygen -t ed25519 -C "you@example.com"

# Push the public key to the remote
ssh-copy-id -i ~/.ssh/id_ed25519.pub user@server
```

Then in `config.json`:

```json
"auth": {
  "type": "key",
  "key_path": "~/.ssh/id_ed25519",
  "key_password": ""
}
```

`key_password` is only needed if the private key itself is encrypted.

### Password-based

```json
"auth": {
  "type": "password",
  "password": "your-password"
}
```

The password is stored in plain text in `config.json`. Prefer key auth.

---

## GUI manager (optional)

A small Tk-based GUI lets you maintain multiple server profiles and switch
between them:

```bash
# From source
python server_manager.py

# Or build a standalone Windows exe and put it on PATH
pip install -e ".[gui]"   # adds pyinstaller
python build.py
python setup_global.py
# now `SSH-Server-Manager` is on PATH
```

Profiles live in `profiles.json`; switching copies the selected profile into
`config.json` so the MCP server picks it up on next launch.

---

## Security model

This server is intentionally conservative. Two independent layers protect the
remote host:

1. **Path scoping.** Every file operation is normalized (resolving `..`,
   collapsing slashes) and then checked against `allowed_paths`. There is no
   way to escape the list — the check happens server-side after the path is
   resolved on the remote.
2. **Command filtering.** `ssh_run_command` rejects any command matching
   `security.blocked_commands` (substring match). The default list blocks
   recursive destruction, raw device writes, system shutdown, fork bombs, and
   remote shell installers (`curl … | sh`). Extend the list if you need to
   allow something specific — but do not gut it.

Things this server does **not** do:

- It does not run as root on the remote. SSH to a non-root user.
- It does not bypass `sudo`. If the configured user can't `sudo`, neither can
  the server.
- It does not provide an interactive shell. Long-running processes are killed
  by `command_timeout`.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `claude mcp list` shows nothing | Server registered to wrong scope, or `claude` CLI version doesn't read `~/.claude/settings.json` | Use `claude mcp add --scope user ...` (writes `~/.claude.json`) |
| `ModuleNotFoundError: No module named 'mcp'` | Installed into a different Python than `claude` is using | Run `install.py` with the interpreter you intend Claude Code to use |
| `ERROR: ssh.host is required` | Config still has placeholder values | Edit `~/.ssh-mcp-server/config.json` and replace `your-server.example.com`, `CHANGE_ME`, etc. |
| `Access denied: outside allowed paths` | The path the LLM tried isn't in `allowed_paths` | Add the path to `allowed_paths` in your config |
| `Command blocked: dangerous pattern` | The LLM tried a blacklisted command | Adjust `security.blocked_commands` if you really need it |
| `SSH authentication failed` | Wrong credentials or wrong user | Verify with `ssh user@host` in a normal shell |
| Server starts but Claude Code shows no tools | Stale VSCode extension process | Fully quit and reopen VSCode |

---

## Project layout

```
server/
├── ssh_mcp_server/         # MCP server package (the actual product)
│   ├── server.py           #   tool definitions
│   ├── ssh_client.py       #   paramiko wrapper
│   ├── security.py         #   path + command validation
│   └── config.py           #   config loader
├── server_manager.py       # Tk GUI for managing profiles
├── profiles.json           # GUI profile store
├── config.json             # runtime config template (placeholder values)
├── setup.py                # pip-installable package metadata
├── install.py              # one-shot installer (install + register)
├── setup_global.py         # optional: deploy GUI exe to PATH
├── build.py                # optional: PyInstaller wrapper for the GUI
├── SSH-Server-Manager.spec # PyInstaller spec for fine-grained builds
├── requirements.txt        # raw dependency pins
├── LICENSE                 # MIT
├── README.md               # this file (English)
└── README.zh.md            # Chinese translation
```

---

## License

[MIT](LICENSE) — see the file for the full text.
