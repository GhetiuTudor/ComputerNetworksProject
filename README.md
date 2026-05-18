# Remote Debugger – Distributed Arithmetic Program Debugger

A university Computer Networks project implementing a **distributed remote debugger** for simplified arithmetic programs, using **TCP sockets** and **Python threading**.

## Project Structure

```
project/
│
├── server/
│   ├── server.py            # Entry point – TCP listener
│   ├── models.py            # ProgramState dataclass
│   ├── program_runner.py    # Program loading & execution threads
│   ├── client_handler.py    # Per-client command handler
│   ├── protocol.py          # Plain-text TCP protocol helpers
│   └── programs/
│       ├── prog1.txt        # Sample arithmetic program
│       ├── prog2.txt        # Sample arithmetic program
│       └── prog3.txt        # Longer sample (10 lines)
│
├── client/
│   └── client.py            # Interactive console client
│
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Quick Start

### 1. Start the Server (Docker)

```bash
docker compose up --build
```

The server loads all programs in **READY** state and listens on **port 9000** (mapped to container port 5000).

### 2. Launch Clients (local terminals)

Open one or more terminals and run:

```bash
python client/client.py
```

The client connects to `localhost:9000` by default. You can override with:

```bash
python client/client.py <host> <port>
```

Or use any TCP tool:

```bash
nc localhost 9000
```

### Multi-Client Demo Setup

```
Terminal 1:  docker compose up --build          # server
Terminal 2:  python client/client.py            # debugger client A
Terminal 3:  python client/client.py            # debugger client B
```

## Debugging Workflow

```
ATTACH prog3.txt          # take control of the program
BREAK prog3.txt 5         # set breakpoint while READY
RUN prog3.txt             # start execution  (READY → RUNNING)
                           # ... server sends: PAUSED 5
PRINT x                   # inspect variable
SET x 100                 # modify variable
CONTINUE                  # resume execution (PAUSED → RUNNING)
                           # ... server sends: FINISHED prog3.txt
```

## Program States

```
READY  →  RUNNING  →  FINISHED
             ↕
           PAUSED
```

| State      | Meaning                                           |
|------------|---------------------------------------------------|
| `READY`    | Loaded, waiting for `RUN` command                 |
| `RUNNING`  | Executing line by line                            |
| `PAUSED`   | Hit a breakpoint, waiting for `CONTINUE`          |
| `FINISHED` | All lines executed (or error occurred)            |

## Available Commands

| Command                    | Description                              |
|----------------------------|------------------------------------------|
| `LIST`                     | List all programs and their states       |
| `STATUS <program>`         | Show detailed program status             |
| `ATTACH <program>`         | Attach to a program for debugging        |
| `DETACH`                   | Detach from current program              |
| `RUN <program>`            | Start a READY program                    |
| `BREAK <program> <line>`   | Set breakpoint (while READY or PAUSED)   |
| `UNBREAK <program> <line>` | Remove breakpoint (while READY or PAUSED)|
| `CONTINUE`                 | Resume a paused program                  |
| `PRINT <variable>`         | Inspect variable (while PAUSED)          |
| `SET <variable> <value>`   | Modify variable (while PAUSED)           |
| `HELP`                     | Show available commands                  |
| `QUIT`                     | Disconnect from the server               |

## Server Notifications

The server sends asynchronous notifications to attached clients:

| Notification             | Meaning                                  |
|--------------------------|------------------------------------------|
| `PAUSED <line>`          | Program hit a breakpoint and is paused   |
| `FINISHED <program>`     | Program has completed execution          |

## Protocol Format

- All messages are newline-terminated UTF-8 strings.
- `STATUS` returns a single-line response:
  ```
  STATUS prog3.txt state=READY line=0/10 vars={-} breakpoints=[0,5] attached=192.168.65.1:5000
  ```

## Tech Stack

- Python 3.11 (stdlib only – no external packages)
- TCP sockets (`socket`)
- `threading` + `threading.Condition`
- Docker & Docker Compose

## Roadmap

- [x] Expression evaluator (arithmetic parser)
- [x] Breakpoint support (`BREAK`, `UNBREAK`)
- [x] Pause / Resume via `threading.Condition`
- [x] Variable inspection (`PRINT`) and modification (`SET`)
- [x] Breakpoint re-trigger fix
- [x] `FINISHED` notification to attached client
- [x] Single-line protocol-safe STATUS
- [x] Graceful server shutdown
- [x] Explicit `RUN` command and `READY` state
- [ ] Stepping (`STEP`)

## License

University coursework – not licensed for redistribution.
