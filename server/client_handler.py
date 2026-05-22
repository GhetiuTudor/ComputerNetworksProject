"""
client_handler.py – gestioneaza comenzile primite de la un client

Fiecare client conectat primeste un thread dedicat care ruleaza functia
handle_client(). Aceasta functie citeste comenzi in bucla, le proceseaza
si trimite raspunsuri. Suporta toate comenzile protocolului de debugging:
LIST, STATUS, ATTACH, DETACH, RUN, BREAK, UNBREAK, CONTINUE, PRINT, SET, QUIT, HELP.
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


# formateaza informatiile despre un program intr-o singura linie
# (sigura pentru protocol - nu contine newline-uri suplimentare)
def _format_status_line(s: ProgramState) -> str:
    """
    Returneaza un rezumat al starii programului pe o singura linie,
    compatibil cu protocolul (fara newline-uri in interior).

    Formatul: STATUS <nume> state=<stare> line=<curenta>/<total>
              vars={<variabile>} breakpoints=[<linii>] attached=<client>
    """
    # construieste string-ul cu breakpoint-urile sortate, sau "-" daca nu exista
    bp = ",".join(str(b) for b in sorted(s.breakpoints)) if s.breakpoints else "-"
    # construieste string-ul cu variabilele, sau "-" daca nu exista
    vs = ",".join(f"{k}={v}" for k, v in s.variables.items()) if s.variables else "-"
    # adresa clientului atasat sau "-" daca nimeni nu e atasat
    attached = s.attached_client or "-"
    return (
        f"STATUS {s.name} "
        f"state={s.status.value} "
        f"line={s.current_line}/{len(s.lines)} "
        f"vars={{{vs}}} "
        f"breakpoints=[{bp}] "
        f"attached={attached}"
    )


# bucla principala care proceseaza comenzile unui singur client
def handle_client(
    client_sock: socket.socket,
    client_addr: tuple,
    programs: Dict[str, ProgramState],
) -> None:
    """
    Bucla principala pentru o singura conexiune client.

    Citeste comenzi in bucla, le proceseaza si trimite raspunsuri.
    Ruleaza pana cand clientul trimite QUIT sau se deconecteaza.

    Parametri:
        client_sock: socket-ul clientului conectat
        client_addr: tuplu (ip, port) al clientului
        programs:    dictionarul global cu programele incarcate (partajat intre threaduri)
    """
    # creeaza un string citibil cu adresa clientului pentru logging
    addr_str = f"{client_addr[0]}:{client_addr[1]}"
    print(f"[handler] Client connected: {addr_str}")
    # trimite mesajul de bun venit la conectare
    send_message(client_sock, "WELCOME to the Remote Debugger. Type HELP for commands.")

    # retine la ce program este atasat clientul (None = neatasat)
    attached_program: str | None = None

    try:
        while True:  # bucla de procesare comenzi
            # citeste urmatoarea comanda de la client
            raw = receive_message(client_sock)
            if raw is None:
                print(f"[handler] Client {addr_str} disconnected.")
                break  # clientul s-a deconectat

            # desparte comanda in: comanda + argument(e)
            # maxsplit=1 pastreaza argumentele ca un singur string
            parts = raw.split(maxsplit=1)
            if not parts:
                send_message(client_sock, f"{RESP_ERROR} Empty command.")
                continue  # comanda goala, asteapta urmatoarea

            cmd = parts[0].upper()  # comanda (case-insensitive)
            arg = parts[1] if len(parts) > 1 else ""  # argumentele (daca exista)

            # ---- LIST -----------------------------------------------
            # listeaza toate programele si starea lor curenta
            if cmd == CMD_LIST:
                if not programs:
                    send_message(client_sock, "No programs loaded.")
                else:
                    lines = []
                    for name, state in programs.items():
                        # adauga o linie cu numele, starea si progresul fiecarui program
                        lines.append(
                            f"  {name}  {state.status.value}  "
                            f"line={state.current_line}/{len(state.lines)}"
                        )
                    # trimite toate liniile unite cu newline
                    send_message(client_sock, "\n".join(lines))

            # ---- STATUS <program> ------------------------------------
            # afiseaza informatii detaliate despre un program specific
            elif cmd == CMD_STATUS:
                name = arg.strip()
                if not name:
                    send_message(client_sock, f"{RESP_ERROR} Usage: STATUS <program>")
                elif name not in programs:
                    send_message(client_sock, f"{RESP_ERROR} Unknown program: {name}")
                else:
                    s = programs[name]
                    # citeste starea sub lock pentru consistenta
                    with s.condition:
                        line = _format_status_line(s)
                    send_message(client_sock, line)

            # ---- ATTACH <program> ------------------------------------
            # ataseaza clientul la un program pentru a-l putea controla
            elif cmd == CMD_ATTACH:
                name = arg.strip()
                if not name:
                    send_message(client_sock, f"{RESP_ERROR} Usage: ATTACH <program>")
                elif name not in programs:
                    send_message(client_sock, f"{RESP_ERROR} Unknown program: {name}")
                else:
                    state = programs[name]
                    with state.condition:
                        # verifica daca alt client e deja atasat
                        if state.attached_client is not None and state.attached_client != addr_str:
                            send_message(
                                client_sock,
                                f"{RESP_ERROR} Program already controlled by {state.attached_client}",
                            )
                        else:
                            # ataseaza clientul curent la program
                            state.attached_client = addr_str
                            state.attached_socket = client_sock
                            attached_program = name
                            send_message(client_sock, f"{RESP_OK} Attached to {name}")
                            print(f"[handler] {addr_str} attached to {name}")

            # ---- DETACH ----------------------------------------------
            # detaseaza clientul de la programul curent
            elif cmd == CMD_DETACH:
                if attached_program is None:
                    send_message(client_sock, f"{RESP_ERROR} Not attached to any program.")
                else:
                    state = programs[attached_program]
                    with state.condition:
                        # sterge informatiile de atasare
                        state.attached_client = None
                        state.attached_socket = None
                        # daca programul era oprit pe breakpoint, il reluam automat
                        # altfel thread-ul runner ar ramane blocat pe Condition.wait()
                        if state.status == ExecutionStatus.PAUSED:
                            state.status = ExecutionStatus.RUNNING
                            state.condition.notify_all()  # deblocheaza runner-ul
                            print(f"[handler] Auto-resumed {attached_program} on detach")
                    send_message(client_sock, f"{RESP_OK} Detached from {attached_program}")
                    print(f"[handler] {addr_str} detached from {attached_program}")
                    attached_program = None  # reseteaza programul atasat local

            # ---- RUN <program> -------------------------------------------
            # porneste executia unui program care este in starea READY
            elif cmd == CMD_RUN:
                name = arg.strip()
                if not name:
                    send_message(client_sock, f"{RESP_ERROR} Usage: RUN <program>")
                elif name not in programs:
                    send_message(client_sock, f"{RESP_ERROR} Unknown program: {name}")
                else:
                    state = programs[name]
                    with state.condition:
                        # RUN functioneaza doar pe programe in starea READY
                        if state.status != ExecutionStatus.READY:
                            send_message(
                                client_sock,
                                f"{RESP_ERROR} {name} is {state.status.value}. "
                                f"RUN is only valid when status is READY.",
                            )
                        else:
                            # creeaza si porneste un thread dedicat pentru executie
                            start_single_program(state)
                            print(f"[handler] {addr_str} started {name}")
                            send_message(client_sock, f"{RESP_OK} Started {name}")

            # ---- BREAK <program> <line> ------------------------------
            # seteaza un breakpoint la o linie specificata
            # functioneaza doar cand programul este in READY sau PAUSED
            elif cmd == CMD_BREAK:
                tokens = arg.split()
                if len(tokens) != 2:
                    send_message(client_sock, f"{RESP_ERROR} Usage: BREAK <program> <line>")
                elif attached_program is None:
                    send_message(client_sock, f"{RESP_ERROR} Not attached to any program.")
                else:
                    name, line_str = tokens
                    # verifica ca programul specificat e cel la care e atasat clientul
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
                        # verifica starea sub lock - BREAK nu e permis in RUNNING sau FINISHED
                        with state.condition:
                            if state.status == ExecutionStatus.RUNNING:
                                send_message(
                                    client_sock,
                                    f"{RESP_ERROR} {name} is RUNNING. "
                                    f"BREAK is only allowed while READY or PAUSED.",
                                )
                                continue  # revine la citirea urmatoarei comenzi
                            if state.status == ExecutionStatus.FINISHED:
                                send_message(
                                    client_sock,
                                    f"{RESP_ERROR} {name} is FINISHED.",
                                )
                                continue
                        # parseaza numarul de linie
                        try:
                            line_no = int(line_str)
                        except ValueError:
                            send_message(
                                client_sock,
                                f"{RESP_ERROR} Invalid line number: '{line_str}' is not an integer.",
                            )
                            continue
                        # verifica ca linia e in intervalul valid
                        if line_no < 0 or line_no >= len(state.lines):
                            send_message(
                                client_sock,
                                f"{RESP_ERROR} Line {line_no} out of range "
                                f"(valid: 0–{len(state.lines) - 1}).",
                            )
                        else:
                            # adauga breakpoint-ul in set (set = cautare O(1))
                            with state.condition:
                                state.breakpoints.add(line_no)
                            print(f"[handler] Breakpoint added: {name}:{line_no}")
                            send_message(
                                client_sock,
                                f"{RESP_OK} Breakpoint set at {name}:{line_no}",
                            )

            # ---- UNBREAK <program> <line> ----------------------------
            # sterge un breakpoint de la o linie specificata
            # functioneaza doar cand programul este in READY sau PAUSED
            elif cmd == CMD_UNBREAK:
                tokens = arg.split()
                if len(tokens) != 2:
                    send_message(client_sock, f"{RESP_ERROR} Usage: UNBREAK <program> <line>")
                elif attached_program is None:
                    send_message(client_sock, f"{RESP_ERROR} Not attached to any program.")
                else:
                    name, line_str = tokens
                    # verifica ca programul specificat e cel la care e atasat clientul
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
                        # verifica starea sub lock - UNBREAK nu e permis in RUNNING sau FINISHED
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
                        # parseaza numarul de linie
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
                            # verifica daca breakpoint-ul exista inainte de stergere
                            if line_no in state.breakpoints:
                                # discard() sterge elementul fara sa arunce eroare daca nu exista
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
            # reia executia unui program oprit pe breakpoint (PAUSED -> RUNNING)
            elif cmd == CMD_CONTINUE:
                if attached_program is None:
                    send_message(client_sock, f"{RESP_ERROR} Not attached to any program.")
                else:
                    state = programs[attached_program]
                    with state.condition:
                        # CONTINUE functioneaza doar daca programul e in PAUSED
                        if state.status != ExecutionStatus.PAUSED:
                            send_message(
                                client_sock,
                                f"{RESP_ERROR} {attached_program} is not paused "
                                f"(current state: {state.status.value}).",
                            )
                        else:
                            # schimba starea si notifica thread-ul runner sa continue
                            state.status = ExecutionStatus.RUNNING
                            state.condition.notify_all()  # deblocheaza runner-ul care asteapta pe wait()
                            print(f"[handler] Resumed {attached_program}")
                            send_message(client_sock, f"{RESP_OK} Resumed {attached_program}")

            # ---- PRINT <variable> ------------------------------------
            # afiseaza valoarea unei variabile din programul atasat
            # functioneaza doar cand programul este in PAUSED
            elif cmd == CMD_PRINT:
                var_name = arg.strip()
                if not var_name:
                    send_message(client_sock, f"{RESP_ERROR} Usage: PRINT <variable>")
                elif attached_program is None:
                    send_message(client_sock, f"{RESP_ERROR} Not attached to any program.")
                else:
                    state = programs[attached_program]
                    with state.condition:
                        # PRINT functioneaza doar in PAUSED (variabilele se schimba in RUNNING)
                        if state.status != ExecutionStatus.PAUSED:
                            send_message(
                                client_sock,
                                f"{RESP_ERROR} {attached_program} is not paused "
                                f"(current state: {state.status.value}). "
                                f"PRINT only works while paused.",
                            )
                        elif var_name not in state.variables:
                            # variabila nu exista - afiseaza lista de variabile disponibile
                            available = ", ".join(state.variables.keys()) or "(none)"
                            send_message(
                                client_sock,
                                f"{RESP_ERROR} Variable '{var_name}' not found. "
                                f"Available: {available}",
                            )
                        else:
                            # citeste si trimite valoarea variabilei
                            value = state.variables[var_name]
                            print(f"[handler] PRINT {var_name} = {value} ({attached_program})")
                            send_message(client_sock, f"VALUE {var_name} {value}")

            # ---- SET <variable> <value> ------------------------------
            # modifica valoarea unei variabile din programul atasat
            # functioneaza doar cand programul este in PAUSED
            elif cmd == CMD_SET:
                tokens = arg.split(maxsplit=1)  # maxsplit=1 pt a pastra valoarea intacta
                if len(tokens) != 2:
                    send_message(client_sock, f"{RESP_ERROR} Usage: SET <variable> <value>")
                elif attached_program is None:
                    send_message(client_sock, f"{RESP_ERROR} Not attached to any program.")
                else:
                    var_name, val_str = tokens
                    state = programs[attached_program]
                    with state.condition:
                        # SET functioneaza doar in PAUSED
                        if state.status != ExecutionStatus.PAUSED:
                            send_message(
                                client_sock,
                                f"{RESP_ERROR} {attached_program} is not paused "
                                f"(current state: {state.status.value}). "
                                f"SET only works while paused.",
                            )
                        elif var_name not in state.variables:
                            # variabila nu exista - afiseaza lista de variabile disponibile
                            available = ", ".join(state.variables.keys()) or "(none)"
                            send_message(
                                client_sock,
                                f"{RESP_ERROR} Variable '{var_name}' not found. "
                                f"Available: {available}",
                            )
                        else:
                            # parseaza noua valoare ca int sau float
                            try:
                                # daca contine punct zecimal -> float, altfel -> int
                                new_value = float(val_str) if "." in val_str else int(val_str)
                            except ValueError:
                                send_message(
                                    client_sock,
                                    f"{RESP_ERROR} Invalid value: '{val_str}' "
                                    f"is not a valid number.",
                                )
                                continue
                            # salveaza vechea valoare pentru logging si actualizeaza
                            old_value = state.variables[var_name]
                            state.variables[var_name] = new_value
                            print(
                                f"[handler] SET {var_name}: {old_value} -> {new_value} "
                                f"({attached_program})"
                            )
                            send_message(client_sock, f"{RESP_OK} {var_name} = {new_value}")

            # ---- QUIT ------------------------------------------------
            # deconecteaza clientul de la server
            elif cmd == CMD_QUIT:
                send_message(client_sock, "BYE")  # trimite confirmare
                break  # iese din bucla de procesare comenzi

            # ---- HELP ------------------------------------------------
            # afiseaza lista de comenzi disponibile cu descrieri
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

            # ---- comanda necunoscuta ---------------------------------
            else:
                send_message(
                    client_sock,
                    f"{RESP_ERROR} Unknown command: '{cmd}'. Type HELP for a list of commands.",
                )

    finally:
        # --- cleanup la deconectare ---
        # daca clientul era atasat la un program, il detaseaza si reia executia daca e cazul
        if attached_program and attached_program in programs:
            state = programs[attached_program]
            with state.condition:
                # verifica ca acest client e cel atasat (nu alt client)
                if state.attached_client == addr_str:
                    state.attached_client = None
                    state.attached_socket = None

                    # daca programul era oprit pe breakpoint, il reluam automat
                    # altfel thread-ul runner ar ramane blocat pe Condition.wait() la infinit
                    if state.status == ExecutionStatus.PAUSED:
                        state.status = ExecutionStatus.RUNNING
                        state.condition.notify_all()
                        print(f"[handler] Auto-resumed {attached_program} (client disconnected)")
        # inchide socket-ul clientului
        try:
            client_sock.close()
        except OSError:
            pass  # ignora erori la inchidere (socket deja inchis)
        print(f"[handler] Connection closed: {addr_str}")
