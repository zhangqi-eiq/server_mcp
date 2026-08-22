"""One-shot installer for ssh-mcp-server.

Steps performed:
1. Install this package (and its dependencies) into the active Python env.
2. Stage a config directory at ``~/.ssh-mcp-server`` if not already present.
3. Register the MCP server with Claude Code via ``claude mcp add``.

The script is idempotent — running it twice does not duplicate the registration.

Usage::

    python install.py            # install + register
    python install.py --no-register   # only install
    python install.py --uninstall     # undo registration + remove installed pkg

Requirements: Python 3.10+, ``claude`` CLI on PATH (for the register step).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).parent.resolve()
USER_CONFIG_DIR = Path.home() / ".ssh-mcp-server"
USER_CONFIG_FILE = USER_CONFIG_DIR / "config.json"
TEMPLATE_CONFIG = PACKAGE_DIR / "config.json"

MCP_SERVER_NAME = "ssh-remote"


def _step(label: str) -> None:
    print(f"\n── {label} " + "─" * max(0, 60 - len(label)))


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a subprocess, streaming output on failure."""
    try:
        return subprocess.run(cmd, check=True, **kwargs)
    except subprocess.CalledProcessError as e:
        print(f"  ✗ Command failed (exit {e.returncode}): {' '.join(cmd)}")
        sys.exit(e.returncode)


def install_package() -> None:
    _step("Installing package into current Python environment")
    print(f"  Python: {sys.executable}")
    cmd = [sys.executable, "-m", "pip", "install", "-e", str(PACKAGE_DIR)]
    print(f"  $ {' '.join(cmd)}")
    _run(cmd)
    print("  ✓ Package installed (editable mode)")


def stage_user_config() -> None:
    _step("Staging user-level config directory")
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    print(f"  Directory: {USER_CONFIG_DIR}")
    if not USER_CONFIG_FILE.exists():
        if TEMPLATE_CONFIG.exists():
            shutil.copy2(TEMPLATE_CONFIG, USER_CONFIG_FILE)
            print(f"  ✓ Copied template → {USER_CONFIG_FILE}")
        else:
            print(f"  ✗ Template missing: {TEMPLATE_CONFIG}")
            sys.exit(1)
    else:
        print(f"  -- {USER_CONFIG_FILE} already exists, leaving untouched")
    print()
    print("  ▸ Edit this file with your real server credentials before using:")
    print(f"      {USER_CONFIG_FILE}")


def register_with_claude() -> bool:
    _step(f"Registering MCP server '{MCP_SERVER_NAME}' with Claude Code")
    if shutil.which("claude") is None:
        print("  ✗ `claude` CLI not found on PATH")
        print("    Install Claude Code first: https://docs.claude.com/claude-code")
        return False

    # Check whether already registered
    list_result = subprocess.run(
        ["claude", "mcp", "list"], capture_output=True, text=True
    )
    if list_result.returncode == 0 and MCP_SERVER_NAME in list_result.stdout:
        print(f"  -- '{MCP_SERVER_NAME}' already registered, skipping")
        return True

    cmd = [
        "claude", "mcp", "add", "--scope", "user", MCP_SERVER_NAME,
        "--", "ssh-mcp-server",
    ]
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ✗ Registration failed: {result.stderr.strip()}")
        return False
    print(f"  ✓ Registered")
    print(result.stdout.strip())
    return True


def uninstall() -> None:
    _step("Uninstalling")
    if shutil.which("claude") is not None:
        subprocess.run(
            ["claude", "mcp", "remove", MCP_SERVER_NAME],
            capture_output=True, text=True,
        )
        print(f"  ✓ Removed '{MCP_SERVER_NAME}' from Claude Code (if present)")

    cmd = [sys.executable, "-m", "pip", "uninstall", "-y", "ssh-mcp-server"]
    print(f"  $ {' '.join(cmd)}")
    subprocess.run(cmd)

    if USER_CONFIG_DIR.exists() and not any(USER_CONFIG_DIR.iterdir()):
        USER_CONFIG_DIR.rmdir()
        print(f"  ✓ Removed empty {USER_CONFIG_DIR}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--no-register", action="store_true",
                        help="Skip Claude Code registration")
    parser.add_argument("--uninstall", action="store_true",
                        help="Reverse the install steps")
    args = parser.parse_args()

    if args.uninstall:
        uninstall()
        return

    print("=" * 60)
    print(" ssh-mcp-server installer")
    print("=" * 60)

    install_package()
    stage_user_config()

    if not args.no_register:
        ok = register_with_claude()
        if ok:
            print("\n" + "=" * 60)
            print(" ✓ Done. Restart Claude Code to pick up the new MCP server.")
            print("=" * 60)
            print(f"\nNext steps:")
            print(f"  1. Edit {USER_CONFIG_FILE} with your server info")
            print(f"  2. Restart Claude Code (full quit + reopen for VSCode extension)")
            print(f"  3. Try the `ssh_get_env_info` tool in a chat")


if __name__ == "__main__":
    main()
