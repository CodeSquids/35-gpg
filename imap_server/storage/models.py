"""
Data models for the IMAP server
"""

from dataclasses import dataclass, field
from typing import Set, Optional
import time
import hashlib
import os


@dataclass
class Message:
    """Represents an email message"""
    uid: int
    msg_id: str
    flags: Set[str] = field(default_factory=set)
    internal_date: float = field(default_factory=time.time)
    size: int = 0
    _content: bytes = b""
    
    def __post_init__(self):
        # Ensure flags are lowercase for consistency
        self.flags = {f.lower() for f in self.flags}
        
    def add_flag(self, flag: str):
        """Add a flag to the message"""
        self.flags.add(flag.lower())
        
    def remove_flag(self, flag: str):
        """Remove a flag from the message"""
        self.flags.discard(flag.lower())
        
    def has_flag(self, flag: str) -> bool:
        """Check if message has a flag"""
        return flag.lower() in self.flags
        
    def set_content(self, content: bytes):
        """Set the message content and update size"""
        self._content = content
        self.size = len(content)
        
    def get_content(self) -> bytes:
        """Get the message content"""
        return self._content
        
    def get_headers(self) -> bytes:
        """Extract headers from the message content"""
        # Simple implementation: headers end with first empty line
        content = self.get_content()
        if not content:
            return b""
        # Find the first empty line (separates headers from body)
        parts = content.split(b"\r\n\r\n", 1)
        if len(parts) == 2:
            return parts[0] + b"\r\n\r\n"  # Include the terminating CRLF
        else:
            # No body, all is headers
            return content


@dataclass
class Mailbox:
    """Represents a mailbox (folder)"""
    name: str
    path: str
    uid_validity: int = field(default_factory=lambda: int(time.time()))
    uid_next: int = 1
    messages: dict = field(default_factory=dict)  # uid -> Message
    
    def add_message(self, message: Message) -> int:
        """Add a message to the mailbox and assign UID"""
        message.uid = self.uid_next
        self.uid_next += 1
        self.messages[message.uid] = message
        return message.uid
        
    def remove_message(self, uid: int) -> bool:
        """Remove a message by UID"""
        if uid in self.messages:
            del self.messages[uid]
            return True
        return False
        
    def get_message(self, uid: int) -> Optional[Message]:
        """Get a message by UID"""
        return self.messages.get(uid)
        
    def get_message_count(self) -> int:
        """Get the number of messages in the mailbox"""
        return len(self.messages)
        
    def get_recent_count(self) -> int:
        """Get the number of recent messages (not implemented, always 0)"""
        return 0
        
    def get_unseen_count(self) -> int:
        """Get the number of unseen messages"""
        return sum(1 for msg in self.messages.values() if not msg.has_flag('\\seen'))