"""Security module: path validation and command filtering."""

import posixpath
import re
import logging
from .config import SecurityConfig

logger = logging.getLogger("ssh_mcp.security")


class SecurityError(Exception):
    """Raised when a security check fails."""


def normalize_remote_path(path: str) -> str:
    """Normalize a remote path: resolve . and .., remove trailing slashes."""
    # Normalize using posixpath (remote is Linux)
    normalized = posixpath.normpath(path)
    # Ensure root stays as /
    if normalized == "":
        normalized = "/"
    return normalized


def validate_path(remote_path: str, allowed_paths: list[str]) -> str:
    """Validate that remote_path is within one of the allowed_paths.

    Returns the normalized path if valid.
    Raises SecurityError if the path is not allowed.
    """
    normalized = normalize_remote_path(remote_path)

    for allowed in allowed_paths:
        allowed_normalized = normalize_remote_path(allowed)
        # Check if the path starts with an allowed directory
        if normalized == allowed_normalized or normalized.startswith(allowed_normalized + "/"):
            return normalized

    raise SecurityError(
        f"Access denied: '{remote_path}' is outside allowed paths. "
        f"Allowed: {allowed_paths}"
    )


def validate_command(command: str, security: SecurityConfig) -> None:
    """Validate that a command does not contain dangerous patterns.

    Raises SecurityError if the command is blocked.
    """
    cmd_lower = command.lower().strip()

    # Check against blocked command patterns
    for blocked in security.blocked_commands:
        if blocked.lower() in cmd_lower:
            raise SecurityError(
                f"Command blocked: contains dangerous pattern '{blocked}'. "
                f"Full command: {command}"
            )

    # Additional pattern-based checks
    _check_pipe_danger(cmd_lower, command)
    _check_redirect_danger(cmd_lower, command)
    _check_fork_bomb(cmd_lower, command)


def _check_pipe_danger(cmd_lower: str, command: str) -> None:
    """Block piping to dangerous commands."""
    dangerous_pipe_targets = [
        "rm ", "mkfs", "dd ", "format", "shutdown", "reboot",
        "chmod", "chown", "> /dev/",
    ]
    if "|" in cmd_lower:
        for target in dangerous_pipe_targets:
            if target in cmd_lower:
                raise SecurityError(
                    f"Command blocked: pipe to dangerous command detected. "
                    f"Full command: {command}"
                )


def _check_redirect_danger(cmd_lower: str, command: str) -> None:
    """Block redirecting to block devices or critical system files."""
    dangerous_redirects = [
        "> /dev/sd", "> /dev/nvme", "> /dev/vd",
        "> /etc/", "> /boot/", "> /usr/",
        ">> /dev/sd", ">> /dev/nvme",
    ]
    for pattern in dangerous_redirects:
        if pattern in cmd_lower:
            raise SecurityError(
                f"Command blocked: redirect to dangerous location detected. "
                f"Full command: {command}"
            )


def _check_fork_bomb(cmd_lower: str, command: str) -> None:
    """Block fork bombs."""
    fork_bomb_patterns = [
        ":(){:|:&};:", ":(){ :|:& };:", ".(){.||.&};.",
        "fork()", "while true; do", "for((;;))",
    ]
    # Only block obvious fork bombs, not all while/for loops
    for pattern in fork_bomb_patterns[:3]:  # Only the shell fork bomb patterns
        if pattern.replace(" ", "") in cmd_lower.replace(" ", ""):
            raise SecurityError(
                f"Command blocked: fork bomb pattern detected. "
                f"Full command: {command}"
            )


def check_file_size(size_bytes: int, max_size_mb: int) -> None:
    """Check if file size exceeds the limit."""
    max_bytes = max_size_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise SecurityError(
            f"File size ({size_bytes / 1024 / 1024:.1f} MB) exceeds limit ({max_size_mb} MB)."
        )
