"""Serveur TCP asyncio : accepte les connexions et relie chaque socket à une
ImapSession via le parseur de commandes."""

from __future__ import annotations

import asyncio

from accounts import AccountStore
from storage import MaildirBackend

from .parser import ParseError, parse_line
from .session import ImapSession
from .session_state import SessionState


async def _handle_client(reader, writer, account_store, backend) -> None:
    session = ImapSession(account_store=account_store, backend=backend)
    writer.write(b"* OK IMAP4rev1 server ready\r\n")
    await writer.drain()

    try:
        while True:
            line = await reader.readline()
            if not line:
                break  # client a fermé la connexion

            text = line.decode("utf-8", errors="replace").rstrip("\r\n")
            if not text.strip():
                continue

            try:
                parsed = parse_line(text)
            except ParseError as exc:
                writer.write(f"* BAD {exc}\r\n".encode("utf-8"))
                await writer.drain()
                continue

            responses = session.handle_command(parsed.tag, parsed.name, parsed.args)
            for response in responses:
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


async def run_server(host: str, port: int, data_dir: str) -> None:
    account_store = AccountStore(data_dir=data_dir)
    backend = MaildirBackend(data_dir=data_dir)

    async def handler(reader, writer):
        await _handle_client(reader, writer, account_store, backend)

    server = await asyncio.start_server(handler, host, port)
    addr = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    print(f"Serveur IMAP en écoute sur {addr}")

    async with server:
        await server.serve_forever()