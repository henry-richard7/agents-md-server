"""agents-md-server main entrypoint shim.

Delegates to the production agents_md_server CLI.
"""

from agents_md_server.cli import main

if __name__ == "__main__":
    main()
