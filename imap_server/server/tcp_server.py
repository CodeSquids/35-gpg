"""
TCP Server for IMAP4rev1 Server
Handles connection acceptance and basic I/O using asyncio streams
"""

import asyncio
import logging
from typing import Optional
from imap_server.storage.maildir_backend import MaildirBackend
from imap_server.server.session import IMAPSession

logger = logging.getLogger(__name__)


class TCPServer:
    """TCP server handling IMAP connections using asyncio streams."""
    
    def __init__(self, host: str = 'localhost', port: int = 1143, storage: Optional[MaildirBackend] = None):
        self.host = host
        self.port = port
        self.server: Optional[asyncio.Server] = None
        self.storage = storage or MaildirBackend()
        
    async def start(self):
        """Start the TCP server."""
        self.server = await asyncio.start_server(
            self.client_connected,
            self.host,
            self.port
        )
        
        addr = self.server.sockets[0].getsockname()
        logging.info(f'Serving on {addr}')
        
    async def wait_closed(self):
        """Wait for the server to close."""
        if self.server:
            await self.server.wait_closed()
            
    async def stop(self):
        """Stop the TCP server."""
        if self.server:
            self.server.close()
            await self.wait_closed()
            
    async def client_connected(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle a new client connection."""
        client_addr = writer.get_extra_info('peername')
        logging.info(f'New connection from {client_addr}')
        
        # Create a new session for this client
        session = IMAPSession(reader, writer, self.storage)
        
        try:
            await session.handle_client()
        except Exception as e:
            logging.error(f"Error handling client {client_addr}: {e}")
        finally:
            logging.info(f'Connection from {client_addr} closed')