from __future__ import annotations

from pathlib import Path

from txtest.ui.app import TxTestApp


def main() -> None:
    TxTestApp(Path.cwd()).run()


if __name__ == "__main__":
    main()
