"""
program_runner.py – incarca si executa programe 

fiecare program ruleaza intr-un thread dedicat 
inainte de a executa o linie, runnerul verifica daca exista un breakpoint la linia respectiva 
"""

import os
import time
import threading
from typing import Dict

from models import ProgramState, ExecutionStatus
from protocol import send_message

PROGRAMS_DIR = os.path.join(os.path.dirname(__file__), "programs")

#delay intre executia liniilor pt demo 
LINE_DELAY = 1.0


def load_programs() -> Dict[str, ProgramState]:
    """
    scaneaza folderul cu programe si returneaza un dict cu program - state 
    """
    programs: Dict[str, ProgramState] = {}
    if not os.path.isdir(PROGRAMS_DIR):
        print(f"[runner] Warning: programs directory not found at {PROGRAMS_DIR}")
        return programs

    for filename in sorted(os.listdir(PROGRAMS_DIR)):
        if not filename.endswith(".txt"):
            continue
        filepath = os.path.join(PROGRAMS_DIR, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            lines = [line.rstrip("\n") for line in f if line.strip()]
        state = ProgramState(name=filename, lines=lines)
        programs[filename] = state
        print(f"[runner] Loaded program '{filename}' ({len(lines)} lines)")

    return programs


#evaluarea expresiilor 

def execute_line(line: str, variables: Dict[str, float]) -> str:
    """
    """
    if "=" not in line:
        raise ValueError(f"Not an assignment: {line!r}")

    var_name, _, expr = line.partition("=")
    var_name = var_name.strip()
    expr = expr.strip()

    if not var_name.isidentifier():
        raise ValueError(f"Invalid variable name: {var_name!r}")

    result = eval(expr, {"__builtins__": {}}, variables)

    variables[var_name] = result
    return var_name


#runnerul 

def run_program(state: ProgramState) -> None:
    """
    """
    print(f"[runner] Starting execution of '{state.name}'")

    with state.condition:
        state.status = ExecutionStatus.RUNNING
        state.current_line = 0

    skip_break_on_line: int | None = None

    while True:
        with state.condition:
           
            if state.current_line >= len(state.lines):
                state.status = ExecutionStatus.FINISHED
                state.condition.notify_all()
                break

            
            should_break = (
                state.current_line in state.breakpoints
                and state.attached_socket is not None
                and state.current_line != skip_break_on_line
            )

            if should_break:
                state.status = ExecutionStatus.PAUSED
                line_no = state.current_line
                client_sock = state.attached_socket
                print(
                    f"[runner] {state.name} PAUSED at line {line_no} "
                    f"(breakpoint)"
                )
                
                try:
                    send_message(client_sock, f"PAUSED {line_no}")
                except OSError:
                    pass  

                
                while state.status == ExecutionStatus.PAUSED:
                    state.condition.wait()

                
                skip_break_on_line = line_no

                continue

            line = state.lines[state.current_line]
            line_no = state.current_line

       
        try:
            var_name = execute_line(line, state.variables)
            value = state.variables[var_name]
            print(
                f"[runner] {state.name}:{line_no} | {line}  "
                f"=> {var_name} = {value}"
            )
        except Exception as exc:
            print(
                f"[runner] {state.name}:{line_no} | {line}  "
                f"=> ERROR: {exc}"
            )
           
            with state.condition:
                state.status = ExecutionStatus.FINISHED
                state.condition.notify_all()
            _notify_finished(state)
            break

       
        with state.condition:
            state.current_line += 1
            skip_break_on_line = None

        time.sleep(LINE_DELAY)

   
    _notify_finished(state)
    print(
        f"[runner] Program '{state.name}' finished.  "
        f"variables = {state.variables}"
    )


def _notify_finished(state: ProgramState) -> None:
    """
    """
    with state.condition:
        sock = state.attached_socket
    if sock is not None:
        try:
            send_message(sock, f"FINISHED {state.name}")
        except OSError:
            pass  


def start_single_program(state: ProgramState) -> threading.Thread:
    """
    """
    t = threading.Thread(
        target=run_program,
        args=(state,),
        name=f"prog-{state.name}",
        daemon=True,
    )
    t.start()
    print(f"[runner] Thread started for '{state.name}'")
    return t
