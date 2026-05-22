"""
server.py – punctul de intrare al serverului TCP

Porneste un server TCP care asculta pe portul 5000 (in container).
Fiecare client care se conecteaza primeste un thread dedicat
care ii proceseaza comenzile prin handle_client().
La shutdown, inchide toate conexiunile si reia programele oprite pe breakpoint.
"""

import socket
import sys
import threading

from models import ProgramState, ExecutionStatus
from program_runner import load_programs
from client_handler import handle_client

HOST = "0.0.0.0"  # asculta pe toate interfetele de retea (necesar in Docker)
PORT = 5000        # portul intern al containerului (mapat la 9000 pe host)


# functia principala - porneste serverul si gestioneaza conexiunile
def main() -> None:
    """
    Punctul de intrare al serverului.

    1. Incarca programele din folderul programs/
    2. Creeaza socket-ul TCP si incepe sa asculte
    3. Accepta clienti si creeaza cate un thread pentru fiecare
    4. La Ctrl+C, face shutdown graceful (inchide conexiuni, reia programe blocate)
    """

    # incarca toate programele din folderul server/programs/
    programs = load_programs()
    if not programs:
        print("[server] No programs found — the server will still accept clients.")
    else:
        print(f"[server] Loaded {len(programs)} program(s) in READY state.")

    # creeaza socket-ul TCP al serverului
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # SO_REUSEADDR permite reutilizarea portului imediat dupa oprirea serverului
    # (altfel portul ramane blocat cateva minute in starea TIME_WAIT)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))  # asociaza socket-ul cu adresa si portul
    server_sock.listen()            # marcheaza socket-ul ca ascultator (pasiv)

    # timeout de 1 secunda pe accept() pentru a permite verificarea KeyboardInterrupt
    # fara timeout, accept() blocheaza indefinit si Ctrl+C nu ar functiona corect
    server_sock.settimeout(1.0)
    print(f"[server] Listening on {HOST}:{PORT}")

    # lista de socket-uri client active, protejata de un lock
    # necesara pentru a inchide toate conexiunile la shutdown
    client_sockets: list[socket.socket] = []
    client_sockets_lock = threading.Lock()

    # wrapper care inregistreaza/dezinregistreaza socket-ul clientului
    def _handle_and_track(csock, caddr, progs):
        """
        Inregistreaza socket-ul clientului in lista, apeleaza handler-ul,
        si il scoate din lista la deconectare. Aceasta permite shutdown-ului
        sa inchida toate conexiunile active.
        """
        # adauga socket-ul in lista (sub lock pentru thread-safety)
        with client_sockets_lock:
            client_sockets.append(csock)
        try:
            handle_client(csock, caddr, progs)  # proceseaza comenzile clientului
        finally:
            # scoate socket-ul din lista la deconectare
            with client_sockets_lock:
                try:
                    client_sockets.remove(csock)
                except ValueError:
                    pass  # socket-ul a fost deja scos (ex: de shutdown)

    try:
        while True:  # bucla principala de acceptare clienti
            try:
                # accept() blocheaza max 1 secunda (din cauza settimeout)
                client_sock, client_addr = server_sock.accept()
            except socket.timeout:
                continue  # timeout expirat, revenim la accept() (verifica si Ctrl+C)
            # creeaza un thread daemon pentru noul client
            t = threading.Thread(
                target=_handle_and_track,
                args=(client_sock, client_addr, programs),
                name=f"client-{client_addr[0]}:{client_addr[1]}",  # nume descriptiv
                daemon=True,  # thread daemon - nu blocheaza iesirea procesului
            )
            t.start()
    except KeyboardInterrupt:
        print("\n[server] Shutting down gracefully...")
    finally:
        # --- shutdown graceful ---

        # 1. inchide socket-ul serverului (nu mai accepta clienti noi)
        server_sock.close()

        # 2. inchide toate socket-urile clientilor activi
        with client_sockets_lock:
            for csock in client_sockets:
                try:
                    csock.close()
                except OSError:
                    pass  # ignora erori la inchidere (socket deja inchis)
            client_sockets.clear()

        # 3. reia programele care sunt blocate in starea PAUSED
        # (altfel thread-urile runner ar ramane blocate pe Condition.wait() la infinit)
        for name, state in programs.items():
            with state.condition:
                if state.status == ExecutionStatus.PAUSED:
                    state.status = ExecutionStatus.RUNNING
                    state.condition.notify_all()  # deblocheaza thread-ul runner
                    print(f"[server] Auto-resumed {name} for shutdown")

        print("[server] Bye.")


if __name__ == "__main__":
    main()
