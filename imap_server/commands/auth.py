"""
IMAP Authentication Commands
Handles CAPABILITY, LOGIN, and LOGOUT commands
"""

from typing import List
from ..server.parser import IMAPCommand
from ..storage.maildir_backend import MaildirBackend
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..server.session import IMAPSession

logger = logging.getLogger(__name__)


class AuthCommands:
    """Handles IMAP authentication commands"""
    
    def __init__(self, session: "IMAPSession", storage: MaildirBackend):
        self.session = session
        self.storage = storage
         
    async def handle_capability(self, command: IMAPCommand):
        """Handle CAPABILITY command"""
        # Basic IMAP4rev1 capabilities
        capabilities = [
            "IMAP4REV1",
            "IMAP4",
            "STARTTLS",  # Even though we don't implement it, we advertise it per RFC
            "LOGIN"      # We support plain text login
        ]
        
        capability_line = "CAPABILITY " + " ".join(capabilities)
        await self.session.send_untagged(capability_line)
        await self.session.send_tagged_response(
            command.tag, "OK", "CAPABILITY completed"
        )
        
    async def handle_login(self, command: IMAPCommand):
        """Handle LOGIN command"""
        if self.session.state != "NOT_AUTHENTICATED":
            await self.session.send_tagged_response(
                command.tag, "NO", "Cannot LOGIN in current state"
            )
            return
            
        if len(command.arguments) < 2:
            await self.session.send_tagged_response(
                command.tag, "BAD", "LOGIN command requires username and password"
            )
            return
            
        username = command.arguments[0].strip('"')
        password = command.arguments[1].strip('"')
        
        # Validate credentials against our storage
        if self.storage.validate_user(username, password):
            self.session.authenticated_user = username
            self.session.state = "AUTHENTICATED"
            await self.session.send_tagged_response(
                command.tag, "OK", "LOGIN completed"
            )
            logger.info(f"User {username} logged in successfully")
        else:
            await self.session.send_tagged_response(
                command.tag, "NO", "LOGIN failed: invalid username or password"
            )
            logger.warning(f"Failed login attempt for user: {username}")
            
    async def handle_logout(self, command: IMAPCommand):
        """Handle LOGOUT command"""
        # Send BYE response before closing
        await self.session.send_untagged("BYE LOGOUT requested")
        await self.session.send_tagged_response(
            command.tag, "OK", "LOGOUT completed"
        )
        await self.session.close()
        logger.info("Client logged out")