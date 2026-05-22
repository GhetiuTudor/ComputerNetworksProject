"""
program_runner.py – incarca si executa programe aritmetice

Fiecare program ruleaza intr-un thread dedicat. Inainte de a executa
o linie, runner-ul verifica daca exista un breakpoint la linia respectiva.
Daca da si exista un client atasat, programul se opreste (PAUSED) si
asteapta comanda CONTINUE de la client.
"""

import os
import time
import threading
from typing import Dict

from models import ProgramState, ExecutionStatus
from protocol import send_message

# calea catre folderul cu programe (.txt) - relativa la locatia acestui fisier
PROGRAMS_DIR = os.path.join(os.path.dirname(__file__), "programs")

# delay in secunde intre executia fiecarei linii (pentru demo/vizualizare)
LINE_DELAY = 1.0


# incarca toate programele din folderul programs/ si returneaza un dictionar
def load_programs() -> Dict[str, ProgramState]:
    """
    Scaneaza folderul cu programe si returneaza un dictionar
    cu numele fisierului ca cheie si ProgramState ca valoare.
    Toate programele sunt incarcate in starea READY.
    """
    programs: Dict[str, ProgramState] = {}

    # verifica daca folderul cu programe exista
    if not os.path.isdir(PROGRAMS_DIR):
        print(f"[runner] Warning: programs directory not found at {PROGRAMS_DIR}")
        return programs

    # itereaza prin fisierele .txt in ordine alfabetica
    for filename in sorted(os.listdir(PROGRAMS_DIR)):
        if not filename.endswith(".txt"):
            continue  # ignora fisierele care nu sunt programe
        filepath = os.path.join(PROGRAMS_DIR, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            # citeste liniile, elimina newline-ul si ignora liniile goale
            lines = [line.rstrip("\n") for line in f if line.strip()]
        # creeaza starea programului cu liniile incarcate
        state = ProgramState(name=filename, lines=lines)
        programs[filename] = state
        print(f"[runner] Loaded program '{filename}' ({len(lines)} lines)")

    return programs


# evalueaza o singura linie de cod (o atribuire de forma: variabila = expresie)
def execute_line(line: str, variables: Dict[str, float]) -> str:
    """
    Executa o singura linie de program de forma 'variabila = expresie'.
    Evalueaza expresia folosind variabilele existente si salveaza rezultatul.

    Parametri:
        line:      linia de cod de executat (ex: "z = x + y")
        variables: dictionarul de variabile existente (se modifica in-place)

    Returneaza:
        Numele variabilei care a fost atribuita.

    Arunca ValueError daca linia nu este o atribuire valida.
    """
    # verifica ca linia contine operatorul de atribuire
    if "=" not in line:
        raise ValueError(f"Not an assignment: {line!r}")

    # desparte linia in: nume_variabila = expresie
    # partition returneaza (inainte, separator, dupa)
    var_name, _, expr = line.partition("=")
    var_name = var_name.strip()  # elimina spatiile din jurul numelui
    expr = expr.strip()          # elimina spatiile din jurul expresiei

    # valideaza ca numele variabilei este un identificator Python valid
    if not var_name.isidentifier():
        raise ValueError(f"Invalid variable name: {var_name!r}")

    # eval() evalueaza expresia matematica
    # __builtins__: {} dezactiveaza functiile built-in pentru securitate
    # variables permite accesul la variabilele existente ale programului
    result = eval(expr, {"__builtins__": {}}, variables)

    # salveaza rezultatul in dictionarul de variabile
    variables[var_name] = result
    return var_name


# functia principala de executie - ruleaza programul linie cu linie
def run_program(state: ProgramState) -> None:
    """
    Executa un program linie cu linie intr-un thread dedicat.

    Inainte de fiecare linie verifica daca exista breakpoint.
    Daca se intalneste un breakpoint si exista un client atasat,
    programul trece in PAUSED si trimite notificare clientului.
    Thread-ul asteapta pe Condition pana primeste CONTINUE.

    La sfarsit trimite notificare FINISHED clientului atasat.
    """
    print(f"[runner] Starting execution of '{state.name}'")

    # marcheaza programul ca RUNNING si reseteaza linia curenta
    with state.condition:
        state.status = ExecutionStatus.RUNNING
        state.current_line = 0

    # variabila care previne re-declansarea breakpoint-ului pe aceeasi linie
    # dupa un CONTINUE (altfel s-ar opri din nou pe acelasi breakpoint)
    skip_break_on_line: int | None = None

    while True:
        with state.condition:
            # verifica daca am ajuns la sfarsitul programului
            if state.current_line >= len(state.lines):
                state.status = ExecutionStatus.FINISHED
                state.condition.notify_all()  # notifica alte threaduri care asteapta
                break

            # decide daca trebuie sa ne oprim pe un breakpoint:
            # 1. linia curenta are breakpoint
            # 2. exista un client atasat (altfel nu are sens sa oprim)
            # 3. nu suntem pe linia de la care tocmai am facut CONTINUE
            should_break = (
                state.current_line in state.breakpoints
                and state.attached_socket is not None
                and state.current_line != skip_break_on_line
            )

            if should_break:
                # trece programul in starea PAUSED
                state.status = ExecutionStatus.PAUSED
                line_no = state.current_line
                client_sock = state.attached_socket
                print(
                    f"[runner] {state.name} PAUSED at line {line_no} "
                    f"(breakpoint)"
                )

                # trimite notificare asincrona clientului ca programul s-a oprit
                try:
                    send_message(client_sock, f"PAUSED {line_no}")
                except OSError:
                    pass  # clientul s-a deconectat, ignoram eroarea

                # asteapta pe Condition pana cand statusul se schimba din PAUSED
                # (clientul trimite CONTINUE care face notify_all)
                while state.status == ExecutionStatus.PAUSED:
                    state.condition.wait()

                # marcheaza linia curenta ca "skip" pentru a nu re-declansa
                # breakpoint-ul imediat dupa CONTINUE
                skip_break_on_line = line_no

                # revenim la inceputul buclei pentru a re-evalua starea
                continue

            # preluam linia de cod de executat (in interiorul lock-ului)
            line = state.lines[state.current_line]
            line_no = state.current_line

        # executam linia de cod (in afara lock-ului pentru a nu bloca alte threaduri)
        try:
            var_name = execute_line(line, state.variables)
            value = state.variables[var_name]
            print(
                f"[runner] {state.name}:{line_no} | {line}  "
                f"=> {var_name} = {value}"
            )
        except Exception as exc:
            # daca apare o eroare la executie, programul se termina
            print(
                f"[runner] {state.name}:{line_no} | {line}  "
                f"=> ERROR: {exc}"
            )
            # marcheaza programul ca FINISHED si notifica
            with state.condition:
                state.status = ExecutionStatus.FINISHED
                state.condition.notify_all()
            _notify_finished(state)  # trimite notificare clientului
            break

        # avanseaza la urmatoarea linie si reseteaza skip-ul de breakpoint
        with state.condition:
            state.current_line += 1
            skip_break_on_line = None  # urmatoarea linie poate avea breakpoint

        # delay intre linii pentru a simula executia pas cu pas
        time.sleep(LINE_DELAY)

    # trimite notificare FINISHED clientului atasat (daca exista)
    _notify_finished(state)
    print(
        f"[runner] Program '{state.name}' finished.  "
        f"variables = {state.variables}"
    )


# trimite notificare de tip FINISHED clientului atasat
def _notify_finished(state: ProgramState) -> None:
    """
    Trimite un mesaj asincron de tip 'FINISHED <program>' catre clientul atasat.
    Aceasta notificare informeaza clientul ca programul a terminat executia.
    Daca nu exista client atasat sau trimiterea esueaza, nu face nimic.
    """
    # obtinem socket-ul clientului sub lock pentru thread-safety
    with state.condition:
        sock = state.attached_socket
    if sock is not None:
        try:
            send_message(sock, f"FINISHED {state.name}")
        except OSError:
            pass  # clientul s-a deconectat, ignoram eroarea


# creeaza si porneste un thread dedicat pentru executia unui program
def start_single_program(state: ProgramState) -> threading.Thread:
    """
    Creeaza un thread daemon dedicat pentru executia unui program
    si il porneste imediat.

    Parametri:
        state: starea programului de executat

    Returneaza:
        Thread-ul creat (deja pornit).

    Thread-ul este daemon, deci se opreste automat cand procesul principal se termina.
    """
    t = threading.Thread(
        target=run_program,   # functia care va rula in thread
        args=(state,),        # argumentele functiei
        name=f"prog-{state.name}",  # nume descriptiv pentru debugging
        daemon=True,          # thread daemon - se opreste cu procesul principal
    )
    t.start()  # porneste executia thread-ului
    print(f"[runner] Thread started for '{state.name}'")
    return t
