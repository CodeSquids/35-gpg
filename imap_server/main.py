"""Point d'entrée : lance le serveur IMAP.

Usage :
    python -m imap_server.main
    python -m imap_server.main --host 0.0.0.0 --port 1143
    MAIL_HOST=127.0.0.1 IMAP_PORT=1143 python -m imap_server.main
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import create_tls_context, load_config  # noqa: E402
from imap_server.server.tcp_server import run_server  # noqa: E402


def main() -> None:
    cfg = load_config("imap")
    tls_context = create_tls_context(cfg)
    protocol = "IMAPS (TLS)" if tls_context else "IMAP"
    print(f"Démarrage du serveur {protocol} sur {cfg.host}:{cfg.port} (data: {cfg.data_dir})")
    asyncio.run(run_server(cfg.host, cfg.port, cfg.data_dir, tls_context))


if __name__ == "__main__":
    main()
