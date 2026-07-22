# Agent Prompt — Python IMAP Mail Server

## Project
Build an IMAP mail server in Python, implementing a functional subset of RFC 3501 (IMAP4rev1). 
This is an academic project — the goal is a correct, well-architected, testable server that a 
real IMAP client (Thunderbird, Mutt) can connect to, not a toy script.

## Hard requirements
- Language: Python 3.11+
- Networking: use asyncio (asyncio.start_server, StreamReader/StreamWriter) — not raw threads. 
  IMAP is line-based with length-prefixed literals ({n}\r\n<n bytes>), which asyncio streams 
  handle cleanly.
- Line endings: every protocol line ends in \r\n, not \n. Handle this explicitly.
- Storage backend: Maildir format (per-user new/, cur/, tmp/ directories, one file per message). 
  You may reference Python's stdlib mailbox.Maildir to understand the format, but implement the 
  mailbox logic yourself rather than wrapping it directly, unless told otherwise.
- Tagged responses: every client command has a tag (e.g. a001 LOGIN user pass); every final 
  server response echoes that tag (a001 OK LOGIN completed). Untagged responses use * 
  (e.g. * 23 EXISTS).

## Required commands (priority order)
1. CAPABILITY
2. LOGIN / LOGOUT
3. SELECT / EXAMINE
4. LIST
5. FETCH — at minimum FLAGS, UID, BODY[], BODY[HEADER]
6. STORE — flag changes (\Seen, \Answered, \Deleted, etc.)
7. SEARCH — basic criteria: ALL, UNSEEN, FROM
8. EXPUNGE
9. NOOP

Session state machine must be enforced explicitly: Not Authenticated → Authenticated → Selected. 
Commands issued in the wrong state must be rejected with a tagged BAD/NO response 
(e.g. FETCH before SELECT).

## Required architecture (directory layout)
imap_server/
├── main.py                  # entry point, starts the asyncio server
├── server/
│   ├── tcp_server.py         # connection accept loop
│   ├── session.py            # per-connection state machine
│   └── parser.py             # raw line/literal -> (tag, command, args)
├── commands/
│   ├── auth.py               # LOGIN, LOGOUT, CAPABILITY
│   ├── mailbox.py            # SELECT, EXAMINE, LIST, CREATE
│   └── messages.py           # FETCH, STORE, SEARCH, EXPUNGE
├── storage/
│   ├── models.py              # Mailbox / Message data classes
│   └── maildir_backend.py     # Maildir read/write logic
├── tests/
│   ├── test_parser.py
│   ├── test_auth.py
│   └── test_fetch.py
├── data/                      # sample users + test mail
├── requirements.txt
└── README.md

Strict separation of concerns is a grading/review criterion:
- parser.py only turns raw bytes/lines into structured commands — no sockets, no storage.
- commands/* contain protocol logic only — no direct socket I/O, no direct file I/O 
  (go through storage/).
- storage/* know nothing about IMAP syntax — they expose plain Message/Mailbox objects.

This split must allow tests/test_parser.py to test parsing with zero open sockets.

## Deliverables
1. Full working source tree as above.
2. requirements.txt (stdlib-only preferred; justify any dependency).
3. pytest suite covering: parser edge cases (literals, multi-argument FETCH, malformed commands), 
   the auth/session state machine, and FETCH/STORE against a sample Maildir fixture.
4. README.md covering: how to run the server, how to point Thunderbird/Mutt/telnet/openssl s_client 
   at it for a manual test, and known limitations (no TLS/STARTTLS, no multi-user concurrency 
   guarantees, etc. — be explicit about what's out of scope).
5. Explicit error handling: malformed lines, unexpected literal sizes, client disconnects 
   mid-command, timeouts.

## Explicitly out of scope (do not implement unless asked)
- STARTTLS / TLS / SASL authentication mechanisms beyond plain LOGIN
- IMAP extensions (IDLE, CONDSTORE, QRESYNC, etc.)
- A GUI or web front-end
- Sending mail (SMTP) — this is IMAP only, mailbox management, not mail delivery

## Working style
- Build incrementally in this order: (1) bare TCP echo server with greeting, (2) parser + 
  CAPABILITY/LOGIN/LOGOUT + session states, (3) SELECT/LIST/Maildir reading, (4) FETCH/STORE 
  with literals, (5) SEARCH/EXPUNGE, (6) tests + README.
- After each stage, show a sample manual test transcript (e.g. a nc/telnet session) demonstrating 
  the new behavior actually working before moving to the next stage.
- Flag any point where the RFC is ambiguous or where you're deliberately simplifying, rather than 
  silently guessing.