"""
Integration tests for the IMAP server
"""

import sys
import os
# Add the project root to the Python path so we can import imap_server
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import pytest
import threading
import time
import socket
from imap_server.main import main
from imap_server.server.tcp_server import TCPServer
from imap_server.storage.maildir_backend import MaildirBackend


@pytest.fixture
def server():
    """Create a test server instance"""
    storage = MaildirBackend()
    tcp_server = TCPServer(host='localhost', port=0, storage=storage)  # Port 0 means auto-assign
    return tcp_server


def test_server_start_stop(server):
    """Test that the server can start and stop"""
    # This is a simple test - in practice we'd use asyncio to test the server
    # For now, we just verify that the server object is created correctly
    assert server is not None
    assert server.storage is not None


def parse_imap_response(response):
    """Parse a simple IMAP response line"""
    return response.decode('utf-8').strip()


def test_imap_conversation():
    """Test a simple IMAP conversation"""
    # Start server in a separate thread
    storage = MaildirBackend()
    server = TCPServer(host='localhost', port=11430, storage=storage)
    
    # We'll run the server in a background task
    async def run_server():
        await server.start()
        await server.wait_closed()
    
    # Start server thread
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=lambda: loop.run_until_complete(run_server()))
    thread.daemon = True
    thread.start()
    
    # Give the server a moment to start
    time.sleep(0.5)
    
    try:
        # Connect to the server
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(('localhost', 11430))
        
        # Read greeting
        greeting = sock.recv(1024)
        print(f"Greeting: {greeting}")
        assert b"* OK IMAP4rev1 server ready" in greeting
        
        # Send CAPABILITY command
        sock.send(b"a001 CAPABILITY\r\n")
        response = sock.recv(1024)
        print(f"CAPABILITY response: {response}")
        assert b"* CAPABILITY" in response
        assert b"a001 OK CAPABILITY completed" in response
        
        # Send LOGIN command (with dummy credentials)
        sock.send(b'a002 LOGIN "testuser" "testpass"\r\n')
        response = sock.recv(1024)
        print(f"LOGIN response: {response}")
        # Since our validate_user accepts any non-empty credentials, this should succeed
        assert b"a002 OK LOGIN completed" in response
        
        # Send SELECT INBOX
        sock.send(b'a003 SELECT "INBOX"\r\n')
        response = sock.recv(1024)
        print(f"SELECT response: {response}")
        # Should succeed and show we have 0 messages initially
        assert b"* 0 EXISTS" in response
        assert b"a003 OK [READ-WRITE] SELECT completed" in response
        
        # Send LOGOUT command
        sock.send(b'a004 LOGOUT\r\n')
        response = sock.recv(1024)
        print(f"LOGOUT response: {response}")
        assert b"* BYE LOGOUT requested" in response
        assert b"a004 OK LOGOUT completed" in response
        
        sock.close()
        
    finally:
        # Stop the server
        # In a real test we'd properly shut down the server
        # For now, we'll just let it be cleaned up when the test ends
        pass


if __name__ == "__main__":
    test_imap_conversation()
    print("Integration test passed!")