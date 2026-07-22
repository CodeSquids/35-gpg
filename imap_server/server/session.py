"""
IMAP Session Handling
Manages the state machine for IMAP4rev1 protocol interactions
"""

import asyncio
import logging
from enum import Enum
from typing import Optional
from imap_server.server.parser import IMAPParser, CommandType
from imap_server.commands.auth import AuthCommands
from imap_server.commands.mailbox import MailboxCommands
from imap_server.commands.messages import MessageCommands
from imap_server.storage.maildir_backend import MaildirBackend

logger = logging.getLogger(__name__)


class IMAPState(Enum):
    """IMAP4rev1 connection states"""
    NOT_AUTHENTICATED = "NOT AUTHENTICATED"
    AUTHENTICATED = "AUTHENTICATED"
    SELECTED = "SELECTED"
    LOGOUT = "LOGOUT"


class IMAPSession:
    """Handles an individual IMAP client connection."""
    
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, storage: MaildirBackend):
        self.reader = reader
        self.writer = writer
        self.state = IMAPState.NOT_AUTHENTICATED
        self.authenticated_user: Optional[str] = None
        self.selected_mailbox: Optional[str] = None
        self.storage = storage
        
        # Create command processors
        self.parser = IMAPParser()
        self.auth_handler = AuthCommands(self, storage)
        self.mailbox_handler = MailboxCommands(self, storage)
        self.message_handler = MessageCommands(self, storage)
        
        self.logger = logging.getLogger(f"{__name__}.{id(self)}")
        
    async def handle_client(self):
        """Main client handling loop."""
        # Send greeting upon connection
        await self.send_response("* OK IMAP4rev1 server ready")
        
        try:
            while self.state != IMAPState.LOGOUT:
                # Read a line from the client
                line = await self.reader.readline()
                if not line:  # Connection closed
                    break
                    
                line = line.decode('utf-8').strip()
                self.logger.debug(f"Received: {line}")
                
                if not line:
                    continue
                    
                # Process the command
                try:
                    command = self.parser.parse(line)
                    await self.process_command(command)
                except Exception as e:
                    self.logger.error(f"Error processing command '{line}': {e}")
                    await self.send_response(f"BAD Error processing command: {e}")
                    
        except Exception as e:
            self.logger.error(f"Connection error: {e}")
        finally:
            await self.close()
            
    async def process_command(self, command):
        """Dispatch command to appropriate handler based on state and command type."""
        # Log the command for debugging
        self.logger.debug(f"Processing command: {command.command_type.value} in state {self.state.value}")
        
        # Handle authentication state
        if self.state == IMAPState.NOT_AUTHENTICATED:
            if command.command_type == CommandType.CAPABILITY:
                await self.auth_handler.handle_capability(command)
            elif command.command_type == CommandType.LOGIN:
                await self.auth_handler.handle_login(command)
            elif command.command_type == CommandType.LOGOUT:
                await self.auth_handler.handle_logout(command)
            else:
                await self.send_tagged_response(command.tag, "NO", "Please authenticate first")
                
        # Handle authenticated state (but not selected)
        elif self.state == IMAPState.AUTHENTICATED:
            if command.command_type == CommandType.CAPABILITY:
                await self.auth_handler.handle_capability(command)
            elif command.command_type == CommandType.LOGIN:
                await self.auth_handler.handle_login(command)
            elif command.command_type == CommandType.LOGOUT:
                await self.auth_handler.handle_logout(command)
            elif command.command_type in [CommandType.SELECT, CommandType.EXAMINE]:
                if command.command_type == CommandType.SELECT:
                    await self.mailbox_handler.handle_select(command)
                else:
                    await self.mailbox_handler.handle_examine(command)
            elif command.command_type == CommandType.LIST:
                await self.mailbox_handler.handle_list(command)
            elif command.command_type == CommandType.CREATE:
                await self.mailbox_handler.handle_create(command)
            elif command.command_type == CommandType.DELETE:
                await self.mailbox_handler.handle_delete(command)
            elif command.command_type == CommandType.RENAME:
                await self.mailbox_handler.handle_rename(command)
            elif command.command_type == CommandType.SUBSCRIBE:
                await self.mailbox_handler.handle_subscribe(command)
            elif command.command_type == CommandType.UNSUBSCRIBE:
                await self.mailbox_handler.handle_unsubscribe(command)
            elif command.command_type == CommandType.STATUS:
                await self.mailbox_handler.handle_status(command)
            else:
                await self.send_tagged_response(command.tag, "NO", "Please select a mailbox first")
                
        # Handle selected state
        elif self.state == IMAPState.SELECTED:
            if command.command_type == CommandType.CAPABILITY:
                await self.auth_handler.handle_capability(command)
            elif command.command_type == CommandType.LOGOUT:
                await self.auth_handler.handle_logout(command)
            elif command.command_type == CommandType.SELECT:
                await self.mailbox_handler.handle_select(command)
            elif command.command_type == CommandType.EXAMINE:
                await self.mailbox_handler.handle_examine(command)
            elif command.command_type == CommandType.LIST:
                await self.mailbox_handler.handle_list(command)
            elif command.command_type == CommandType.CREATE:
                await self.mailbox_handler.handle_create(command)
            elif command.command_type == CommandType.DELETE:
                await self.mailbox_handler.handle_delete(command)
            elif command.command_type == CommandType.RENAME:
                await self.mailbox_handler.handle_rename(command)
            elif command.command_type == CommandType.SUBSCRIBE:
                await self.mailbox_handler.handle_subscribe(command)
            elif command.command_type == CommandType.UNSUBSCRIBE:
                await self.mailbox_handler.handle_unsubscribe(command)
            elif command.command_type == CommandType.STATUS:
                await self.mailbox_handler.handle_status(command)
            elif command.command_type == CommandType.FETCH:
                await self.message_handler.handle_fetch(command)
            elif command.command_type == CommandType.STORE:
                await self.message_handler.handle_store(command)
            elif command.command_type == CommandType.SEARCH:
                await self.message_handler.handle_search(command)
            elif command.command_type == CommandType.EXPUNGE:
                await self.message_handler.handle_expunge(command)
            elif command.command_type == CommandType.COPY:
                await self.message_handler.handle_copy(command)
            elif command.command_type == CommandType.UID:
                await self.message_handler.handle_uid(command)
            elif command.command_type == CommandType.NOOP:
                await self.send_tagged_response(command.tag, "OK", "NOOP completed")
            else:
                await self.send_tagged_response(command.tag, "NO", "Command not allowed in selected state")
                
        # Handle logout state (shouldn't reach here due to while condition, but just in case)
        elif self.state == IMAPState.LOGOUT:
            await self.send_tagged_response(command.tag, "BAD", "Connection is closing")
            
    async def send_response(self, message: str):
        """Send a response to the client."""
        data = f"{message}\r\n".encode('utf-8')
        print(f"SENDING: {data}")  # Debug
        self.writer.write(data)
        await self.writer.drain()
        self.logger.debug(f"Sent: {message}")
        
    async def send_untagged(self, message: str):
        """Send an untagged response."""
        await self.send_response(f"* {message}")
        
    async def send_tagged_response(self, tag: str, status: str, message: str):
        """Send a tagged response."""
        await self.send_response(f"{tag} {status} {message}")
        
    async def close(self):
        """Close the connection."""
        if not self.writer.is_closing():
            self.writer.close()
            await self.writer.wait_closed()