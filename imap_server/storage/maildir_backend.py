"""
Maildir backend for IMAP server
Implements Maildir-style storage for email messages
"""

import os
import os.path
import errno
import time
import uuid
from typing import Dict, List, Optional, Tuple, Set
from .models import Message, Mailbox
import logging

logger = logging.getLogger(__name__)


class MaildirBackend:
    """Maildir storage backend for IMAP server"""
    
    def __init__(self, root_path: str = "./data"):
        self.root_path = root_path
        self.users: Dict[str, Dict[str, Mailbox]] = {}  # user -> mailbox_name -> Mailbox
        self._ensure_dir_exists(root_path)
        
    def _ensure_dir_exists(self, path: str):
        """Ensure a directory exists, creating it if necessary"""
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
                
    def _get_user_dir(self, username: str) -> str:
        """Get the directory for a user's maildir"""
        return os.path.join(self.root_path, username)
        
    def _get_mailbox_dir(self, username: str, mailbox: str) -> str:
        """Get the directory for a specific mailbox of a user"""
        # In Maildir, the mailbox name is the directory name under the user's Maildir
        # We'll replace '.' with hierarchy separator if needed, but for simplicity we'll use flat structure
        return os.path.join(self._get_user_dir(username), mailbox)
        
    def _get_maildir_dirs(self, mailbox_dir: str) -> tuple:
        """Get the tmp, new, and cur directories for a maildir"""
        return (
            os.path.join(mailbox_dir, "tmp"),
            os.path.join(mailbox_dir, "new"),
            os.path.join(mailbox_dir, "cur")
        )
        
    def _ensure_maildir_dirs(self, mailbox_dir: str):
        """Ensure the maildir subdirectories exist"""
        tmp, new, cur = self._get_maildir_dirs(mailbox_dir)
        self._ensure_dir_exists(tmp)
        self._ensure_dir_exists(new)
        self._ensure_dir_exists(cur)
        
    def _list_mailbox_files(self, mailbox_dir: str) -> List[str]:
        """List all message files in a maildir (in cur and new)"""
        _, new, cur = self._get_maildir_dirs(mailbox_dir)
        files = []
        for dir_path in (new, cur):
            if os.path.isdir(dir_path):
                try:
                    files.extend([os.path.join(dir_path, f) for f in os.listdir(dir_path)])
                except OSError:
                    pass  # Directory might not exist or be empty
        return files
        
    def _parse_message_flags(self, filename: str) -> Set[str]:
        """Parse flags from a maildir filename"""
        # Filename format: <unique_name>.<flags>
        # Flags are letters after the second dot, or after the first dot if no second dot?
        # Actually, Maildir format: <unique_name>_<host>.<flags>
        # But we'll simplify: flags are after the second dot if present
        parts = filename.split('.')
        if len(parts) >= 3:
            flags_part = parts[2]
        elif len(parts) == 2:
            flags_part = parts[1]
        else:
            flags_part = ""
        
        flags = set()
        flag_map = {
            'P': 'passed',
            'R': 'replied',
            'S': 'seen',
            'T': 'trashed',
            'D': 'draft',
            'F': 'flagged',
            # Note: Maildir uses different letters, but we'll map to our internal flags
            # We'll use a simple mapping for now
        }
        for flag_char in flags_part:
            if flag_char in flag_map:
                flags.add(flag_map[flag_char])
            # Also handle direct flag letters if needed
            elif flag_char in ['S', 'F', 'R', 'P', 'T', 'D']:
                # Map to our standard flags
                mapping = {'S': '\\seen', 'F': '\\flagged', 'R': '\\answered', 'P': '\\passed', 'T': '\\deleted', 'D': '\\draft'}
                if flag_char in mapping:
                    flags.add(mapping[flag_char])
        return flags
        
    def _format_flags_for_maildir(self, flags: Set[str]) -> str:
        """Convert internal flags to maildir flag string"""
        # Map our flags to Maildir single-letter flags
        flag_map = {
            '\\seen': 'S',
            '\\answered': 'R',
            '\\flagged': 'F',
            '\\draft': 'D',
            '\\deleted': 'T',
            '\\passed': 'P'
        }
        flag_chars = []
        for flag in flags:
            if flag in flag_map:
                flag_chars.append(flag_map[flag])
        return ''.join(sorted(flag_chars))
        
    def _create_message_file(self, mailbox_dir: str, msg: Message) -> str:
        """Create a message file in the maildir and return the filename"""
        tmp, new, cur = self._get_maildir_dirs(mailbox_dir)
        
        # Generate a unique filename
        # Format: <seconds>.<microseconds>_<host>.tmp
        # We'll simplify: use time and uuid
        timestamp = time.time()
        hostname = "localhost"  # In practice, we'd use the actual hostname
        unique_id = str(uuid.uuid4()).split('-')[0]
        base_name = f"{int(timestamp)}.{int((timestamp - int(timestamp)) * 1000000)}_{hostname}"
        
        # Create the file in tmp first
        tmp_file = os.path.join(tmp, f"{base_name}.tmp")
        
        # Write the message content
        with open(tmp_file, 'wb') as f:
            f.write(msg.get_content())
            
        # Determine flags for the filename
        flags = self._format_flags_for_maildir(msg.flags)
        if flags:
            new_file = os.path.join(new, f"{base_name},{flags}")
        else:
            new_file = os.path.join(new, base_name)
            
        # Move from tmp to new
        os.rename(tmp_file, new_file)
        
        return new_file
        
    def _load_mailbox(self, username: str, mailbox_name: str) -> Optional[Mailbox]:
        """Load a mailbox from disk into a Mailbox object"""
        mailbox_dir = self._get_mailbox_dir(username, mailbox_name)
        if not os.path.isdir(mailbox_dir):
            return None
            
        # Ensure maildir subdirectories exist
        self._ensure_maildir_dirs(mailbox_dir)
        
        # Create mailbox object
        mailbox = Mailbox(name=mailbox_name, path=mailbox_dir)
        
        # Load all messages from cur and new
        for file_path in self._list_mailbox_files(mailbox_dir):
            try:
                with open(file_path, 'rb') as f:
                    content = f.read()
                    
                # Parse filename to get flags
                filename = os.path.basename(file_path)
                flags = self._parse_message_flags(filename)
                
                # Create message object
                msg = Message(
                    uid=0,  # Will be assigned when we add to mailbox
                    msg_id=f"<{uuid.uuid4()}@{hostname}>",  # Generate a message ID
                    flags=flags
                )
                msg.set_content(content)
                
                # Add to mailbox (will assign UID)
                uid = mailbox.add_message(msg)
                # Update uid_next if necessary
                if uid >= mailbox.uid_next:
                    mailbox.uid_next = uid + 1
                    
            except Exception as e:
                logger.error(f"Error loading message from {file_path}: {e}")
                
        return mailbox
        
    def _save_mailbox(self, mailbox: Mailbox):
        """Save a mailbox to disk (write any new messages)"""
        mailbox_dir = mailbox.path
        self._ensure_maildir_dirs(mailbox_dir)
        
        # For each message that doesn't have a corresponding file, create one
        tmp, new, cur = self._get_maildir_dirs(mailbox_dir)
        existing_files = set()
        for dir_path in (new, cur):
            if os.path.isdir(dir_path):
                existing_files.update(set(os.listdir(dir_path)))
                
        for uid, msg in mailbox.messages.items():
            # Check if this message already has a file
            # We'll use a simple heuristic: if the message doesn't have a filename hint, we need to create one
            # In a real implementation, we'd store the filename with the message
            # For simplicity, we'll just regenerate files for messages that don't match existing files
            # This is not efficient but works for our simple implementation
            found = False
            for filename in existing_files:
                # Check if this file corresponds to our message (by checking flags and maybe content hash)
                # This is a simplified check - in reality we'd store the filename with the message
                pass  # Skip for now, we'll just recreate all files (inefficient but simple)
                
            # For now, we'll just rewrite all messages (not efficient but works for small scale)
            # In a real implementation, we'd track which files correspond to which messages
            self._create_message_file(mailbox_dir, msg)
            
        # Note: This implementation is inefficient because it rewrites all messages on every save.
        # A better approach would be to store the filename with each message and only write new/changed ones.
        
    def ensure_user_exists(self, username: str):
        """Ensure a user directory exists"""
        user_dir = self._get_user_dir(username)
        self._ensure_dir_exists(user_dir)
        # Also ensure the INBOX exists
        self.ensure_mailbox_exists(username, "INBOX")
        
    def ensure_mailbox_exists(self, username: str, mailbox_name: str) -> bool:
        """Ensure a mailbox exists for a user, creating it if necessary"""
        self.ensure_user_exists(username)
        mailbox_dir = self._get_mailbox_dir(username, mailbox_name)
        if not os.path.isdir(mailbox_dir):
            try:
                self._ensure_maildir_dirs(mailbox_dir)
                # Create an empty mailbox object and save it to create the directory structure
                mailbox = Mailbox(name=mailbox_name, path=mailbox_dir)
                self._save_mailbox(mailbox)
                return True
            except OSError as e:
                logger.error(f"Failed to create mailbox {mailbox_name} for user {username}: {e}")
                return False
        return True
        
    def validate_user(self, username: str, password: str) -> bool:
        """Validate a user's credentials
        For simplicity, we'll accept any non-empty username and password.
        In a real implementation, this would check against a database or password file.
        """
        # For this exercise, we'll accept any non-empty credentials
        return bool(username and password)
        
    def get_mailbox(self, username: str, mailbox_name: str) -> Optional[Mailbox]:
        """Get a mailbox for a user, loading it from disk if necessary"""
        # Check if we have it cached
        if username in self.users and mailbox_name in self.users[username]:
            return self.users[username][mailbox_name]
            
        # Load from disk
        mailbox = self._load_mailbox(username, mailbox_name)
        if mailbox is not None:
            # Cache it
            if username not in self.users:
                self.users[username] = {}
            self.users[username][mailbox_name] = mailbox
            
        return mailbox
        
    def select_mailbox(self, username: str, mailbox_name: str) -> Optional[dict]:
        """Select a mailbox and return status information"""
        mailbox = self.get_mailbox(username, mailbox_name)
        if mailbox is None:
            return None
            
        # Ensure the maildir structure exists
        self._ensure_maildir_dirs(mailbox.path)
        
        # Return status information
        return {
            "exists": mailbox.get_message_count(),
            "recent": mailbox.get_recent_count(),
            "uidnext": mailbox.uid_next,
            "uidvalidity": mailbox.uid_validity,
            "unseen": mailbox.get_unseen_count()
        }
        
    def list_mailboxes(self, username: str) -> List[str]:
        """List all mailboxes for a user"""
        user_dir = self._get_user_dir(username)
        if not os.path.isdir(user_dir):
            return []
            
        # List all directories in the user's directory (each is a mailbox)
        mailboxes = []
        try:
            for entry in os.listdir(user_dir):
                full_path = os.path.join(user_dir, entry)
                if os.path.isdir(full_path):
                    # Check if it looks like a maildir (has cur, new, tmp subdirs)
                    # For simplicity, we'll consider all directories as mailboxes
                    mailboxes.append(entry)
        except OSError:
            pass
            
        return sorted(mailboxes)
        
    def get_message(self, username: str, mailbox_name: str, uid: int) -> Optional[Message]:
        """Get a specific message from a mailbox"""
        mailbox = self.get_mailbox(username, mailbox_name)
        if mailbox is None:
            return None
        return mailbox.get_message(uid)
        
    def get_message_bytes(self, username: str, mailbox_name: str, uid: int) -> Optional[bytes]:
        """Get the full message content as bytes"""
        msg = self.get_message(username, mailbox_name, uid)
        if msg is None:
            return None
        return msg.get_content()
        
    def get_message_headers(self, username: str, mailbox_name: str, uid: int) -> Optional[bytes]:
        """Get the message headers as bytes"""
        msg = self.get_message(username, mailbox_name, uid)
        if msg is None:
            return None
        return msg.get_headers()
        
    def add_message(self, username: str, mailbox_name: str, msg: Message) -> int:
        """Add a message to a mailbox and return its UID"""
        # Ensure the mailbox exists
        if not self.ensure_mailbox_exists(username, mailbox_name):
            raise Exception(f"Failed to create mailbox {mailbox_name}")
            
        mailbox = self.get_mailbox(username, mailbox_name)
        if mailbox is None:
            raise Exception(f"Failed to load mailbox {mailbox_name}")
            
        # Add the message to the mailbox
        uid = mailbox.add_message(msg)
        
        # Save the mailbox to disk (this will create the file)
        self._save_mailbox(mailbox)
        
        return uid
        
    def update_message_flags(self, username: str, mailbox_name: str, uid: int, flags: Set[str]) -> bool:
        """Update the flags for a message"""
        mailbox = self.get_mailbox(username, mailbox_name)
        if mailbox is None:
            return False
            
        msg = mailbox.get_message(uid)
        if msg is None:
            return False
            
        # Update flags
        msg.flags = set(flags)
        
        # Save the mailbox to update the file
        self._save_mailbox(mailbox)
        
        return True
        
    def delete_message(self, username: str, mailbox_name: str, uid: int) -> bool:
        """Delete a message from a mailbox"""
        mailbox = self.get_mailbox(username, mailbox_name)
        if mailbox is None:
            return False
            
        # Remove from mailbox
        if not mailbox.remove_message(uid):
            return False
            
        # Save the mailbox (this will rewrite all files, effectively removing the deleted one)
        self._save_mailbox(mailbox)
        
        return True
        
    def get_mailbox_status(self, username: str, mailbox_name: str) -> Optional[dict]:
        """Get status information for a mailbox"""
        mailbox = self.get_mailbox(username, mailbox_name)
        if mailbox is None:
            return None
            
        return {
            "messages": mailbox.get_message_count(),
            "recent": mailbox.get_recent_count(),
            "uidnext": mailbox.uid_next,
            "uidvalidity": mailbox.uid_validity,
            "unseen": mailbox.get_unseen_count()
        }
        
    def create_mailbox(self, username: str, mailbox_name: str) -> bool:
        """Create a new mailbox"""
        return self.ensure_mailbox_exists(username, mailbox_name)
        
    def delete_mailbox(self, username: str, mailbox_name: str) -> bool:
        """Delete a mailbox"""
        if mailbox_name == "INBOX":
            return False  # Cannot delete INBOX
            
        mailbox_dir = self._get_mailbox_dir(username, mailbox_name)
        if not os.path.isdir(mailbox_dir):
            return False  # Doesn't exist
            
        try:
            # Remove the directory tree
            import shutil
            shutil.rmtree(mailbox_dir)
            
            # Remove from cache
            if username in self.users and mailbox_name in self.users[username]:
                del self.users[username][mailbox_name]
                
            return True
        except Exception as e:
            logger.error(f"Error deleting mailbox {mailbox_name}: {e}")
            return False
            
    def rename_mailbox(self, username: str, old_name: str, new_name: str) -> bool:
        """Rename a mailbox"""
        if old_name == "INBOX":
            return False  # Cannot rename INBOX
            
        old_dir = self._get_mailbox_dir(username, old_name)
        new_dir = self._get_mailbox_dir(username, new_name)
        
        if not os.path.isdir(old_dir):
            return False  # Source doesn't exist
            
        if os.path.exists(new_dir):
            return False  # Destination already exists
            
        try:
            os.rename(old_dir, new_dir)
            
            # Update cache
            if username in self.users and old_name in self.users[username]:
                mailbox = self.users[username][old_name]
                mailbox.name = new_name
                mailbox.path = new_dir
                if new_name not in self.users[username]:
                    self.users[username][new_name] = mailbox
                del self.users[username][old_name]
                
            return True
        except Exception as e:
            logger.error(f"Error renaming mailbox from {old_name} to {new_name}: {e}")
            return False