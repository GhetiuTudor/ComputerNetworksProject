"""
modelul de date pt un program la runtime

Defineste structura de date care retine starea completa a unui program
in timpul executiei: variabile, linia curenta, breakpoint-uri, clientul atasat etc.
"""

import socket
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Set


# enum care defineste toate starile posibile ale unui program
class ExecutionStatus(Enum):
    """
    Starile posibile de executie in care se poate afla un program
    la un moment de timp. Tranzitiile valide sunt:
    READY -> RUNNING -> FINISHED
    RUNNING <-> PAUSED (prin breakpoint / continue)
    """
    READY = "READY"       # program incarcat, gata de pornire
    RUNNING = "RUNNING"   # program in executie activa
    PAUSED = "PAUSED"     # program oprit temporar pe un breakpoint
    FINISHED = "FINISHED" # program care a terminat executia tuturor liniilor


# dataclass care retine intreaga stare a unui program la runtime
@dataclass
class ProgramState:
    """
    Starea completa a unui program la un moment de timp.

    Acest obiect este partajat intre thread-ul runner (care executa programul)
    si thread-urile handler (cate unul per client conectat). Sincronizarea
    se face prin campul 'condition' (threading.Condition).

    Atribute:
        name:              Numele fisierului programului (.txt).
        lines:             Lista de linii de cod incarcate din fisier.
        variables:         Dictionarul de variabile construite in timpul executiei.
        current_line:      Indexul (0-based) al liniei care urmeaza sa fie executata.
        status:            Starea curenta de executie (READY/RUNNING/PAUSED/FINISHED).
        breakpoints:       Set de indici de linii (0-based) unde executia se opreste.
        attached_client:   Adresa (ip:port) a clientului care controleaza programul, sau None.
        attached_socket:   Socket-ul clientului atasat, folosit de runner pentru
                           notificari asincrone (PAUSED, FINISHED).
        condition:         Obiect threading.Condition folosit pentru toata
                           sincronizarea pe starea acestui program.
    """

    name: str                                              # numele fisierului (ex: prog1.txt)
    lines: list = field(default_factory=list)               # liniile de cod ca lista de stringuri
    variables: Dict[str, float] = field(default_factory=dict)  # contextul de memorie la runtime (variabile)
    current_line: int = 0                                  # indexul liniei curente (0-based)
    status: ExecutionStatus = ExecutionStatus.READY         # starea initiala este READY
    breakpoints: Set[int] = field(default_factory=set)      # set de linii cu breakpoint-uri (cautare O(1))
    attached_client: Optional[str] = None                  # clientul atasat ca string "ip:port"
    attached_socket: Optional[socket.socket] = None        # socket-ul clientului pentru notificari asincrone
    # field cu default_factory creeaza un obiect Condition nou pentru fiecare instanta
    # (altfel toate instantele ar imparti acelasi obiect - bug de partajare)
    # Condition wrapeaza un Lock si permite wait/notify pentru sincronizare intre threaduri
    condition: threading.Condition = field(
        default_factory=lambda: threading.Condition(threading.Lock()))

    # --- functii helper ---

    # verifica daca programul a terminat executia tuturor liniilor
    def is_finished(self) -> bool:
        """Returneaza True cand nu mai sunt linii de executat."""
        return self.current_line >= len(self.lines)

    # reseteaza programul la starea initiala pentru re-executie
    def reset(self) -> None:
        """
        Reseteaza programul la starea READY.
        Goleste variabilele, pune linia curenta pe 0 si schimba statusul.
        """
        self.variables.clear()   # sterge toate variabilele acumulate
        self.current_line = 0    # revine la prima linie
        self.status = ExecutionStatus.READY  # marcheaza ca gata de pornire

    # reprezentarea text a starii programului (util pentru debugging/logging)
    def __repr__(self) -> str:
        """Returneaza o reprezentare text concisa a starii programului."""
        return (
            f"ProgramState(name={self.name!r}, "
            f"line={self.current_line}/{len(self.lines)}, "
            f"status={self.status.value})"
        )
