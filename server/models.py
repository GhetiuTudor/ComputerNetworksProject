"""
modelul de date pt un program la runtime 
"""

import socket
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Set


class ExecutionStatus(Enum):
    """starile posibile de executie in care se poate afla un program la un moment de timp"""
    READY = "READY" #program incarcat 
    RUNNING = "RUNNING" #program in executie 
    PAUSED = "PAUSED" #program in paza - breakpoint
    FINISHED = "FINISHED" #program rulat complet 


@dataclass
class ProgramState:
    """
    starea unui program la un moment de timp 

   Atribute :
        name:              Friendly name / filename of the program.
        lines:             Source lines loaded from the .txt file.
        variables:         Variable store built up during execution.
        current_line:      0-based index of the line about to execute.
        status:            Current execution status.
        breakpoints:       Set of 0-based line indices where execution
                           should pause.
        attached_client:   Address string of the client currently
                           controlling this program, or None.
        attached_socket:   Socket of the attached client, used by the
                           runner thread to send PAUSED notifications.
        condition:         threading.Condition used for all
                           synchronization on this program's state.
    """

    name: str #filename
    lines: list = field(default_factory=list) #liniile de cod ca lista
    variables: Dict[str, float] = field(default_factory=dict) #runtime memory context 
    current_line: int = 0 
    status: ExecutionStatus = ExecutionStatus.READY
    breakpoints: Set[int] = field(default_factory=set) #set de linii cu breakpoint-uri - complexitate O(1)
    attached_client: Optional[str] = None #clientul ip:port
    attached_socket: Optional[socket.socket] = None #socketul clientului pt notificari 
    condition: threading.Condition = field(
        default_factory=lambda: threading.Condition(threading.Lock()))

        #functii helper 

    def is_finished(self) -> bool:
        """returneaza True cand nu mai sunt linii de executat"""
        return self.current_line >= len(self.lines)

    def reset(self) -> None:
        """reseteaza programul la starea READY"""
        self.variables.clear()
        self.current_line = 0
        self.status = ExecutionStatus.READY

    def __repr__(self) -> str:
        return (
            f"ProgramState(name={self.name!r}, "
            f"line={self.current_line}/{len(self.lines)}, "
            f"status={self.status.value})"
        )
