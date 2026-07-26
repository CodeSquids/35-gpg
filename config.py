"""
Configuration centralisée pour le système de messagerie.

Permet de basculer entre un test 100% local (localhost) et un test
multi-VM (0.0.0.0 + port exposé sur un réseau privé) sans toucher au code
des serveurs : il suffit de changer une variable d'environnement, ou de
passer un argument en ligne de commande.

Priorité de résolution : argument CLI > variable d'environnement > défaut.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

# Valeurs par défaut. 0.0.0.0 = écoute sur toutes les interfaces réseau,
# ce qui est nécessaire pour qu'une VM cliente puisse joindre le serveur.
# Pour un test strictement local, on peut surcharger avec MAIL_HOST=127.0.0.1.
DEFAULT_HOST = "0.0.0.0"
DEFAULT_IMAP_PORT = 1143
DEFAULT_SMTP_PORT = 1025
DEFAULT_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


@dataclass(frozen=True)
class ServerConfig:
    host: str
    port: int
    data_dir: str


def _build_parser(default_port: int) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--host", type=str, default=None, help="Interface d'écoute (ex: 0.0.0.0, 127.0.0.1, ou l'IP de la VM)")
    parser.add_argument("--port", type=int, default=None, help="Port TCP d'écoute")
    parser.add_argument("--data-dir", type=str, default=None, help="Répertoire de stockage des comptes et Maildirs")
    return parser


def load_config(server: str, argv: list[str] | None = None) -> ServerConfig:
    """
    Résout la configuration réseau pour un serveur donné.

    server: "imap" ou "smtp" (détermine le port par défaut)
    argv: liste d'arguments CLI à parser (None => sys.argv est utilisé par argparse)
    """
    default_port = DEFAULT_IMAP_PORT if server == "imap" else DEFAULT_SMTP_PORT
    env_prefix = "MAIL"  # variables partagées: MAIL_HOST, MAIL_DATA_DIR
    server_env_prefix = "IMAP" if server == "imap" else "SMTP"  # IMAP_PORT / SMTP_PORT

    parser = _build_parser(default_port)
    args, _unknown = parser.parse_known_args(argv)

    host = (
        args.host
        or os.environ.get(f"{env_prefix}_HOST")
        or DEFAULT_HOST
    )
    port = (
        args.port
        or _env_int(f"{server_env_prefix}_PORT")
        or default_port
    )
    data_dir = (
        args.data_dir
        or os.environ.get(f"{env_prefix}_DATA_DIR")
        or DEFAULT_DATA_DIR
    )

    return ServerConfig(host=host, port=port, data_dir=data_dir)


def _env_int(name: str) -> int | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None