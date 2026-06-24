"""Entry point for ``python -m frontprompt``.

Required so the MCP-daemon's child-spawn (``python -m frontprompt show <url>``
in :mod:`frontprompt.mcp_spawn`) can execute the package as a script.
"""

from frontprompt.cli import main

if __name__ == "__main__":
    main()
