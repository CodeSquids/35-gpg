"""
Tests for the authentication commands
"""

import sys
import os
# Add the project root to the Python path so we can import imap_server
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import AsyncMock, MagicMock
from imap_server.commands.auth import AuthCommands
from imap_server.server.parser import IMAPCommand, CommandType
from imap_server.storage.maildir_backend import MaildirBackend
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..server.session import IMAPSession

@pytest.fixture
def mock_session():
    """Create a mock IMAP session"""
    session = MagicMock()
    session.state = "NOT_AUTHENTICATED"
    session.authenticated_user = None
    # Make the methods async mocks
    session.send_response = AsyncMock()
    session.send_untagged = AsyncMock()
    session.send_tagged_response = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def mock_storage():
    """Create a mock mailbox storage"""
    storage = MagicMock(spec=MaildirBackend)
    storage.validate_user = MagicMock(return_value=True)
    return storage


@pytest.fixture
def auth_command(mock_session, mock_storage):
    """Create an AuthCommands instance"""
    return AuthCommands(mock_session, mock_storage)


@pytest.mark.asyncio
async def test_capability(auth_command, mock_session):
    """Test the CAPABILITY command"""
    command = IMAPCommand(
        tag="a001",
        command_type=CommandType.CAPABILITY,
        arguments=[]
    )
    
    await auth_command.handle_capability(command)
    
    # Check that untagged CAPABILITY response was sent
    mock_session.send_untagged.assert_called_once()
    args = mock_session.send_untagged.call_args[0][0]
    # The send_untagged method adds "* " prefix, so we check for the argument without the prefix
    assert args == "CAPABILITY IMAP4REV1 IMAP4 STARTTLS LOGIN"
    
    # Check that tagged OK response was sent
    mock_session.send_tagged_response.assert_called_once_with(
        "a001", "OK", "CAPABILITY completed"
    )


@pytest.mark.asyncio
async def test_login_success(auth_command, mock_session, mock_storage):
    """Test successful LOGIN command"""
    command = IMAPCommand(
        tag="a002",
        command_type=CommandType.LOGIN,
        arguments=['"user"', '"password"']
    )
    
    await auth_command.handle_login(command)
    
    # Check that validate_user was called
    mock_storage.validate_user.assert_called_once_with("user", "password")
    
    # Check that session state was updated
    assert mock_session.authenticated_user == "user"
    assert mock_session.state == "AUTHENTICATED"
    
    # Check that tagged OK response was sent
    mock_session.send_tagged_response.assert_called_once_with(
        "a002", "OK", "LOGIN completed"
    )


@pytest.mark.asyncio
async def test_login_failure(auth_command, mock_session, mock_storage):
    """Test failed LOGIN command"""
    # Setup mock to return False for invalid credentials
    mock_storage.validate_user.return_value = False
    
    command = IMAPCommand(
        tag="a003",
        command_type=CommandType.LOGIN,
        arguments=['"user"', '"wrongpassword"']
    )
    
    await auth_command.handle_login(command)
    
    # Check that validate_user was called
    mock_storage.validate_user.assert_called_once_with("user", "wrongpassword")
    
    # Check that session state was NOT changed to authenticated
    assert mock_session.authenticated_user is None
    assert mock_session.state == "NOT_AUTHENTICATED"
    
    # Check that tagged NO response was sent
    mock_session.send_tagged_response.assert_called_once_with(
        "a003", "NO", "LOGIN failed: invalid username or password"
    )


@pytest.mark.asyncio
async def test_login_wrong_state(auth_command, mock_session):
    """Test LOGIN when already authenticated"""
    # Set state to AUTHENTICATED
    mock_session.state = "AUTHENTICATED"
    
    command = IMAPCommand(
        tag="a004",
        command_type=CommandType.LOGIN,
        arguments=['"user2"', '"password2"']
    )
    
    await auth_command.handle_login(command)
    
    # Check that tagged NO response was sent
    mock_session.send_tagged_response.assert_called_once_with(
        "a004", "NO", "Cannot LOGIN in current state"
    )


@pytest.mark.asyncio
async def test_logout(auth_command, mock_session):
    """Test LOGOUT command"""
    command = IMAPCommand(
        tag="a005",
        command_type=CommandType.LOGOUT,
        arguments=[]
    )
    
    await auth_command.handle_logout(command)
    
    # Check that untagged BYE was sent
    mock_session.send_untagged.assert_called_once_with("BYE LOGOUT requested")
    
    # Check that tagged OK response was sent
    mock_session.send_tagged_response.assert_called_once_with(
        "a005", "OK", "LOGOUT completed"
    )
    
    # Check that close was called
    mock_session.close.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])