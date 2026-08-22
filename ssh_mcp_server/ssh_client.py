"""SSH client for remote server operations."""

import io
import logging
import stat
import time
from datetime import datetime

import paramiko

from .config import ServerConfig, SSHConfig

logger = logging.getLogger("ssh_mcp.ssh")


class SSHClient:
    """Manages SSH connection and provides file/command operations."""

    def __init__(self, config: ServerConfig):
        self.config = config
        self.ssh_config = config.ssh
        self._client: paramiko.SSHClient | None = None
        self._sftp: paramiko.SFTPClient | None = None
        self._last_activity: float = 0

    def connect(self) -> None:
        """Establish SSH connection."""
        if self._client is not None:
            # Check if still alive
            transport = self._client.get_transport()
            if transport and transport.is_active():
                return
            self.close()

        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs = {
            "hostname": self.ssh_config.host,
            "port": self.ssh_config.port,
            "username": self.ssh_config.username,
            "timeout": self.ssh_config.connect_timeout,
        }

        auth = self.ssh_config.auth
        if auth.auth_type == "key":
            connect_kwargs["key_filename"] = auth.key_path
            if auth.key_password:
                connect_kwargs["passphrase"] = auth.key_password
        elif auth.auth_type == "password":
            connect_kwargs["password"] = auth.password

        try:
            self._client.connect(**connect_kwargs)
            # Enable keepalive
            transport = self._client.get_transport()
            if transport:
                transport.set_keepalive(self.ssh_config.keepalive_interval)
            self._sftp = self._client.open_sftp()
            self._last_activity = time.time()
            logger.info(f"Connected to {self.ssh_config.host}:{self.ssh_config.port}")
        except paramiko.AuthenticationException:
            self.close()
            raise ConnectionError("SSH authentication failed. Check credentials.")
        except paramiko.SSHException as e:
            self.close()
            raise ConnectionError(f"SSH connection error: {e}")
        except Exception as e:
            self.close()
            raise ConnectionError(f"Failed to connect: {e}")

    def close(self) -> None:
        """Close SSH connection."""
        if self._sftp:
            try:
                self._sftp.close()
            except Exception:
                pass
            self._sftp = None
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def _ensure_connected(self) -> None:
        """Ensure connection is alive, reconnect if needed."""
        if self._client is None:
            self.connect()
            return
        transport = self._client.get_transport()
        if transport is None or not transport.is_active():
            logger.info("Connection lost, reconnecting...")
            self.connect()

    def read_file(self, remote_path: str, encoding: str = "utf-8") -> str:
        """Read file contents from remote server."""
        self._ensure_connected()
        try:
            # Check file size first
            stat_info = self._sftp.stat(remote_path)
            max_bytes = self.config.security.max_file_size_mb * 1024 * 1024
            if stat_info.st_size > max_bytes:
                raise ValueError(
                    f"File size ({stat_info.st_size / 1024 / 1024:.1f} MB) "
                    f"exceeds limit ({self.config.security.max_file_size_mb} MB)."
                )

            with self._sftp.open(remote_path, "r") as f:
                content = f.read()
            if isinstance(content, bytes):
                content = content.decode(encoding)
            self._last_activity = time.time()
            return content
        except FileNotFoundError:
            raise FileNotFoundError(f"File not found: {remote_path}")
        except PermissionError:
            raise PermissionError(f"Permission denied: {remote_path}")

    def write_file(
        self, remote_path: str, content: str, encoding: str = "utf-8", mode: str = "overwrite"
    ) -> int:
        """Write content to a remote file. Returns bytes written."""
        self._ensure_connected()
        try:
            # Check content size
            content_bytes = content.encode(encoding)
            max_bytes = self.config.security.max_file_size_mb * 1024 * 1024
            if len(content_bytes) > max_bytes:
                raise ValueError(
                    f"Content size ({len(content_bytes) / 1024 / 1024:.1f} MB) "
                    f"exceeds limit ({self.config.security.max_file_size_mb} MB)."
                )

            # Create parent directories if needed
            parent_dir = remote_path.rsplit("/", 1)[0] if "/" in remote_path else ""
            if parent_dir:
                self._ensure_directory(parent_dir)

            file_mode = "a" if mode == "append" else "w"
            with self._sftp.open(remote_path, file_mode) as f:
                f.write(content_bytes)
            self._last_activity = time.time()
            return len(content_bytes)
        except PermissionError:
            raise PermissionError(f"Permission denied: {remote_path}")

    def edit_file(
        self, remote_path: str, old_text: str, new_text: str, replace_all: bool = False
    ) -> int:
        """Edit file by replacing text. Returns number of replacements made."""
        self._ensure_connected()
        content = self.read_file(remote_path)

        if old_text not in content:
            raise ValueError(f"Text not found in {remote_path}:\n{old_text}")

        if replace_all:
            count = content.count(old_text)
            new_content = content.replace(old_text, new_text)
        else:
            count = 1
            new_content = content.replace(old_text, new_text, 1)

        self.write_file(remote_path, new_content)
        return count

    def list_directory(self, remote_path: str, show_hidden: bool = False) -> list[dict]:
        """List directory contents with details."""
        self._ensure_connected()
        try:
            entries = []
            for entry in self._sftp.listdir_attr(remote_path):
                name = entry.filename
                if not show_hidden and name.startswith("."):
                    continue

                full_path = f"{remote_path.rstrip('/')}/{name}"
                is_dir = stat.S_ISDIR(entry.st_mode)
                size = entry.st_size if not is_dir else 0
                permissions = stat.filemode(entry.st_mode) if entry.st_mode else "----------"
                mtime = datetime.fromtimestamp(entry.st_mtime).strftime("%Y-%m-%d %H:%M:%S") if entry.st_mtime else "unknown"

                entries.append({
                    "name": name,
                    "path": full_path,
                    "type": "directory" if is_dir else "file",
                    "size": size,
                    "permissions": permissions,
                    "modified": mtime,
                })

            self._last_activity = time.time()
            # Sort: directories first, then by name
            entries.sort(key=lambda e: (0 if e["type"] == "directory" else 1, e["name"]))
            return entries
        except FileNotFoundError:
            raise FileNotFoundError(f"Directory not found: {remote_path}")
        except PermissionError:
            raise PermissionError(f"Permission denied: {remote_path}")

    def run_command(
        self, command: str, workdir: str | None = None, timeout: int = 30
    ) -> dict:
        """Execute a command on the remote server.

        Returns dict with: stdout, stderr, exit_code
        """
        self._ensure_connected()

        # Build full command with optional working directory
        if workdir:
            full_command = f"cd {workdir} && {command}"
        else:
            full_command = command

        try:
            stdin, stdout, stderr = self._client.exec_command(
                full_command, timeout=timeout
            )

            exit_code = stdout.channel.recv_exit_status()
            stdout_str = stdout.read().decode("utf-8", errors="replace")
            stderr_str = stderr.read().decode("utf-8", errors="replace")

            # Truncate if too long
            max_chars = self.config.security.max_output_chars
            if len(stdout_str) > max_chars:
                stdout_str = stdout_str[:max_chars] + f"\n... (truncated, {len(stdout_str)} total chars)"
            if len(stderr_str) > max_chars:
                stderr_str = stderr_str[:max_chars] + f"\n... (truncated, {len(stderr_str)} total chars)"

            self._last_activity = time.time()
            return {
                "stdout": stdout_str,
                "stderr": stderr_str,
                "exit_code": exit_code,
            }
        except paramiko.SSHException as e:
            raise RuntimeError(f"Command execution failed: {e}")

    def search_files(
        self, search_path: str, pattern: str, search_type: str = "name", max_results: int = 50
    ) -> str:
        """Search for files by name or content."""
        self._ensure_connected()

        if search_type == "name":
            cmd = f"find {search_path} -name '*{pattern}*' -maxdepth 10 2>/dev/null | head -{max_results}"
        elif search_type == "content":
            # Use grep -r for recursive content search
            cmd = f"grep -rl '{pattern}' {search_path} 2>/dev/null | head -{max_results}"
        else:
            raise ValueError(f"Invalid search_type: {search_type}. Use 'name' or 'content'.")

        result = self.run_command(cmd, timeout=30)
        return result["stdout"].strip()

    def get_file_info(self, remote_path: str) -> dict:
        """Get detailed info about a file or directory."""
        self._ensure_connected()
        try:
            stat_info = self._sftp.stat(remote_path)
            is_dir = stat.S_ISDIR(stat_info.st_mode)
            is_link = stat.S_ISLNK(stat_info.st_mode)

            permissions = stat.filemode(stat_info.st_mode) if stat_info.st_mode else "----------"
            mtime = datetime.fromtimestamp(stat_info.st_mtime).strftime("%Y-%m-%d %H:%M:%S") if stat_info.st_mtime else "unknown"
            atime = datetime.fromtimestamp(stat_info.st_atime).strftime("%Y-%m-%d %H:%M:%S") if stat_info.st_atime else "unknown"

            # Get owner/group via command (SFTP stat doesn't always provide this)
            owner_info = self.run_command(f"stat -c '%U:%G' '{remote_path}' 2>/dev/null || echo 'unknown:unknown'")
            owner = owner_info["stdout"].strip()

            result = {
                "path": remote_path,
                "type": "directory" if is_dir else ("symlink" if is_link else "file"),
                "size": stat_info.st_size if not is_dir else 0,
                "permissions": permissions,
                "owner": owner,
                "modified": mtime,
                "accessed": atime,
            }

            # If it's a symlink, get the target
            if is_link:
                try:
                    target = self._sftp.readlink(remote_path)
                    result["symlink_target"] = target
                except Exception:
                    pass

            self._last_activity = time.time()
            return result
        except FileNotFoundError:
            raise FileNotFoundError(f"Path not found: {remote_path}")
        except PermissionError:
            raise PermissionError(f"Permission denied: {remote_path}")

    def get_env_info(self) -> dict:
        """Get remote server environment information."""
        self._ensure_connected()

        commands = {
            "os_info": "cat /etc/os-release 2>/dev/null | head -5 || uname -a",
            "kernel": "uname -r",
            "hostname": "hostname",
            "python_version": "python3 --version 2>/dev/null || python --version 2>/dev/null || echo 'not found'",
            "disk_usage": "df -h / 2>/dev/null | tail -1",
            "memory": "free -h 2>/dev/null | head -2 || echo 'free not available'",
            "cpu": "nproc 2>/dev/null || echo 'unknown'",
            "uptime": "uptime 2>/dev/null || echo 'unknown'",
            "shell": "echo $SHELL",
            "user": "whoami",
        }

        info = {}
        for key, cmd in commands.items():
            result = self.run_command(cmd, timeout=10)
            info[key] = result["stdout"].strip() if result["exit_code"] == 0 else result["stderr"].strip()

        return info

    def _ensure_directory(self, remote_path: str) -> None:
        """Ensure a remote directory exists, creating it if needed."""
        try:
            self._sftp.stat(remote_path)
        except FileNotFoundError:
            # Create parent first
            parent = remote_path.rsplit("/", 1)[0] if "/" in remote_path else ""
            if parent and parent != "/":
                self._ensure_directory(parent)
            try:
                self._sftp.mkdir(remote_path)
            except OSError:
                # Directory may have been created by another process
                pass

    def __del__(self):
        self.close()
