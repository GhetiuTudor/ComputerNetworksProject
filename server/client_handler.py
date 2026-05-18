"""
"""

import socket
import threading
from typing import Dict

from models import ProgramState, ExecutionStatus
from program_runner import start_single_program
from protocol import (
    send_message,
    receive_message,
    CMD_LIST,
    CMD_STATUS,
    CMD_ATTACH,
    CMD_DETACH,
    CMD_QUIT,
    CMD_BREAK,
    CMD_UNBREAK,
    CMD_CONTINUE,
    CMD_PRINT,
    CMD_SET,
    CMD_RUN,
    RESP_OK,
    RESP_ERROR,
)

def _format_status_line(s: ProgramState) -> str:
    """Return a protocol-safe, single-line status summary."""
    bp = ",".join(str(b) for b in sorted(s.breakpoints)) if s.breakpoints else "-"
    vs = ",".join(f"{k}={v}" for k, v in s.variables.items()) if s.variables else "-"
    attached = s.attached_client or "-"
    return (
        f"STATUS {s.name} "
        f"state={s.status.value} "
        f"line={s.current_line}/{len(s.lines)} "
        f"vars={{{vs}}} "
        f"breakpoints=[{bp}] "
        f"attached={attached}"
    )




def handle_client(
    client_sock: socket.socket,
    client_addr: tuple,
    programs: Dict[str, ProgramState],
) -> None:
    """
    Main loop for a single client connection.

    Runs until the client sends QUIT or disconnects.
    """
    addr_str = f"{client_addr[0]}:{client_addr[1]}"
    print(f"[handler] Client connected: {addr_str}")
    send_message(client_sock, "WELCOME to the Remote Debugger. Type HELP for commands.")

    attached_program: str | None = None   

    try:
        while True:
            raw = receive_message(client_sock)
            if raw is None:
                print(f"[handler] Client {addr_str} disconnected.")
                break

            parts = raw.split(maxsplit=1)
            if not parts:
                send_message(client_sock, f"{RESP_ERROR} Empty command.")
                continue

            cmd = parts[0].upper()
            arg = parts[1] if len(parts) > 1 else ""

            # ---- LIST -----------------------------------------------
            if cmd == CMD_LIST:
                if not programs:
                    send_message(client_sock, "No programs loaded.")
                else:
                    lines = []
                    for name, state in programs.items():
                        lines.append(
                            f"  {name}  {state.status.value}  "
                            f"line={state.current_line}/{len(state.lines)}"
                        )
                    send_message(client_sock, "\n".join(lines))

            # ---- STATUS <program> ------------------------------------
            elif cmd == CMD_STATUS:
                name = arg.strip()
                if not name:
                    send_message(client_sock, f"{RESP_ERROR} Usage: STATUS <program>")
                elif name not in programs:
                    send_message(client_sock, f"{RESP_ERROR} Unknown program: {name}")
                else:
                    s = programs[name]
                    with s.condition:
                        line = _format_status_line(s)
                    send_message(client_sock, line)

            # ---- ATTACH <program> ------------------------------------
            elif cmd == CMD_ATTACH:
                name = arg.strip()
                if not name:
                    send_message(client_sock, f"{RESP_ERROR} Usage: ATTACH <program>")
                elif name not in programs:
                    send_message(client_sock, f"{RESP_ERROR} Unknown program: {name}")
                else:
                    state = programs[name]
                    with state.condition:
                        if state.attached_client is not None and state.attached_client != addr_str:
                            send_message(
                                client_sock,
                                f"{RESP_ERROR} Program already controlled by {state.attached_client}",
                            )
                        else:
                            state.attached_client = addr_str
                            state.attached_socket = client_sock
                            attached_program = name
                            send_message(client_sock, f"{RESP_OK} Attached to {name}")
                            print(f"[handler] {addr_str} attached to {name}")

            # ---- DETACH ----------------------------------------------
            elif cmd == CMD_DETACH:
                if attached_program is None:
                    send_message(client_sock, f"{RESP_ERROR} Not attached to any program.")
                else:
                    state = programs[attached_program]
                    with state.condition:
                        state.attached_client = None
                        state.attached_socket = None
                        # If the program is paused, resume it so the
                        # runner thread does not deadlock.
                        if state.status == ExecutionStatus.PAUSED:
                            state.status = ExecutionStatus.RUNNING
                            state.condition.notify_all()
                            print(f"[handler] Auto-resumed {attached_program} on detach")
                    send_message(client_sock, f"{RESP_OK} Detached from {attached_program}")
                    print(f"[handler] {addr_str} detached from {attached_program}")
                    attached_program = None

            # ---- RUN <program> -------------------------------------------
            elif cmd == CMD_RUN:
                name = arg.strip()
                if not name:
                    send_message(client_sock, f"{RESP_ERROR} Usage: RUN <program>")
                elif name not in programs:
                    send_message(client_sock, f"{RESP_ERROR} Unknown program: {name}")
                else:
                    state = programs[name]
                    with state.condition:
                        if state.status != ExecutionStatus.READY:
                            send_message(
                                client_sock,
                                f"{RESP_ERROR} {name} is {state.status.value}. "
                                f"RUN is only valid when status is READY.",
                            )
                        else:
                            
                            start_single_program(state)
                            print(f"[handler] {addr_str} started {name}")
                            send_message(client_sock, f"{RESP_OK} Started {name}")

            # ---- BREAK <program> <line> ------------------------------
            elif cmd == CMD_BREAK:
                tokens = arg.split()
                if len(tokens) != 2:
                    send_message(client_sock, f"{RESP_ERROR} Usage: BREAK <program> <line>")
                elif attached_program is None:
                    send_message(client_sock, f"{RESP_ERROR} Not attached to any program.")
                else:
                    name, line_str = tokens
                    if name != attached_program:
                        send_message(
                            client_sock,
                            f"{RESP_ERROR} You are attached to {attached_program}, "
                            f"not {name}.",
                        )
                    elif name not in programs:
                        send_message(client_sock, f"{RESP_ERROR} Unknown program: {name}")
                    else:
                        state = programs[name]
                        with state.condition:
                            if state.status == ExecutionStatus.RUNNING:
                                send_message(
                                    client_sock,
                                    f"{RESP_ERROR} {name} is RUNNING. "
                                    f"BREAK is only allowed while READY or PAUSED.",
                                )
                                continue
                            if state.status == ExecutionStatus.FINISHED:
                                send_message(
                                    client_sock,
                                    f"{RESP_ERROR} {name} is FINISHED.",
                                )
                                continue
                        try:
                            line_no = int(line_str)
                        except ValueError:
                            send_message(
                                client_sock,
                                f"{RESP_ERROR} Invalid line number: '{line_str}' is not an integer.",
                            )
                            continue
                        if line_no < 0 or line_no >= len(state.lines):
                            send_message(
                                client_sock,
                                f"{RESP_ERROR} Line {line_no} out of range "
                                f"(valid: 0–{len(state.lines) - 1}).",
                            )
                        else:
                            with state.condition:
                                state.breakpoints.add(line_no)
                            print(f"[handler] Breakpoint added: {name}:{line_no}")
                            send_message(
                                client_sock,
                                f"{RESP_OK} Breakpoint set at {name}:{line_no}",
                            )

            # ---- UNBREAK <program> <line> ----------------------------
            elif cmd == CMD_UNBREAK:
                tokens = arg.split()
                if len(tokens) != 2:
                    send_message(client_sock, f"{RESP_ERROR} Usage: UNBREAK <program> <line>")
                elif attached_program is None:
                    send_message(client_sock, f"{RESP_ERROR} Not attached to any program.")
                else:
                    name, line_str = tokens
                    if name != attached_program:
                        send_message(
                            client_sock,
                            f"{RESP_ERROR} You are attached to {attached_program}, "
                            f"not {name}.",
                        )
                    elif name not in programs:
                        send_message(client_sock, f"{RESP_ERROR} Unknown program: {name}")
                    else:
                        state = programs[name]
                        with state.condition:
                            if state.status == ExecutionStatus.RUNNING:
                                send_message(
                                    client_sock,
                                    f"{RESP_ERROR} {name} is RUNNING. "
                                    f"UNBREAK is only allowed while READY or PAUSED.",
                                )
                                continue
                            if state.status == ExecutionStatus.FINISHED:
                                send_message(
                                    client_sock,
                                    f"{RESP_ERROR} {name} is FINISHED.",
                                )
                                continue
                        try:
                            line_no = int(line_str)
                        except ValueError:
                            send_message(
                                client_sock,
                                f"{RESP_ERROR} Invalid line number: '{line_str}' is not an integer.",
                            )
                            continue
                        state = programs[name]
                        with state.condition:
                            if line_no in state.breakpoints:
                                state.breakpoints.discard(line_no)
                                print(f"[handler] Breakpoint removed: {name}:{line_no}")
                                send_message(
                                    client_sock,
                                    f"{RESP_OK} Breakpoint removed at {name}:{line_no}",
                                )
                            else:
                                send_message(
                                    client_sock,
                                    f"{RESP_ERROR} No breakpoint at {name}:{line_no}.",
                                )

            # ---- CONTINUE --------------------------------------------
            elif cmd == CMD_CONTINUE:
                if attached_program is None:
                    send_message(client_sock, f"{RESP_ERROR} Not attached to any program.")
                else:
                    state = programs[attached_program]
                    with state.condition:
                        if state.status != ExecutionStatus.PAUSED:
                            send_message(
                                client_sock,
                                f"{RESP_ERROR} {attached_program} is not paused "
                                f"(current state: {state.status.value}).",
                            )
                        else:
                            state.status = ExecutionStatus.RUNNING
                            state.condition.notify_all()
                            print(f"[handler] Resumed {attached_program}")
                            send_message(client_sock, f"{RESP_OK} Resumed {attached_program}")

            # ---- PRINT <variable> ------------------------------------
            elif cmd == CMD_PRINT:
                var_name = arg.strip()
                if not var_name:
                    send_message(client_sock, f"{RESP_ERROR} Usage: PRINT <variable>")
                elif attached_program is None:
                    send_message(client_sock, f"{RESP_ERROR} Not attached to any program.")
                else:
                    state = programs[attached_program]
                    with state.condition:
                        if state.status != ExecutionStatus.PAUSED:
                            send_message(
                                client_sock,
                                f"{RESP_ERROR} {attached_program} is not paused "
                                f"(current state: {state.status.value}). "
                                f"PRINT only works while paused.",
                            )
                        elif var_name not in state.variables:
                            available = ", ".join(state.variables.keys()) or "(none)"
                            send_message(
                                client_sock,
                                f"{RESP_ERROR} Variable '{var_name}' not found. "
                                f"Available: {available}",
                            )
                        else:
                            value = state.variables[var_name]
                            print(f"[handler] PRINT {var_name} = {value} ({attached_program})")
                            send_message(client_sock, f"VALUE {var_name} {value}")

            # ---- SET <variable> <value> ------------------------------
            elif cmd == CMD_SET:
                tokens = arg.split(maxsplit=1)
                if len(tokens) != 2:
                    send_message(client_sock, f"{RESP_ERROR} Usage: SET <variable> <value>")
                elif attached_program is None:
                    send_message(client_sock, f"{RESP_ERROR} Not attached to any program.")
                else:
                    var_name, val_str = tokens
                    state = programs[attached_program]
                    with state.condition:
                        if state.status != ExecutionStatus.PAUSED:
                            send_message(
                                client_sock,
                                f"{RESP_ERROR} {attached_program} is not paused "
                                f"(current state: {state.status.value}). "
                                f"SET only works while paused.",
                            )
                        elif var_name not in state.variables:
                            available = ", ".join(state.variables.keys()) or "(none)"
                            send_message(
                                client_sock,
                                f"{RESP_ERROR} Variable '{var_name}' not found. "
                                f"Available: {available}",
                            )
                        else:
                            try:
                                new_value = float(val_str) if "." in val_str else int(val_str)
                            except ValueError:
                                send_message(
                                    client_sock,
                                    f"{RESP_ERROR} Invalid value: '{val_str}' "
                                    f"is not a valid number.",
                                )
                                continue
                            old_value = state.variables[var_name]
                            state.variables[var_name] = new_value
                            print(
                                f"[handler] SET {var_name}: {old_value} -> {new_value} "
                                f"({attached_program})"
                            )
                            send_message(client_sock, f"{RESP_OK} {var_name} = {new_value}")

            # ---- QUIT ------------------------------------------------
            elif cmd == CMD_QUIT:
                send_message(client_sock, "BYE")
                break

            # ---- HELP ------------------------------------------------
            elif cmd == "HELP":
                help_text = (
                    "=== Remote Debugger Commands ===\n"
                    "\n"
                    "  General:\n"
                    "    LIST                     - List all programs and their states\n"
                    "    STATUS <program>         - Show detailed program status\n"
                    "    HELP                     - Show this help message\n"
                    "    QUIT                     - Disconnect from the server\n"
                    "\n"
                    "  Execution:\n"
                    "    ATTACH <program>         - Attach to a program for debugging\n"
                    "    DETACH                   - Detach from current program\n"
                    "    RUN <program>            - Start a READY program\n"
                    "\n"
                    "  Breakpoints (while READY or PAUSED):\n"
                    "    BREAK <program> <line>   - Set a breakpoint (0-based line)\n"
                    "    UNBREAK <program> <line> - Remove a breakpoint\n"
                    "    CONTINUE                 - Resume a paused program\n"
                    "\n"
                    "  Inspection (while PAUSED):\n"
                    "    PRINT <variable>         - Show variable value\n"
                    "    SET <variable> <value>   - Modify variable value\n"
                    "\n"
                    "  Workflow: ATTACH -> BREAK -> RUN -> PAUSED -> PRINT/SET -> CONTINUE"
                )
                send_message(client_sock, help_text)

            else:
                send_message(
                    client_sock,
                    f"{RESP_ERROR} Unknown command: '{cmd}'. Type HELP for a list of commands.",
                )

    finally:
        if attached_program and attached_program in programs:
            state = programs[attached_program]
            with state.condition:
                if state.attached_client == addr_str:
                    state.attached_client = None
                    state.attached_socket = None

                    if state.status == ExecutionStatus.PAUSED:
                        state.status = ExecutionStatus.RUNNING
                        state.condition.notify_all()
                        print(f"[handler] Auto-resumed {attached_program} (client disconnected)")
        try:
            client_sock.close()
        except OSError:
            pass
        print(f"[handler] Connection closed: {addr_str}")

