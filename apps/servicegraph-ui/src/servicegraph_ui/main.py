"""Visualization service entrypoint."""

from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run(
        "servicegraph_ui.api:create_app",
        factory=True,
        host="0.0.0.0",
        port=8080,
        workers=1,
    )


if __name__ == "__main__":
    main()
