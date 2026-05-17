"""uvicorn 啟動入口。"""

from __future__ import annotations

import argparse

import uvicorn

from aicentral.config import load_config
from aicentral.config.loader import get_config
from aicentral.gateway.localhost import validate_bind_host


def main(argv: list[str] | None = None) -> None:
    load_config(reload=True)
    cfg = get_config().gateway
    host = validate_bind_host(cfg.bind_host)
    port = cfg.bind_port

    parser = argparse.ArgumentParser(description="aicentral HTTP Gateway (localhost only)")
    parser.add_argument("--host", default=host, help="必須為 loopback")
    parser.add_argument("--port", type=int, default=port)
    args = parser.parse_args(argv)

    bind = validate_bind_host(args.host)
    uvicorn.run(
        "aicentral.gateway.app:app",
        host=bind,
        port=args.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
