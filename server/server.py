"""
server.py – punctul de intrare al serverului TCP

Porneste un server TCP care asculta pe portul 5000 (in container).
Fiecare client care se conecteaza primeste un thread dedicat
care ii proceseaza comenzile prin handle_client().
"""

import socket
import threading

from program_runner import load_programs
from client_handler import handle_client

HOST = "0.0.0.0"  # asculta pe toate interfetele de retea (necesar in Docker)
PORT = 8524        # portul pe care asculta serverul (portul universitar alocat)


# functia principala - porneste serverul si gestioneaza conexiunile
def main() -> None:
    """
    Punctul de intrare al serverului.

    1. Incarca programele din folderul programs/
    2. Creeaza socket-ul TCP si incepe sa asculte
    3. Accepta clienti si creeaza cate un thread daemon pentru fiecare
    4. La Ctrl+C, inchide socket-ul serverului si iese
       (thread-urile daemon se opresc automat, iar client_handler.py
        face auto-resume pentru programe blocate pe breakpoint)
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

    try:
        while True:  # bucla principala de acceptare clienti
            try:
                # accept() blocheaza max 1 secunda (din cauza settimeout)
                client_sock, client_addr = server_sock.accept()
            except socket.timeout:
                continue  # timeout expirat, revenim la accept() (verifica si Ctrl+C)
            # creeaza un thread daemon pentru noul client
            # daemon=True inseamna ca thread-ul se opreste automat la iesirea procesului
            t = threading.Thread(
                target=handle_client,
                args=(client_sock, client_addr, programs),
                daemon=True,
            )
            t.start()
    except KeyboardInterrupt:
        print("\n[server] Shutting down...")
    finally:
        # inchide socket-ul serverului (nu mai accepta clienti noi)
        server_sock.close()
        print("[server] Bye.")


if __name__ == "__main__":
    main()
