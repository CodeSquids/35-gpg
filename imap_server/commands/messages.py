"""
IMAP Message Commands
Handles FETCH, STORE, SEARCH, EXPUNGE, COPY, UID commands
"""

from typing import List
from ..server.parser import IMAPCommand
from ..storage.maildir_backend import MaildirBackend
import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..server.session import IMAPSession
    from ..storage.models import Message

logger = logging.getLogger(__name__)


class MessageCommands:
    """Handles IMAP message manipulation commands"""
    
    def __init__(self, session: "IMAPSession", storage: MaildirBackend):
        self.session = session
        self.storage = storage
        
    async def handle_fetch(self, command: IMAPCommand):
        """Handle FETCH command"""
        if self.session.state != "SELECTED":
            await self.session.send_tagged_response(
                command.tag, "NO", "Please select a mailbox first"
            )
            return
            
        if len(command.arguments) < 2:
            await self.session.send_tagged_response(
                command.tag, "BAD", "FETCH command requires sequence set and data items"
            )
            return
            
        sequence_set = command.arguments[0]
        data_items = command.arguments[1:]
        
        # Parse sequence set (simplified - just handles simple numbers and *)
        msg_nums = self._parse_sequence_set(sequence_set)
        
        if not msg_nums:
            await self.session.send_tagged_response(
                command.tag, "OK", "FETCH completed (no messages)"
            )
            return
            
        # Fetch each message
        for msg_num in msg_nums:
            await self._fetch_message_data(msg_num, data_items)
            
        await self.session.send_tagged_response(
            command.tag, "OK", "FETCH completed"
        )
        
    async def _fetch_message_data(self, msg_num: int, data_items: List[str]):
        """Fetch specific data items for a message"""
        # Get the message from storage
        message = self.storage.get_message(
            self.session.selected_mailbox, 
            self.session.authenticated_user, 
            msg_num
        )
        
        if message is None:
            # Message doesn't exist (might have been expunged)
            await self.session.send_untagged(f'* {msg_num} FETCH (NIL)')
            return
            
        # Build FETCH response
        fetch_data = []
        
        for item in data_items:
            item_upper = item.upper().strip('()')
            
            if item_upper == "FLAGS":
                flags = self._format_flags(message.flags)
                fetch_data.append(f'FLAGS ({flags})')
                
            elif item_upper == "UID":
                fetch_data.append(f'UID {message.uid}')
                
            elif item_upper == "BODY[]" or item_upper == "BODY":
                # Return the entire message
                body_data = self.storage.get_message_bytes(
                    self.session.selected_mailbox,
                    self.session.authenticated_user,
                    msg_num
                )
                if body_data is not None:
                    # Literal format: {size}\r\n{data}
                    fetch_data.append(f'BODY[] {{{len(body_data)}}}\r\n{body_data.decode("utf-8", errors="replace")}')
                else:
                    fetch_data.append('BODY[] NIL')
                    
            elif item_upper == "BODY[HEADER]":
                # Return just the headers
                header_data = self.storage.get_message_headers(
                    self.session.selected_mailbox,
                    self.session.authenticated_user,
                    msg_num
                )
                if header_data is not None:
                    fetch_data.append(f'BODY[HEADER] {{{len(header_data)}}}\r\n{header_data.decode("utf-8", errors="replace")}')
                else:
                    fetch_data.append('BODY[HEADER] NIL')
                    
            elif item_upper.startswith("BODY["):
                # Handle partial body fetching - simplified
                fetch_data.append(f'{item} NIL')  # Not implemented
                
            else:
                # Unknown data item
                fetch_data.append(f'{item} NIL')
                
        if fetch_data:
            await self.session.send_untagged(f'* {msg_num} FETCH ({", ".join(fetch_data)})')
            
    def _format_flags(self, flags: set) -> str:
        """Format flags for IMAP response"""
        if not flags:
            return ""
        # Convert internal flag names to IMAP format
        imap_flags = []
        flag_map = {
            "answered": "\\Answered",
            "flagged": "\\Flagged", 
            "draft": "\\Draft",
            "deleted": "\\Deleted",
            "seen": "\\Seen"
        }
        for flag in flags:
            imap_flags.append(flag_map.get(flag, f"\\{flag}"))
        return " ".join(sorted(imap_flags))
        
    def _parse_sequence_set(self, sequence_set: str) -> list:
        """Parse IMAP sequence set (simplified implementation)"""
        nums = []
        parts = sequence_set.split(',')
        
        for part in parts:
            part = part.strip()
            if part == '*':
                # Get all messages in mailbox
                mailbox_info = self.storage.get_mailbox_status(
                    self.session.selected_mailbox,
                    self.session.authenticated_user
                )
                if mailbox_info:
                    nums.extend(range(1, mailbox_info['messages'] + 1))
            elif ':' in part:
                # Range
                try:
                    start, end = part.split(':')
                    start = int(start) if start != '*' else float('inf')
                    end = int(end) if end != '*' else float('inf')
                    # Simplified - just handle numeric ranges
                    if start != float('inf') and end != float('inf'):
                        nums.extend(range(int(start), int(end) + 1))
                except ValueError:
                    pass  # Invalid range, ignore
            else:
                # Single number
                try:
                    nums.append(int(part))
                except ValueError:
                    pass  # Invalid number, ignore
                    
        return sorted(list(set(nums)))  # Remove duplicates and sort
        
    async def handle_store(self, command: IMAPCommand):
        """Handle STORE command"""
        if self.session.state != "SELECTED":
            await self.session.send_tagged_response(
                command.tag, "NO", "Please select a mailbox first"
            )
            return
            
        if len(command.arguments) < 3:
            await self.session.send_tagged_response(
                command.tag, "BAD", "STORE command requires sequence set, data item, and value"
            )
            return
            
        sequence_set = command.arguments[0]
        data_item = command.arguments[1].upper()
        flag_value = " ".join(command.arguments[2:]).strip()
        
        # Parse sequence set
        msg_nums = self._parse_sequence_set(sequence_set)
        if not msg_nums:
            await self.session.send_tagged_response(
                command.tag, "OK", "STORE completed (no messages)"
            )
            return
            
        # Process the flag operation
        if data_item == "FLAGS":
            # Replace flags entirely
            flags = self._parse_flag_list(flag_value)
            for msg_num in msg_nums:
                self.storage.set_message_flags(
                    self.session.selected_mailbox,
                    self.session.authenticated_user,
                    msg_num,
                    flags
                )
        elif data_item == "+FLAGS":
            # Add flags
            flags = self._parse_flag_list(flag_value)
            for msg_num in msg_nums:
                self.storage.add_message_flags(
                    self.session.selected_mailbox,
                    self.session.authenticated_user,
                    msg_num,
                    flags
                )
        elif data_item == "-FLAGS":
            # Remove flags
            flags = self._parse_flag_list(flag_value)
            for msg_num in msg_nums:
                self.storage.remove_message_flags(
                    self.session.selected_mailbox,
                    self.session.authenticated_user,
                    msg_num,
                    flags
                )
        else:
            await self.session.send_tagged_response(
                command.tag, "BAD", f"Unsupported STORE data item: {data_item}"
            )
            return
            
        # Send FETCH responses for affected messages
        for msg_num in msg_nums:
            await self._fetch_message_data(msg_num, ["FLAGS"])
            
        await self.session.send_tagged_response(
            command.tag, "OK", "STORE completed"
        )
        
    def _parse_flag_list(self, flag_value: str) -> set:
        """Parse flag list from STORE command"""
        flags = set()
        # Remove parentheses if present
        if flag_value.startswith('(') and flag_value.endswith(')'):
            flag_value = factor[1:-1]
            
        # Split by spaces and process each flag
        for flag in flag_value.split():
            flag = flag.strip()
            if flag.startswith('\\'):
                # Internal flag format
                flag_name = flag[1:].lower()
                flag_map = {
                    "answered": "answered",
                    "flagged": "flagged",
                    "draft": "draft",
                    "deleted": "deleted",
                    "seen": "seen"
                }
                if flag_name in flag_map:
                    flags.add(flag_map[flag_name])
            else:
                # Keyword flag (not implemented in our simple version)
                flags.add(flag.lower())
                
        return flags
        
    async def handle_search(self, command: IMAPCommand):
        """Handle SEARCH command"""
        if self.session.state != "SELECTED":
            await self.session.send_tagged_response(
                command.tag, "NO", "Please select a mailbox first"
            )
            return
            
        if len(command.arguments) < 1:
            await self.session.send_tagged_response(
                command.tag, "BAD", "SEARCH command requires search criteria"
            )
            return
            
        # Parse search criteria (simplified implementation)
        criteria = " ".join(command.arguments).upper()
        msg_nums = []
        
        if criteria == "ALL":
            # Get all messages
            mailbox_info = self.storage.get_mailbox_status(
                self.session.selected_mailbox,
                self.session.authenticated_user
            )
            if mailbox_info:
                msg_nums = list(range(1, mailbox_info['messages'] + 1))
                
        elif criteria == "UNSEEN":
            # Get unseen messages
            msg_nums = self.storage.search_messages(
                self.session.selected_mailbox,
                self.session.authenticated_user,
                unseen=True
            )
            
        elif criteria.startswith("FROM "):
            # Get messages from specific sender
            sender = criteria[5:].strip('"')
            msg_nums = self.storage.search_messages(
                self.session.selected_mailbox,
                self.session.authenticated_user,
                from_field=sender
            )
            
        else:
            # Unsupported search criteria
            await self.session.send_tagged_response(
                command.tag, "NO", f"Unsupported search criteria: {criteria}"
            )
            return
            
        # Send SEARCH response
        if msg_nums:
            search_result = " ".join(str(num) for num in msg_nums)
            await self.session.send_untagged(f'* SEARCH {search_result}')
        else:
            await self.session.send_untagged('* SEARCH')
            
        await self.session.send_tagged_response(
            command.tag, "OK", "SEARCH completed"
        )
        
    async def handle_expunge(self, command: IMAPCommand):
        """Handle EXPUNGE command"""
        if self.session.state != "SELECTED":
            await self.session.send_tagged_response(
                command.tag, "NO", "Please select a mailbox first"
            )
            return
            
        # Get expunged messages
        expunged = self.storage.expunge_mailbox(
            self.session.selected_mailbox,
            self.session.authenticated_user
        )
        
        # Send EXPUNGE responses for each removed message
        for msg_num in expunged:
            await self.session.send_untagged(f'* {msg_num} EXPUNGE')
            
        await self.session.send_tagged_response(
            command.tag, "OK", f"EXPUNGE completed ({len(expunged)} messages removed)"
        )
        
    async def handle_copy(self, command: IMAPCommand):
        """Handle COPY command"""
        if self.session.state != "SELECTED":
            await self.session.send_tagged_response(
                command.tag, "NO", "Please select a mailbox first"
            )
            return
            
        if len(command.arguments) < 2:
            await self.session.send_tagged_response(
                command.tag, "BAD", "COPY command requires sequence set and destination mailbox"
            )
            return
            
        sequence_set = command.arguments[0]
        destination = command.arguments[1].strip('"')
        
        # Parse sequence set
        msg_nums = self._parse_sequence_set(sequence_set)
        if not msg_nums:
            await self.session.send_tagged_response(
                command.tag, "OK", "COPY completed (no messages)"
            )
            return
            
        # Copy each message
        copied_count = 0
        for msg_num in msg_nums:
            if self.storage.copy_message(
                self.session.selected_mailbox,
                destination,
                self.session.authenticated_user,
                msg_num
            ):
                copied_count += 1
                
        await self.session.send_tagged_response(
            command.tag, "OK", f"COPY completed ({copied_count} messages copied)"
        )
        
    async def handle_uid(self, command: IMAPCommand):
        """Handle UID command"""
        if self.session.state != "SELECTED":
            await self.session.send_tagged_response(
                command.tag, "NO", "Please select a mailbox first"
            )
            return
            
        if len(command.arguments) < 1:
            await self.session.send_tagged_response(
                command.tag, "BAD", "UID command requires a subcommand"
            )
            return
            
        subcommand = command.arguments[0].upper()
        
        if subcommand == "FETCH":
            # UID FETCH - treat sequence set as UIDs
            if len(command.arguments) < 3:
                await self.session.send_tagged_response(
                    command.tag, "BAD", "UID FETCH requires sequence set and data items"
                )
                return
                
            # Convert UIDs to message numbers (simplified - assumes UID == msg_num for now)
            sequence_set = command.arguments[1]
            data_items = command.arguments[2:]
            
            # For simplicity, we'll treat UIDs as message numbers
            # A full implementation would need to map UIDs to message numbers
            await self.handle_fetch(IMAPCommand(
                tag=command.tag,
                command_type=command.command_type,
                arguments=[sequence_set] + data_items,
                raw_arguments=command.raw_arguments
            ))
            
        elif subcommand == "STORE":
            # UID STORE - similar to UID FETCH
            if len(command.arguments) < 4:
                await self.session.send_tagged_response(
                    command.tag, "BAD", "UID STORE requires sequence set, data item, and value"
                )
                return
                
            sequence_set = command.arguments[1]
            data_item = command.arguments[2]
            flag_value = " ".join(command.arguments[3:])
            
            await self.handle_store(IMAPCommand(
                tag=command.tag,
                command_type=command.command_type,
                arguments=[sequence_set, data_item, flag_value],
                raw_arguments=f"{sequence_set} {data_item} {flag_value}"
            ))
            
        elif subcommand == "SEARCH":
            # UID SEARCH - return UIDs instead of message numbers
            if len(command.arguments) < 2:
                await self.session.send_tagged_response(
                    command.tag, "BAD", "UID SEARCH requires search criteria"
                )
                return
                
            criteria = " ".join(command.arguments[1:]).upper()
            
            # For simplicity, we'll treat this like regular SEARCH
            # A full implementation would return UIDs
            search_command = IMAPCommand(
                tag=command.tag,
                command_type=command.command_type,
                arguments=command.arguments[1:],
                raw_arguments=" ".join(command.arguments[1:])
            )
            await self.handle_search(search_command)
            
        elif subcommand == "COPY":
            # UID COPY - similar to COPY but with UIDs
            if len(command.arguments) < 3:
                await self.session.send_tagged_response(
                    command.tag, "BAD", "UID COPY requires sequence set and destination mailbox"
                )
                return
                
            sequence_set = command.arguments[1]
            destination = command.arguments[2].strip('"')
            
            await self.handle_copy(IMAPCommand(
                tag=command.tag,
                command_type=command.command_type,
                arguments=[sequence_set, destination],
                raw_arguments=command.raw_arguments
            ))
            
        else:
            await self.session.send_tagged_response(
                command.tag, "BAD", f"Unknown UID subcommand: {subcommand}"
            )