"""
IMAP Command Parser
Parses raw IMAP commands into structured command objects
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Union
import logging

logger = logging.getLogger(__name__)


class CommandType(Enum):
    """IMAP4rev1 command types"""
    CAPABILITY = "CAPABILITY"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    SELECT = "SELECT"
    EXAMINE = "EXAMINE"
    LIST = "LIST"
    FETCH = "FETCH"
    STORE = "STORE"
    SEARCH = "SEARCH"
    EXPUNGE = "EXPUNGE"
    NOOP = "NOOP"
    CREATE = "CREATE"
    DELETE = "DELETE"
    RENAME = "RENAME"
    SUBSCRIBE = "SUBSCRIBE"
    UNSUBSCRIBE = "UNSUBSCRIBE"
    STATUS = "STATUS"
    APPEND = "APPEND"
    COPY = "COPY"
    UID = "UID"


@dataclass
class IMAPCommand:
    """Represents a parsed IMAP command"""
    tag: str
    command_type: CommandType
    arguments: List[str]
    raw_arguments: str = ""  # For literal handling
    

class IMAPParser:
    """Parses IMAP protocol commands from raw text."""
    
    # Regular expression for parsing IMAP commands
    # Format: tag command [arguments] 
    COMMAND_PATTERN = re.compile(r'^(\S+)\s+(\S+)(?:\s+(.*))?$')
    
    # Literal pattern: {n}\r\n followed by n bytes
    LITERAL_PATTERN = re.compile(r'\{(\d+)\}\r\n')
    
    def parse(self, line: str) -> IMAPCommand:
        """
        Parse an IMAP command line.
        
        Args:
            line: Raw command line from client (without \r\n)
            
        Returns:
            IMAPCommand object
            
        Raises:
            ValueError: If the line cannot be parsed
        """
        line = line.strip()
        if not line:
            raise ValueError("Empty command line")
            
        match = self.COMMAND_PATTERN.match(line)
        if not match:
            raise ValueError(f"Invalid command format: {line}")
            
        tag, command_str, args_str = match.groups()
        
        # Convert command string to enum
        try:
            command_type = CommandType(command_str.upper())
        except ValueError:
            raise ValueError(f"Unknown command: {command_str}")
            
        # Parse arguments
        arguments = []
        if args_str:
            # Simple argument splitting - will be enhanced for literals
            arguments = self._parse_arguments(args_str)
            
        return IMAPCommand(
            tag=tag,
            command_type=command_type,
            arguments=arguments,
            raw_arguments=args_str or ""
        )
        
    def _parse_arguments(self, args_str: str) -> List[str]:
        """
        Parse command arguments, handling quoted strings and literals.
        This is a simplified parser - a full implementation would need 
        to handle nested quotes, literals, etc. properly.
        """
        arguments = []
        current = ""
        in_quotes = False
        i = 0
        
        while i < len(args_str):
            char = args_str[i]
            
            if char == '"' and (i == 0 or args_str[i-1] != '\\'):
                in_quotes = not in_quotes
                current += char
            elif char == ' ' and not in_quotes:
                if current:
                    arguments.append(current)
                    current = ""
            elif char == '{' and not in_quotes:
                # Handle literal - this is simplified
                # A full implementation would need to parse the literal size
                # and extract the literal data from the stream
                current += char
            else:
                current += char
                
            i += 1
            
        if current:
            arguments.append(current)
            
        return arguments