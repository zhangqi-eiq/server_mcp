"""SSH Remote File MCP Server - Main server with tool definitions."""

import logging
import sys

from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent

from .config import load_config, ServerConfig
from .security import validate_path, validate_command, SecurityError
from .ssh_client import SSHClient

logger = logging.getLogger("ssh_mcp")


def create_server(config: ServerConfig | None = None) -> FastMCP:
    """Create and configure the MCP server with all tools."""

    if config is None:
        config = load_config()

    mcp = FastMCP("SSH Remote File Server", log_level="WARNING")
    ssh = SSHClient(config)

    def _format_size(size: int) -> str:
        """Format bytes to human-readable size."""
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    # ── Tool 1: Read File ──────────────────────────────────────────────

    @mcp.tool(
        description="""Read file contents from the remote server.

        Args:
            remote_path (str): Absolute path to the file on the remote server.
            encoding (str, optional): File encoding. Defaults to "utf-8".

        Returns:
            The file contents as text.
        """
    )
    def ssh_read_file(remote_path: str, encoding: str = "utf-8") -> TextContent:
        try:
            validated_path = validate_path(remote_path, config.allowed_paths)
            content = ssh.read_file(validated_path, encoding)
            return TextContent(type="text", text=content)
        except SecurityError as e:
            return TextContent(type="text", text=f"Security error: {e}")
        except FileNotFoundError as e:
            return TextContent(type="text", text=f"Error: {e}")
        except PermissionError as e:
            return TextContent(type="text", text=f"Error: {e}")
        except Exception as e:
            return TextContent(type="text", text=f"Error reading file: {e}")

    # ── Tool 2: Write File ─────────────────────────────────────────────

    @mcp.tool(
        description="""Write or create a file on the remote server. Auto-creates parent directories.

        Args:
            remote_path (str): Absolute path to the file on the remote server.
            content (str): Content to write to the file.
            encoding (str, optional): File encoding. Defaults to "utf-8".
            mode (str, optional): "overwrite" to replace file, "append" to add to end. Defaults to "overwrite".

        Returns:
            Confirmation message with bytes written.
        """
    )
    def ssh_write_file(
        remote_path: str, content: str, encoding: str = "utf-8", mode: str = "overwrite"
    ) -> TextContent:
        try:
            validated_path = validate_path(remote_path, config.allowed_paths)
            bytes_written = ssh.write_file(validated_path, content, encoding, mode)
            return TextContent(
                type="text",
                text=f"Successfully wrote {bytes_written} bytes to {validated_path} (mode: {mode})",
            )
        except SecurityError as e:
            return TextContent(type="text", text=f"Security error: {e}")
        except PermissionError as e:
            return TextContent(type="text", text=f"Error: {e}")
        except Exception as e:
            return TextContent(type="text", text=f"Error writing file: {e}")

    # ── Tool 3: Edit File ──────────────────────────────────────────────

    @mcp.tool(
        description="""Edit a file on the remote server by finding and replacing text.

        Args:
            remote_path (str): Absolute path to the file on the remote server.
            old_text (str): The exact text to find and replace.
            new_text (str): The replacement text.
            replace_all (bool, optional): If True, replace all occurrences. If False, replace only the first. Defaults to False.

        Returns:
            Confirmation message with number of replacements made.
        """
    )
    def ssh_edit_file(
        remote_path: str, old_text: str, new_text: str, replace_all: bool = False
    ) -> TextContent:
        try:
            validated_path = validate_path(remote_path, config.allowed_paths)
            count = ssh.edit_file(validated_path, old_text, new_text, replace_all)
            return TextContent(
                type="text",
                text=f"Successfully replaced {count} occurrence(s) in {validated_path}",
            )
        except SecurityError as e:
            return TextContent(type="text", text=f"Security error: {e}")
        except ValueError as e:
            return TextContent(type="text", text=f"Error: {e}")
        except FileNotFoundError as e:
            return TextContent(type="text", text=f"Error: {e}")
        except PermissionError as e:
            return TextContent(type="text", text=f"Error: {e}")
        except Exception as e:
            return TextContent(type="text", text=f"Error editing file: {e}")

    # ── Tool 4: List Directory ─────────────────────────────────────────

    @mcp.tool(
        description="""List directory contents on the remote server with details.

        Args:
            remote_path (str): Absolute path to the directory on the remote server.
            show_hidden (bool, optional): Whether to show hidden files (starting with .). Defaults to False.

        Returns:
            Formatted directory listing with file type, size, permissions, and modification time.
        """
    )
    def ssh_list_directory(remote_path: str, show_hidden: bool = False) -> TextContent:
        try:
            validated_path = validate_path(remote_path, config.allowed_paths)
            entries = ssh.list_directory(validated_path, show_hidden)

            if not entries:
                return TextContent(type="text", text=f"Directory is empty: {validated_path}")

            lines = [f"Directory: {validated_path}", f"Total: {len(entries)} items", ""]
            lines.append(f"{'Type':<5} {'Permissions':<12} {'Size':>10} {'Modified':<20} {'Name'}")
            lines.append("-" * 70)

            for entry in entries:
                type_char = "D" if entry["type"] == "directory" else "F"
                size_str = _format_size(entry["size"]) if entry["type"] == "file" else "-"
                lines.append(
                    f"{type_char:<5} {entry['permissions']:<12} {size_str:>10} {entry['modified']:<20} {entry['name']}"
                )

            return TextContent(type="text", text="\n".join(lines))
        except SecurityError as e:
            return TextContent(type="text", text=f"Security error: {e}")
        except FileNotFoundError as e:
            return TextContent(type="text", text=f"Error: {e}")
        except PermissionError as e:
            return TextContent(type="text", text=f"Error: {e}")
        except Exception as e:
            return TextContent(type="text", text=f"Error listing directory: {e}")

    # ── Tool 5: Run Command ────────────────────────────────────────────

    @mcp.tool(
        description="""Execute a shell command on the remote server. Dangerous commands are blocked by security filters.

        Args:
            command (str): The shell command to execute.
            workdir (str, optional): Working directory for the command. Must be within allowed paths.
            timeout (int, optional): Command timeout in seconds. Defaults to 30.

        Returns:
            Command output with stdout, stderr, and exit code.
        """
    )
    def ssh_run_command(command: str, workdir: str | None = None, timeout: int = 30) -> TextContent:
        try:
            validate_command(command, config.security)
            if workdir:
                validate_path(workdir, config.allowed_paths)

            result = ssh.run_command(command, workdir, min(timeout, 300))

            output_parts = []
            if result["stdout"]:
                output_parts.append(f"STDOUT:\n{result['stdout']}")
            if result["stderr"]:
                output_parts.append(f"STDERR:\n{result['stderr']}")
            output_parts.append(f"Exit code: {result['exit_code']}")

            return TextContent(type="text", text="\n\n".join(output_parts))
        except SecurityError as e:
            return TextContent(type="text", text=f"Security error: {e}")
        except RuntimeError as e:
            return TextContent(type="text", text=f"Error: {e}")
        except Exception as e:
            return TextContent(type="text", text=f"Error executing command: {e}")

    # ── Tool 6: Search Files ──────────────────────────────────────────

    @mcp.tool(
        description="""Search for files on the remote server by name or content.

        Args:
            search_path (str): Absolute path to the directory to search in.
            pattern (str): Search pattern (filename glob or content string).
            search_type (str, optional): "name" to search by filename, "content" to search file contents. Defaults to "name".
            max_results (int, optional): Maximum number of results. Defaults to 50.

        Returns:
            List of matching file paths.
        """
    )
    def ssh_search_files(
        search_path: str, pattern: str, search_type: str = "name", max_results: int = 50
    ) -> TextContent:
        try:
            validated_path = validate_path(search_path, config.allowed_paths)
            results = ssh.search_files(validated_path, pattern, search_type, max_results)

            if not results:
                return TextContent(type="text", text=f"No files found matching '{pattern}' in {validated_path}")

            return TextContent(type="text", text=f"Search results for '{pattern}' in {validated_path}:\n\n{results}")
        except SecurityError as e:
            return TextContent(type="text", text=f"Security error: {e}")
        except ValueError as e:
            return TextContent(type="text", text=f"Error: {e}")
        except Exception as e:
            return TextContent(type="text", text=f"Error searching files: {e}")

    # ── Tool 7: Get Environment Info ───────────────────────────────────

    @mcp.tool(
        description="""Get remote server environment information including OS, Python, disk, memory, and CPU.

        Args:
            (none)

        Returns:
            Formatted environment information from the remote server.
        """
    )
    def ssh_get_env_info() -> TextContent:
        try:
            info = ssh.get_env_info()

            lines = ["Remote Server Environment:", "=" * 40]
            for key, value in info.items():
                label = key.replace("_", " ").title()
                lines.append(f"{label}: {value}")

            return TextContent(type="text", text="\n".join(lines))
        except Exception as e:
            return TextContent(type="text", text=f"Error getting environment info: {e}")

    # ── Tool 8: File Info ──────────────────────────────────────────────

    @mcp.tool(
        description="""Get detailed information about a file or directory on the remote server.

        Args:
            remote_path (str): Absolute path to the file or directory.

        Returns:
            Detailed info including size, permissions, owner, timestamps, and type.
        """
    )
    def ssh_file_info(remote_path: str) -> TextContent:
        try:
            validated_path = validate_path(remote_path, config.allowed_paths)
            info = ssh.get_file_info(validated_path)

            lines = [f"File Info: {info['path']}", "=" * 40]
            lines.append(f"Type: {info['type']}")
            lines.append(f"Size: {_format_size(info['size'])}")
            lines.append(f"Permissions: {info['permissions']}")
            lines.append(f"Owner: {info['owner']}")
            lines.append(f"Modified: {info['modified']}")
            lines.append(f"Accessed: {info['accessed']}")
            if "symlink_target" in info:
                lines.append(f"Symlink target: {info['symlink_target']}")

            return TextContent(type="text", text="\n".join(lines))
        except SecurityError as e:
            return TextContent(type="text", text=f"Security error: {e}")
        except FileNotFoundError as e:
            return TextContent(type="text", text=f"Error: {e}")
        except PermissionError as e:
            return TextContent(type="text", text=f"Error: {e}")
        except Exception as e:
            return TextContent(type="text", text=f"Error getting file info: {e}")

    return mcp


def main():
    """Entry point for the MCP server."""
    # Setup logging to stderr (stdout is reserved for MCP protocol)
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    config = load_config()
    mcp = create_server(config)
    mcp.run()


if __name__ == "__main__":
    main()
