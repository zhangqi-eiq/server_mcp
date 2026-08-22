"""Configuration loading and validation for SSH MCP Server."""

import json
import os
import sys
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class SSHAuthConfig:
    auth_type: str = "key"  # "key" or "password"
    key_path: str = ""
    password: str = ""
    key_password: str = ""


@dataclass
class SSHConfig:
    host: str = ""
    port: int = 22
    username: str = ""
    auth: SSHAuthConfig = field(default_factory=SSHAuthConfig)
    connect_timeout: int = 10
    keepalive_interval: int = 30


@dataclass
class SecurityConfig:
    blocked_commands: list[str] = field(default_factory=lambda: [
        "rm -rf /", "rm -rf /*", "mkfs", "dd if=", "format",
        "shutdown", "reboot", "halt", "poweroff", "init 0", "init 6",
        ":(){:|:&};:", "chmod -R 777 /", "chown -R",
        "> /dev/sd", "echo > /dev/sd",
    ])
    max_file_size_mb: int = 50
    max_output_chars: int = 100000
    command_timeout: int = 30


@dataclass
class ServerConfig:
    ssh: SSHConfig = field(default_factory=SSHConfig)
    allowed_paths: list[str] = field(default_factory=list)
    security: SecurityConfig = field(default_factory=SecurityConfig)


def _expand_path(path: str) -> str:
    """Expand ~ and resolve to absolute path."""
    return str(Path(os.path.expanduser(path)).resolve())


def _create_default_config(path: Path):
    """Create a minimal default config file."""
    import json
    default = {
        "ssh": {
            "host": "your-server-ip",
            "port": 22,
            "username": "your-username",
            "auth": {
                "type": "key",
                "key_path": "~/.ssh/id_rsa",
                "password": "",
                "key_password": "",
            },
            "connect_timeout": 10,
            "keepalive_interval": 30,
        },
        "allowed_paths": ["/home/your-username/projects"],
        "security": {
            "blocked_commands": [
                "rm -rf /", "rm -rf /*", "mkfs", "dd if=", "format",
                "shutdown", "reboot", "halt", "poweroff", "init 0", "init 6",
                ":(){:|:&};:", "chmod -R 777 /", "chown -R",
                "> /dev/sd", "echo > /dev/sd",
            ],
            "max_file_size_mb": 50,
            "max_output_chars": 100000,
            "command_timeout": 30,
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(default, f, indent=2, ensure_ascii=False)


def load_config(config_path: str | None = None) -> ServerConfig:
    """Load and validate configuration from JSON file.

    Config source priority:
    1. Explicit config_path argument
    2. SSH_MCP_CONFIG environment variable
    3. config.json next to the script/package
    4. ~/.ssh-mcp-server/config.json (user home directory)
    """
    if config_path is None:
        config_path = os.environ.get("SSH_MCP_CONFIG")

    if config_path is None:
        # Search in multiple locations
        candidates = [
            Path(__file__).parent.parent / "config.json",  # next to package
            Path.home() / ".ssh-mcp-server" / "config.json",  # user home
        ]
        for candidate in candidates:
            if candidate.exists():
                config_path = str(candidate)
                break

    if config_path is None:
        # Auto-create default config in user home
        default_dir = Path.home() / ".ssh-mcp-server"
        default_dir.mkdir(parents=True, exist_ok=True)
        default_config = default_dir / "config.json"
        if not default_config.exists():
            import shutil
            template = Path(__file__).parent.parent / "config.json"
            if template.exists():
                shutil.copy2(template, default_config)
            else:
                _create_default_config(default_config)
        config_path = str(default_config)
        print(f"Using config: {config_path}", file=sys.stderr)

    config_path = _expand_path(config_path)

    if not os.path.isfile(config_path):
        print(f"ERROR: Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # Parse SSH config
    ssh_raw = raw.get("ssh", {})
    auth_raw = ssh_raw.get("auth", {})
    auth = SSHAuthConfig(
        auth_type=auth_raw.get("type", "key"),
        key_path=_expand_path(auth_raw["key_path"]) if auth_raw.get("key_path") else "",
        password=auth_raw.get("password", ""),
        key_password=auth_raw.get("key_password", ""),
    )
    ssh = SSHConfig(
        host=ssh_raw.get("host", ""),
        port=ssh_raw.get("port", 22),
        username=ssh_raw.get("username", ""),
        auth=auth,
        connect_timeout=ssh_raw.get("connect_timeout", 10),
        keepalive_interval=ssh_raw.get("keepalive_interval", 30),
    )

    # Parse security config
    sec_raw = raw.get("security", {})
    security = SecurityConfig(
        blocked_commands=sec_raw.get("blocked_commands", SecurityConfig().blocked_commands),
        max_file_size_mb=sec_raw.get("max_file_size_mb", 50),
        max_output_chars=sec_raw.get("max_output_chars", 100000),
        command_timeout=sec_raw.get("command_timeout", 30),
    )

    # Parse allowed paths - resolve to absolute on remote (we store as-is for remote validation)
    allowed_paths = raw.get("allowed_paths", [])
    if not allowed_paths:
        print("ERROR: allowed_paths is empty. Specify at least one allowed remote path.", file=sys.stderr)
        sys.exit(1)

    # Validate SSH config
    if not ssh.host:
        print("ERROR: ssh.host is required.", file=sys.stderr)
        sys.exit(1)
    if not ssh.username:
        print("ERROR: ssh.username is required.", file=sys.stderr)
        sys.exit(1)
    if ssh.auth.auth_type == "key" and not ssh.auth.key_path:
        print("ERROR: ssh.auth.key_path is required for key authentication.", file=sys.stderr)
        sys.exit(1)
    if ssh.auth.auth_type == "password" and not ssh.auth.password:
        print("ERROR: ssh.auth.password is required for password authentication.", file=sys.stderr)
        sys.exit(1)

    return ServerConfig(ssh=ssh, allowed_paths=allowed_paths, security=security)
