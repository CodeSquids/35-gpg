"""Point d'entrée : lance le serveur SMTP (livraison locale uniquement).

Usage :
    python -m smtp_server.main
    python -m smtp_server.main --host 0.0.0.0 --port 1025
    MAIL_HOST=127.0.0.1 SMTP_PORT=1025 python -m smtp_server.main
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import load_config  # noqa: E402
from smtp_server.server.tcp_server import run_server  # noqa: E402


def main() -> None:
    cfg = load_config("smtp")
    print(f"Démarrage du serveur SMTP sur {cfg.host}:{cfg.port} (data: {cfg.data_dir})")
    asyncio.run(run_server(cfg.host, cfg.port, cfg.data_dir))


if __name__ == "__main__":
    main()