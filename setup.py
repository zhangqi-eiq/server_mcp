"""Package metadata for ssh-mcp-server.

Install in editable mode::

    pip install -e .

Or with the optional GUI manager build extras::

    pip install -e ".[gui]"

After install, the ``ssh-mcp-server`` command is on PATH and can be
registered with Claude Code via ``claude mcp add ssh-remote -- ssh-mcp-server``.
"""

from setuptools import setup, find_packages

setup(
    name="ssh-mcp-server",
    version="0.1.0",
    description="MCP server for remote file access over SSH — use Claude Code to edit files on remote servers as if they were local.",
    long_description=open("README.md", encoding="utf-8").read()
    if __import__("os").path.isfile("README.md")
    else None,
    long_description_content_type="text/markdown",
    author="SSH Remote File MCP Server Contributors",
    license="MIT",
    python_requires=">=3.10",
    packages=find_packages(exclude=["build", "dist", "*.tests", "*.tests.*"]),
    include_package_data=True,
    install_requires=[
        "mcp[cli]>=1.6.0,<2.0.0",
        "paramiko>=3.0.0",
    ],
    extras_require={
        # Required to build the GUI manager (SSH-Server-Manager.exe) via build.py
        "gui": ["pyinstaller>=6.0"],
    },
    entry_points={
        "console_scripts": [
            "ssh-mcp-server=ssh_mcp_server.server:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development",
    ],
)
