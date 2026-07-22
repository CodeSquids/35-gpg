"""
Tests for the IMAP command parser
"""

import pytest
from imap_server.server.parser import IMAPParser, CommandType, IMAPCommand


def test_parse_simple_command():
    """Test parsing a simple command with no arguments"""
    parser = IMAPParser()
    cmd = parser.parse("a001 CAPABILITY")
    assert cmd.tag == "a001"
    assert cmd.command_type == CommandType.CAPABILITY
    assert cmd.arguments == []


def test_parse_command_with_arguments():
    """Test parsing a command with arguments"""
    parser = IMAPParser()
    cmd = parser.parse('a002 LOGIN "user" "password"')
    assert cmd.tag == "a002"
    assert cmd.command_type == CommandType.LOGIN
    assert cmd.arguments == ['"user"', '"password"']


def test_parse_command_with_quoted_arguments():
    """Test parsing a command with quoted arguments containing spaces"""
    parser = IMAPParser()
    cmd = parser.parse('a003 SELECT "Inbox"')
    assert cmd.tag == "a003"
    assert cmd.command_type == CommandType.SELECT
    assert cmd.arguments == ['"Inbox"']


def test_parse_command_with_nil():
    """Test parsing a command with NIL argument"""
    parser = IMAPParser()
    cmd = parser.parse('a004 SEARCH NIL')
    assert cmd.tag == "a004"
    assert cmd.command_type == CommandType.SEARCH
    assert cmd.arguments == ["NIL"]


def test_parse_command_with_asterisk():
    """Test parsing a command with asterisk (used in SEQUENCE)"""
    parser = IMAPParser()
    cmd = parser.parse('a005 FETCH * FLAGS')
    assert cmd.tag == "a005"
    assert cmd.command_type == CommandType.FETCH
    assert cmd.arguments == ["*", "FLAGS"]


def test_parse_command_with_range():
    """Test parsing a command with a range (e.g., 2:4)"""
    parser = IMAPParser()
    cmd = parser.parse('a006 FETCH 2:4 FLAGS')
    assert cmd.tag == "a006"
    assert cmd.command_type == CommandType.FETCH
    assert cmd.arguments == ["2:4", "FLAGS"]


def test_parse_command_multiple_arguments():
    """Test parsing a command with multiple arguments"""
    parser = IMAPParser()
    cmd = parser.parse('a007 STORE 1 +FLAGS \\Seen')
    assert cmd.tag == "a007"
    assert cmd.command_type == CommandType.STORE
    assert cmd.arguments == ["1", "+FLAGS", "\\Seen"]


def test_parse_empty_line():
    """Test that parsing an empty line raises ValueError"""
    parser = IMAPParser()
    with pytest.raises(ValueError, match="Empty command line"):
        parser.parse("")


def test_parse_invalid_command():
    """Test that parsing an invalid command raises ValueError"""
    parser = IMAPParser()
    with pytest.raises(ValueError, match="Unknown command"):
        parser.parse("a008 INVALIDCOMMAND")


def test_parse_no_tag():
    """Test that parsing a line with no tag raises ValueError"""
    parser = IMAPParser()
    with pytest.raises(ValueError):
        parser.parse("CAPABILITY")


if __name__ == "__main__":
    pytest.main([__file__])