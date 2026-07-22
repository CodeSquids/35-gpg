"""
Tests for the mailbox commands
"""

import sys
import os
# Add the project root to the Python path so we can import imap_server
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import AsyncMock, MagicMock
from imap_server.commands.mailbox import MailboxCommands
from imap_server.server.parser import IMAPCommand, CommandType
from imap_server.storage.maildir_backend import MaildirBackend


@pytest.fixture
def mock_session():
    """Create a mock IMAP session"""
    session = MagicMock()
    session.state = "AUTHENTICATED"
    session.authenticated_user = "testuser"
    session.selected_mailbox = None
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
    # Mock select_mailbox to return some fake mailbox info
    storage.select_mailbox = MagicMock(return_value={
        "exists": 15,
        "recent": 0,
        "uidnext": 100,
        "uidvalidity": 1234567890,
        "unseen": 3
    })
    storage.list_mailboxes = MagicMock(return_value=["INBOX", "Sent", "Drafts"])
    storage.get_mailbox_status = MagicMock(return_value={
        "messages": 15,
        "recent": 0,
        "uidnext": 100,
        "uidvalidity": 1234567890,  # Fixed the key name to match what the code expects
        "unseen": 3
    })
    # Mock other storage methods
    storage.create_mailbox = MagicMock(return_value=True)
    storage.delete_mailbox = MagicMock(return_value=True)
    storage.rename_mailbox = MagicMock(return_value=True)
    return storage


@pytest.fixture
def mailbox_command(mock_session, mock_storage):
    """Create a MailboxCommands instance"""
    return MailboxCommands(mock_session, mock_storage)


@pytest.mark.asyncio
async def test_select_success(mailbox_command, mock_session, mock_storage):
    """Test successful SELECT command"""
    command = IMAPCommand(
        tag="a001",
        command_type=CommandType.SELECT,
        arguments=['"INBOX"']
    )
    
    await mailbox_command.handle_select(command)
    
    # Check that select_mailbox was called
    mock_storage.select_mailbox.assert_called_once_with("INBOX", "testuser")
    
    # Check that session state was updated
    assert mock_session.selected_mailbox == "INBOX"
    assert mock_session.state == "SELECTED"
    
    # Check that untagged responses were sent
    # FLAGS, EXISTS, RECENT, UIDVALIDITY, PERMANENTFLAGS
    assert mock_session.send_untagged.call_count >= 4
    
    # Check that tagged OK response was sent
    mock_session.send_tagged_response.assert_called_once_with(
        "a001", "OK", "[READ-WRITE] SELECT completed"
    )


@pytest.mark.asyncio
async def test_select_failure(mailbox_command, mock_session, mock_storage):
    """Test SELECT when mailbox doesn't exist"""
    # Make select_mailbox return None
    mock_storage.select_mailbox.return_value = None
    
    command = IMAPCommand(
        tag="a002",
        command_type=CommandType.SELECT,
        arguments=['"Nonexistent"']
    )
    
    await mailbox_command.handle_select(command)
    
    # Check that select_mailbox was called
    mock_storage.select_mailbox.assert_called_once_with("Nonexistent", "testuser")
    
    # Check that session state was NOT changed to SELECTED
    assert mock_session.selected_mailbox is None
    assert mock_session.state == "AUTHENTICATED"  # Should remain unchanged
    
    # Check that tagged NO response was sent
    mock_session.send_tagged_response.assert_called_once_with(
        "a002", "NO", "Mailbox 'Nonexistent' doesn't exist"
    )


@pytest.mark.asyncio
async def test_select_wrong_state(mailbox_command, mock_session):
    """Test SELECT when not authenticated"""
    # Set state to NOT_AUTHENTICATED
    mock_session.state = "NOT_AUTHENTICATED"
    
    command = IMAPCommand(
        tag="a003",
        command_type=CommandType.SELECT,
        arguments=['"INBOX"']
    )
    
    await mailbox_command.handle_select(command)
    
    # Check that tagged NO response was sent
    mock_session.send_tagged_response.assert_called_once_with(
        "a003", "NO", "Please authenticate first"
    )


@pytest.mark.asyncio
async def test_examine_success(mailbox_command, mock_session, mock_storage):
    """Test successful EXAMINE command"""
    command = IMAPCommand(
        tag="a004",
        command_type=CommandType.EXAMINE,
        arguments=['"INBOX"']
    )
    
    await mailbox_command.handle_examine(command)
    
    # Check that select_mailbox was called
    mock_storage.select_mailbox.assert_called_once_with("INBOX", "testuser")
    
    # Check that session state was updated
    assert mock_session.selected_mailbox == "INBOX"
    assert mock_session.state == "SELECTED"
    
    # Check that untagged responses were sent
    # Should include FLAGS, EXISTS, RECENT, UIDVALIDITY, and PERMANENTFLAGS (empty for read-only)
    assert mock_session.send_untagged.call_count >= 4
    
    # Check that tagged OK response was sent
    mock_session.send_tagged_response.assert_called_once_with(
        "a004", "OK", "[READ-ONLY] EXAMINE completed"
    )


@pytest.mark.asyncio
async def test_list_command(mailbox_command, mock_session, mock_storage):
    """Test LIST command"""
    command = IMAPCommand(
        tag="a005",
        command_type=CommandType.LIST,
        arguments=['""', '"*"']  # reference "" and mailbox pattern "*"
    )
    
    await mailbox_command.handle_list(command)
    
    # Check that list_mailboxes was called
    mock_storage.list_mailboxes.assert_called_once_with("testuser")
    
    # Check that untagged LIST responses were sent (one for each mailbox)
    # We expect 3 mailboxes: INBOX, Sent, Drafts
    assert mock_session.send_untagged.call_count == 3
    
    # Check that each call was to send an untagged LIST response
    calls = mock_session.send_untagged.call_args_list
    for i, call in enumerate(calls):
        arg = call[0][0]
        assert arg.startswith("* LIST")
        assert f'"{["INBOX", "Sent", "Drafts"][i]}"' in arg
    
    # Check that tagged OK response was sent
    mock_session.send_tagged_response.assert_called_once_with(
        "a005", "OK", "LIST completed"
    )


@pytest.mark.asyncio
async def test_create_mailbox(mailbox_command, mock_session, mock_storage):
    """Test CREATE command"""
    # Make sure create_mailbox returns True
    mock_storage.create_mailbox = MagicMock(return_value=True)
    
    command = IMAPCommand(
        tag="a006",
        command_type=CommandType.CREATE,
        arguments=['"NewMailbox"']
    )
    
    await mailbox_command.handle_create(command)
    
    # Check that create_mailbox was called
    mock_storage.create_mailbox.assert_called_once_with("NewMailbox", "testuser")
    
    # Check that tagged OK response was sent
    mock_session.send_tagged_response.assert_called_once_with(
        "a006", "OK", "CREATE completed for mailbox 'NewMailbox'"
    )


@pytest.mark.asyncio
async def test_delete_mailbox(mailbox_command, mock_session, mock_storage):
    """Test DELETE command"""
    # Make sure delete_mailbox returns True
    mock_storage.delete_mailbox = MagicMock(return_value=True)
    
    command = IMAPCommand(
        tag="a007",
        command_type=CommandType.DELETE,
        arguments=['"OldMailbox"']
    )
    
    await mailbox_command.handle_delete(command)
    
    # Check that delete_mailbox was called
    mock_storage.delete_mailbox.assert_called_once_with("OldMailbox", "testuser")
    
    # Check that tagged OK response was sent
    mock_session.send_tagged_response.assert_called_once_with(
        "a007", "OK", "DELETE completed for mailbox 'OldMailbox'"
    )


@pytest.mark.asyncio
async def test_delete_inbox_fails(mailbox_command, mock_session):
    """Test that deleting INBOX is not allowed"""
    command = IMAPCommand(
        tag="a008",
        command_type=CommandType.DELETE,
        arguments=['"INBOX"']
    )
    
    await mailbox_command.handle_delete(command)
    
    # Check that tagged NO response was sent
    mock_session.send_tagged_response.assert_called_once_with(
        "a008", "NO", "Cannot delete INBOX"
    )


if __name__ == "__main__":
    pytest.main([__file__])