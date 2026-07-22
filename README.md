# IMAP4rev1 Server

An academic implementation of a subset of the IMAP4rev1 protocol (RFC 3501) in Python 3.11+.

## Features

- Implements a functional subset of IMAP4rev1:
  - CAPABILITY
  - LOGIN / LOGOUT
  - SELECT / EXAMINE
  - LIST
  - FETCH (FLAGS, UID, BODY[], BODY[HEADER])
  - STORE (flag changes)
  - SEARCH (ALL, UNSEEN, FROM)
  - EXPUNGE
  - NOOP
  - Additional mailbox commands: CREATE, DELETE, RENAME, SUBSCRIBE, UNSUBSCRIBE
- Uses asyncio for asynchronous I/O
- Maildir-style mailbox storage
- State machine enforcement (Not Authenticated → Authenticated → Selected)
- Proper handling of tagged and untagged responses
- Basic search functionality
- Flag management (\\Seen, \\Answered, \\Flagged, \\Deleted, \\Draft)

## Architecture

The server follows a strict separation of concerns:

```
imap_server/
├── main.py                  # Entry point
├── server/
│   ├── tcp_server.py        # TCP server using asyncio streams
│   ├── session.py           # Per-connection state machine
│   └── parser.py            # IMAP command parser
├── commands/
│   ├── auth.py              # AUTHENTICATION commands
│   └── mailbox.py           # MAILBOX management commands
│   └── messages.py          # MESSAGE manipulation commands
├── storage/
│   ├── models.py            # Data models (Message, Mailbox)
│   └── maildir_backend.py   # Maildir storage implementation
├── tests/                   # Unit tests
├── data/                    # Mailbox storage directory
├── requirements.txt         # Dependencies (none for production)
└── README.md                # This file
```

## Requirements

- Python 3.11+
- No external dependencies for runtime (uses only standard library)
- For running tests: `pytest`

## Installation

1. Clone this repository
2. Ensure you have Python 3.11+ installed
3. (Optional) Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
4. Install test dependencies if needed:
   ```bash
   pip install pytest
   ```

## Running the Server

To start the IMAP server on localhost port 1143:

```bash
python -m imap_server.main
```

The server will listen on `localhost:1143` by default.

To change the host or port, modify the `main.py` file or pass command-line arguments (not implemented in this basic version).

## Testing

To run the test suite:

```bash
pytest
```

## Connecting to the Server

You can test the server using standard IMAP clients or command-line tools:

### Using telnet or netcat

```bash
telnet localhost 1143
# or
nc localhost 1143
```

### Using OpenSSL (for testing TLS-like behavior, though we don't implement TLS)

```bash
openssl s_client -connect localhost:1143 -quiet
```

### Example Session

```
* OK IMAP4rev1 server ready
a001 CAPABILITY
* CAPABILITY IMAP4REV1 IMAP4 STARTTLS LOGIN
a001 OK CAPABILITY completed
a002 LOGIN "testuser" "testpass"
a002 OK LOGIN completed
a003 SELECT "INBOX"
* FLAGS (\Answered \Flagged \Draft \Deleted \Seen)
* 15 EXISTS
* 0 RECENT
* OK [UIDVALIDITY 1234567890] UIDs valid
* OK [PERMANENTFLAGS (\Answered \Flagged \Draft \Deleted \Seen*)] Limited
a003 OK [READ-WRITE] SELECT completed
a004 FETCH 1 FLAGS
* 1 FETCH (FLAGS (\Seen))
a004 OK FETCH completed
a005 LOGOUT
* BYE LOGOUT requested
a005 OK LOGOUT completed
```

## Implementation Notes

### State Management
The connection progresses through three states:
1. **NOT AUTHENTICATED**: Initial state, only CAPABILITY and LOGIN allowed
2. **AUTHENTICATED**: After successful LOGIN, mailbox commands allowed
3. **SELECTED**: After SELECT/EXAMINE, message commands allowed
4. **LOGOUT**: After LOGOUT command

### Mailbox Storage
- Uses Maildir-style directory structure under `data/`
- Each user has a directory: `data/<username>/`
- Each mailbox is a subdirectory: `data/<username>/<mailbox>/`
- Each mailbox contains `tmp`, `new`, and `cur` subdirectories
- Messages are stored as files with Maildir naming conventions

### Limitations
- No TLS/STARTTLS encryption (as per requirements)
- Plain-text LOGIN only
- No concurrent access locking (single-threaded per connection, but multiple connections possible)
- No persistent UIDVALIDITY across restarts (reset on each startup)
- No actual message parsing (headers/body are treated as opaque bytes)
- Search functionality limited to ALL, UNSEEN, FROM
- No support for UTF-8 or internationalized mailbox names

## Project Structure

See the [Architecture](#architecture) section above for details.

### Key Components

#### `main.py`
Entry point that creates and starts the TCP server.

#### `server/tcp_server.py`
Handles accepting incoming TCP connections and creating sessions.

#### `server/session.py`
Manages the state of a single client connection, including:
- Reading commands from the client
- Dispatching commands to appropriate handlers
- Sending responses to the client
- State transitions

#### `server/parser.py`
Parses raw IMAP command lines into structured command objects.

#### `commands/`
Contains implementations for each IMAP command group:
- `auth.py`: CAPABILITY, LOGIN, LOGOUT
- `mailbox.py`: SELECT, EXAMINE, LIST, CREATE, DELETE, RENAME, SUBSCRIBE, UNSUBSCRIBE, STATUS
- `messages.py`: FETCH, STORE, SEARCH, EXPUNGE, COPY, UID

#### `storage/`
- `models.py`: Defines `Message` and `Mailbox` data classes
- `maildir_backend.py`: Implements Maildir-style storage on disk

## Development

This project was developed as an academic exercise to understand the IMAP protocol and practice asynchronous Python programming.

### Extending the Server

To add new IMAP commands:
1. Add a method to the appropriate command class in `commands/`
2. Add a call to that method in `session.py`'s command dispatcher
3. Update the parser if needed (for new command types)
4. Add unit tests in the `tests/` directory

### Running Tests

```bash
# Run all tests
pytest

# Run tests with coverage (if coverage is installed)
pytest --cov=imap_server

# Run a specific test file
pytest tests/test_auth.py
```

## License

This project is open source and available under the MIT License.