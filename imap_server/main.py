#!/usr/bin/env python3
"""
IMAP4rev1 Server
Academic project implementing a functional subset of RFC 3501 (IMAP4rev1)
"""

import asyncio
import logging
import sys
from imap_server.server.tcp_server import TCPServer
from imap_server.storage.maildir_backend import MaildirBackend

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


async def main():
    """Main entry point for the IMAP server."""
    # Create storage backend
    storage = MaildirBackend()
    
    # Create and start the TCP server
    server = TCPServer(host='localhost', port=1143, storage=storage)
    
    try:
        await server.start()
        logger.info("IMAP server started on localhost:1143")
        logger.info("Press Ctrl+C to stop the server")
        
        # Keep the server running until interrupted
        await server.wait_closed()
        
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        await server.stop()
        logger.info("Server stopped")


if __name__ == "__main__":
    asyncio.run(main())