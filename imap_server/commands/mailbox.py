"""
IMAP Mailbox Commands
Handles SELECT, EXAMINE, LIST, CREATE, DELETE, RENAME, SUBSCRIBE, UNSUBSCRIBE, STATUS commands
"""

from typing import List, TYPE_CHECKING
from ..server.parser import IMAPCommand
from ..storage.maildir_backend import MaildirBackend
import logging
import os

if TYPE_CHECKING:
    from ..server.session import IMAPSession

logger = logging.getLogger(__name__)


class MailboxCommands:
    """Handles IMAP mailbox management commands"""
    
    def __init__(self, session: "IMAPSession", storage: MaildirBackend):
        self.session = session
        self.storage = storage
         
    async def handle_select(self, command: IMAPCommand):
        """Handle SELECT command"""
        if self.session.state != "AUTHENTICATED":
            await self.session.send_tagged_response(
                command.tag, "NO", "Please authenticate first"
            )
            return
            
        if len(command.arguments) < 1:
            await self.session.send_tagged_response(
                command.tag, "BAD", "SELECT command requires mailbox name"
            )
            return
            
        mailbox = command.arguments[0].strip('"')
        
        # Try to select the mailbox
        mailbox_info = self.storage.select_mailbox(mailbox, self.session.authenticated_user)
        if mailbox_info is None:
            await self.session.send_tagged_response(
                command.tag, "NO", f"Mailbox '{mailbox}' doesn't exist"
            )
            return
            
        self.session.selected_mailbox = mailbox
        self.session.state = "SELECTED"
        
        # Send FLAGS response
        flags = "\\Answered \\Flagged \\Draft \\Deleted \\Seen"
        await self.session.send_untagged(f'* FLAGS ({flags})')
        
        # Send EXISTS response
        await self.session.send_untagged(f'* {mailbox_info["exists"]} EXISTS')
        
        # Send RECENT response (always 0 in our implementation as we don't track recent)
        await self.session.send_untagged('* 0 RECENT')
        
        # Send UIDVALIDITY
        await self.session.send_untagged(f'* OK [UIDVALIDITY {mailbox_info["uidvalidity"]}] UIDs valid')
        
        # Send permission flags
        perm_flags = "r"  # read-only by default in our simple implementation
        if mailbox == "INBOX":
            perm_flags += "wsil"  # write, insert, create subfolder, expunge
        await self.session.send_untagged(f'* OK [PERMANENTFLAGS ({perm_flags}*)] Limited')
        
        await self.session.send_tagged_response(
            command.tag, "OK", f"[READ-WRITE] SELECT completed"
        )
        
        logger.info(f"User {self.session.authenticated_user} selected mailbox '{mailbox}'")
        
    async def handle_examine(self, command: IMAPCommand):
        """Handle EXAMINE command (read-only SELECT)"""
        if self.session.state != "AUTHENTICATED":
            await self.session.send_tagged_response(
                command.tag, "NO", "Please authenticate first"
            )
            return
            
        if len(command.arguments) < 1:
            await self.session.send_tagged_response(
                command.tag, "BAD", "EXAMINE command requires mailbox name"
            )
            return
            
        mailbox = command.arguments[0].strip('"')
        
        # Try to select the mailbox (EXAMINE is like SELECT but read-only)
        mailbox_info = self.storage.select_mailbox(mailbox, self.session.authenticated_user)
        if mailbox_info is None:
            await self.session.send_tagged_response(
                command.tag, "NO", f"Mailbox '{mailbox}' doesn't exist"
            )
            return
            
        self.session.selected_mailbox = mailbox
        self.session.state = "SELECTED"
        
        # Send FLAGS response
        flags = "\\Answered \\Flagged \\Draft \\Deleted \\Seen"
        await self.session.send_untagged(f'* FLAGS ({flags})')
        
        # Send EXISTS response
        await self.session.send_untagged(f'* {mailbox_info["exists"]} EXISTS')
        
        # Send RECENT response
        await self.session.send_untagged('* 0 RECENT')
        
        # Send UIDVALIDITY
        await self.session.send_untagged(f'* OK [UIDVALIDITY {mailbox_info["uidvalidity"]}] UIDs valid')
        
        # Send permission flags (read-only for EXAMINE)
        await self.session.send_untagged('* OK [PERMANENTFLAGS ()] Read-only mailbox')
        
        await self.session.send_tagged_response(
            command.tag, "OK", f"[READ-ONLY] EXAMINE completed"
        )
        
        logger.info(f"User {self.session.authenticated_user} examined mailbox '{mailbox}'")
        
    async def handle_list(self, command: IMAPCommand):
        """Handle LIST command"""
        if self.session.state != "AUTHENTICATED":
            await self.session.send_tagged_response(
                command.tag, "NO", "Please authenticate first"
            )
            return
            
        # Parse arguments: LIST reference mailbox
        # Simplified - we'll just support LIST "" "*" for now
        if len(command.arguments) < 2:
            await self.session.send_tagged_response(
                command.tag, "BAD", "LIST command requires reference and mailbox pattern"
            )
            return
            
        reference = command.arguments[0].strip('"')
        mailbox_pattern = command.arguments[1].strip('"')
        
        # For simplicity, we only handle reference "" and pattern "*" or "%"
        if reference != '':
            await self.session.send_tagged_response(
                command.tag, "NO", f"Reference '{reference}' not supported"
            )
            return
            
        # List mailboxes for the current user
        mailboxes = self.storage.list_mailboxes(self.session.authenticated_user)
        
        for mailbox in mailboxes:
            # Determine flags
            flags = r'\HasNoChildren'  # Simplified - we don't implement hierarchy
            if mailbox == "INBOX":
                flags = r'\HasNoChildren'  # INBOX also has no children in our flat structure
                
            await self.session.send_untagged(
                f'* LIST ({flags}) "/" "{mailbox}"'
            )
            
        await self.session.send_tagged_response(
            command.tag, "OK", "LIST completed"
        )
        
    async def handle_create(self, command: IMAPCommand):
        """Handle CREATE command"""
        if self.session.state != "AUTHENTICATED":
            await self.session.send_tagged_response(
                command.tag, "NO", "Please authenticate first"
            )
            return
            
        if len(command.arguments) < 1:
            await self.session.send_tagged_response(
                command.tag, "BAD", "CREATE command requires mailbox name"
            )
            return
            
        mailbox = command.arguments[0].strip('"')
        
        if self.storage.create_mailbox(mailbox, self.session.authenticated_user):
            await self.session.send_tagged_response(
                command.tag, "OK", f"CREATE completed for mailbox '{mailbox}'"
            )
            logger.info(f"User {self.session.authenticated_user} created mailbox '{mailbox}'")
        else:
            await self.session.send_tagged_response(
                command.tag, "NO", f"CREATE failed for mailbox '{mailbox}'"
            )
            
    async def handle_delete(self, command: IMAPCommand):
        """Handle DELETE command"""
        if self.session.state != "AUTHENTICATED":
            await self.session.send_tagged_response(
                command.tag, "NO", "Please authenticate first"
            )
            return
            
        if len(command.arguments) < 1:
            await self.session.send_tagged_response(
                command.tag, "BAD", "DELETE command requires mailbox name"
            )
            return
            
        mailbox = command.arguments[0].strip('"')
        
        # Prevent deleting INBOX
        if mailbox == "INBOX":
            await self.session.send_tagged_response(
                command.tag, "NO", "Cannot delete INBOX"
            )
            return
            
        if self.storage.delete_mailbox(mailbox, self.session.authenticated_user):
            await self.session.send_tagged_response(
                command.tag, "OK", f"DELETE completed for mailbox '{mailbox}'"
            )
            logger.info(f"User {self.session.authenticated_user} deleted mailbox '{mailbox}'")
        else:
            await self.session.send_tagged_response(
                command.tag, "NO", f"DELETE failed for mailbox '{mailbox}'"
            )
            
    async def handle_rename(self, command: IMAPCommand):
        """Handle RENAME command"""
        if self.session.state != "AUTHENTICATED":
            await self.session.send_tagged_response(
                command.tag, "NO", "Please authenticate first"
            )
            return
            
        if len(command.arguments) < 2:
            await self.session.send_tagged_response(
                command.tag, "BAD", "RENAME command requires source and destination mailbox names"
            )
            return
            
        source = command.arguments[0].strip('"')
        destination = command.arguments[1].strip('"')
        
        if self.storage.rename_mailbox(source, destination, self.session.authenticated_user):
            await self.session.send_tagged_response(
                command.tag, "OK", f"RENAME completed"
            )
            logger.info(f"User {self.session.authenticated_user} renamed mailbox '{source}' to '{destination}'")
        else:
            await self.session.send_tagged_response(
                command.tag, "NO", f"RENAME failed from '{source}' to '{destination}'"
            )
            
    async def handle_subscribe(self, command: IMAPCommand):
        """Handle SUBSCRIBE command"""
        if self.session.state != "AUTHENTICATED":
            await self.session.send_tagged_response(
                command.tag, "NO", "Please authenticate first"
            )
            return
            
        if len(command.arguments) < 1:
            await self.session.send_tagged_response(
                command.tag, "BAD", "SUBSCRIBE command requires mailbox name"
            )
            return
            
        mailbox = command.arguments[0].strip('"')
        
        # For simplicity, we don't implement actual subscription tracking
        # All mailboxes are considered subscribed by default
        await self.session.send_tagged_response(
            command.tag, "OK", f"SUBSCRIBE completed for mailbox '{mailbox}'"
        )
        logger.info(f"User {self.session.authenticated_user} subscribed to mailbox '{mailbox}'")
        
    async def handle_unsubscribe(self, command: IMAPCommand):
        """Handle UNSUBSCRIBE command"""
        if self.session.state != "AUTHENTICATED":
            await self.session.send_tagged_response(
                command.tag, "NO", "Please authenticate first"
            )
            return
            
        if len(command.arguments) < 1:
            await self.session.send_tagged_response(
                command.tag, "BAD", "UNSUBSCRIBE command requires mailbox name"
            )
            return
            
        mailbox = command.arguments[0].strip('"')
        
        # For simplicity, we don't implement actual subscription tracking
        await self.session.send_tagged_response(
            command.tag, "OK", f"UNSUBSCRIBE completed for mailbox '{mailbox}'"
        )
        logger.info(f"User {self.session.authenticated_user} unsubscribed from mailbox '{mailbox}'")
        
    async def handle_status(self, command: IMAPCommand):
        """Handle STATUS command"""
        if self.session.state != "AUTHENTICATED":
            await self.session.send_tagged_response(
                command.tag, "NO", "Please authenticate first"
            )
            return
            
        if len(command.arguments) < 2:
            await self.session.send_tagged_response(
                command.tag, "BAD", "STATUS command requires mailbox name and status items"
            )
            return
            
        mailbox = command.arguments[0].strip('"')
        # The second argument is a parenthesized list of status items
        # For simplicity, we'll just return basic info
        
        mailbox_info = self.storage.get_mailbox_status(mailbox, self.session.authenticated_user)
        if mailbox_info is None:
            await self.session.send_tagged_response(
                command.tag, "NO", f"Mailbox '{mailbox}' doesn't exist"
            )
            return
            
        # Build STATUS response
        status_items = []
        if "MESSAGES" in command.raw_arguments.upper():
            status_items.append(f"MESSAGES {mailbox_info['messages']}")
        if "RECENT" in command.raw_arguments.upper():
            status_items.append(f"RECENT {mailbox_info['recent']}")
        if "UIDNEXT" in command.raw_arguments.upper():
            status_items.append(f"UIDNEXT {mailbox_info['uidnext']}")
        if "UIDVALIDITY" in command.raw_arguments.upper():
            # Fixed the key name - it's 'uidvalidity' not 'uidvalidity'
            status_items.append(f"UIDVALIDITY {mailbox_info['uidvalidity']}")
        if "UNSEEN" in command.raw_arguments.upper():
            status_items.append(f"UNSEEN {mailbox_info['unseen']}")
            
        status_line = f'STATUS "{mailbox}" ({", ".join(status_items)})'
        await self.session.send_untagged(status_line)
        await self.session.send_tagged_response(
            command.tag, "OK", "STATUS completed"
        )