"""
Serveur TCP asyncio pour le sous-ensemble SMTP.

Particularité par rapport au serveur IMAP : la commande DATA fait basculer
la connexion dans un mode où chaque ligne reçue n'est PAS une commande mais
du contenu de message, jusqu'à une ligne contenant uniquement ".". C'est
donc le serveur TCP lui-même (pas la session) qui gère ce changement de
mode ligne par ligne.
"""

from __future__ import annotations

import asyncio

from accounts import AccountStore
from storage import MaildirBackend

from .session import SmtpSession
from .session_state import SmtpState


async def _handle_client(reader, writer, account_store, backend) -> None:
    session = SmtpSession(account_store=account_store, backend=backend)
    writer.write(b"220 Local mail server ready\r\n")
    await writer.drain()

    data_buffer: list[bytes] = []

    try:
        while True:
            line = await reader.readline()
            if not line:
                break  # client a fermé la connexion

            if session.in_data_mode:
                stripped = line.rstrip(b"\r\n")
                if stripped == b".":
                    raw_message = b"\r\n".join(data_buffer)
                    data_buffer = []
                    responses = session.finish_data(raw_message)
                    for response in responses:
                        writer.write((response + "\r\n").encode("utf-8"))
                    await writer.drain()
                    continue

                # Transparence dot-stuffing (RFC 5321 §4.5.2) : une ligne de
                # données qui commence réellement par un "." est envoyée
                # avec un point supplémentaire ("..texte"), qu'on retire ici.
                if stripped.startswith(b".."):
                    stripped = stripped[1:]
                data_buffer.append(stripped)
                continue

            text = line.decode("utf-8", errors="replace").rstrip("\r\n")
            if not text.strip():
                continue

            parts = text.split(" ", 1)
            verb = parts[0]
            arg = parts[1] if len(parts) > 1 else ""

            responses = session.handle_command(verb, arg)
            for response in responses:
                writer.write((response + "\r\n").encode("utf-8"))
            await writer.drain()

            if session.state == SmtpState.QUIT:
                break
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def run_server(host: str, port: int, data_dir: str) -> None:
    account_store = AccountStore(data_dir=data_dir)
    backend = MaildirBackend(data_dir=data_dir)

    async def handler(reader, writer):
        await _handle_client(reader, writer, account_store, backend)

    server = await asyncio.start_server(handler, host, port)
    addr = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    print(f"Serveur SMTP en écoute sur {addr}")

    async with server:
        await server.serve_forever()