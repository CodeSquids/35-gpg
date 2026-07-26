"""Serveur TCP asyncio : accepte les connexions et relie chaque socket à une
ImapSession via le parseur de commandes."""

from __future__ import annotations

import asyncio
import os
import ssl

from accounts import AccountStore
from storage import MaildirBackend

from .parser import ParseError, parse_line
from .session import ImapSession
from .session_state import SessionState

# Mode debug : affiche chaque ligne échangée avec le client (utile pour
# diagnostiquer ce qu'envoie réellement un client réel comme Thunderbird,
# qui ne montre jamais son dialogue protocolaire à l'utilisateur).
# Activation : IMAP_DEBUG=1 python -m imap_server.main
_DEBUG = os.environ.get("IMAP_DEBUG", "") not in ("", "0", "false", "False")


def _debug(direction: str, text: str) -> None:
    if _DEBUG:
        print(f"[IMAP {direction}] {text}")


async def _handle_client(reader, writer, account_store, backend) -> None:
    peer = writer.get_extra_info("peername")
    _debug("CONN", f"Nouvelle connexion depuis {peer}")

    session = ImapSession(account_store=account_store, backend=backend)
    greeting = "* OK IMAP4rev1 server ready"
    _debug("<<<", greeting)
    writer.write((greeting + "\r\n").encode("utf-8"))
    await writer.drain()

    try:
        while True:
            line = await reader.readline()
            if not line:
                _debug("CONN", f"{peer} a fermé la connexion")
                break  # client a fermé la connexion

            text = line.decode("utf-8", errors="replace").rstrip("\r\n")
            if not text.strip():
                continue
            _debug(">>>", text)

            try:
                parsed = parse_line(text)
            except ParseError as exc:
                error_line = f"* BAD {exc}"
                _debug("<<<", error_line)
                writer.write((error_line + "\r\n").encode("utf-8"))
                await writer.drain()
                continue

            responses = session.handle_command(parsed.tag, parsed.name, parsed.args)
            for response in responses:
                _debug("<<<", response)
                writer.write((response + "\r\n").encode("utf-8"))
            await writer.drain()

            if session.state == SessionState.LOGOUT:
                break
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def create_server(
    host: str,
    port: int,
    data_dir: str,
    ssl_context: ssl.SSLContext | None = None,
) -> asyncio.base_events.Server:
    """
    Crée et démarre le serveur (bind + listen) sans entrer dans la boucle
    serve_forever(). Utilisé par run_server() pour l'usage normal, et
    directement par les tests d'intégration / le script de démo, qui ont
    besoin de garder la main pour piloter des clients ensuite.
    """
    account_store = AccountStore(data_dir=data_dir)
    backend = MaildirBackend(data_dir=data_dir)

    async def handler(reader, writer):
        await _handle_client(reader, writer, account_store, backend)

    return await asyncio.start_server(handler, host, port, ssl=ssl_context)


async def run_server(
    host: str,
    port: int,
    data_dir: str,
    ssl_context: ssl.SSLContext | None = None,
) -> None:
    server = await create_server(host, port, data_dir, ssl_context)
    addr = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    protocol = "IMAPS (TLS)" if ssl_context else "IMAP"
    print(f"Serveur {protocol} en écoute sur {addr}")
    if _DEBUG:
        print("Mode debug active (IMAP_DEBUG=1) : chaque ligne echangee sera affichee.")

    async with server:
        await server.serve_forever()
