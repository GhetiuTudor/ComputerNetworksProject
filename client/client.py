"""
clientul interactiv - se conecteaza la server prin TCP
trimite comenzi introduse de utilizator si afiseaza raspunsurile primite

Foloseste select() pentru a multiplexa intre socket si stdin
intr-un singur thread, fara a avea nevoie de threading.
select() asteapta pana cand fie serverul trimite date,
fie utilizatorul introduce o comanda – oricare vine prima.
"""

import socket
import sys
import select


SERVER_HOST = "localhost"   # adresa implicita a serverului
SERVER_PORT = 8524          # portul pe care asculta serverul (portul universitar alocat)

ENCODING = "utf-8"          # codificarea folosita pentru mesaje
BUFFER_SIZE = 4096          # dimensiunea maxima a unui chunk citit din socket


# trimite un mesaj catre server, adaugand delimitatorul newline
def send_message(sock: socket.socket, message: str) -> None:
    """
    Trimite un mesaj prin socket catre server.
    Adauga un caracter newline la sfarsit deoarece protocolul
    foloseste newline ca delimitator intre mesaje.
    """
    # encode transforma stringul in bytes, sendall garanteaza trimiterea completa
    sock.sendall((message + "\n").encode(ENCODING))


# functia principala - creeaza conexiunea si ruleaza bucla de comenzi
def main() -> None:
    """
    Punctul de intrare al clientului.

    Foloseste select() pentru a multiplexa intre doua surse de date:
    1. socket-ul TCP (raspunsuri si notificari de la server)
    2. stdin (comenzi de la tastatura)

    select() blocheaza pana cand cel putin una din surse are date disponibile,
    apoi le procesam pe rand. Aceasta abordare:
    - nu necesita threading
    - primeste notificarile asincrone (PAUSED, FINISHED) imediat
    - afiseaza raspunsurile in ordinea corecta
    """
    host = SERVER_HOST
    port = SERVER_PORT

    # permite suprascrierea host-ului si portului din linia de comanda
    if len(sys.argv) >= 2:
        host = sys.argv[1]
    if len(sys.argv) >= 3:
        port = int(sys.argv[2])

    print(f"[client] Connecting to {host}:{port} ...")
    try:
        # creeaza un socket TCP (AF_INET = IPv4, SOCK_STREAM = TCP)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))  # stabileste conexiunea cu serverul
    except ConnectionRefusedError:
        print("[client] Connection refused. Is the server running?")
        sys.exit(1)

    print("[client] Connected. Waiting for server...")

    running = True  # flag pentru bucla principala

    try:
        while running:
            # select() asteapta pana cand socket-ul SAU stdin au date disponibile
            # primul argument = lista de file descriptors de monitorizat pentru citire
            # returneaza lista celor care au date gata de citit
            readable, _, _ = select.select([sock, sys.stdin], [], [])

            for source in readable:
                if source is sock:
                    # --- date de la server ---
                    try:
                        data = sock.recv(BUFFER_SIZE)
                    except (ConnectionResetError, OSError):
                        print("\n[client] Connection lost.")
                        running = False
                        break

                    if not data:
                        # recv() returneaza bytes gol = serverul a inchis conexiunea
                        print("\n[client] Server closed the connection.")
                        running = False
                        break

                    # decodifica si afiseaza fiecare linie primita
                    # pot veni mai multe mesaje in acelasi recv() (ex: LIST cu 3 programe)
                    text = data.decode(ENCODING).strip()
                    if text:
                        print(text)
                        # re-afiseaza promptul dupa mesajele serverului
                        print("dbg> ", end="", flush=True)

                elif source is sys.stdin:
                    # --- comanda de la utilizator ---
                    cmd = sys.stdin.readline().strip()

                    if not cmd:
                        # linie goala - re-afiseaza promptul
                        print("dbg> ", end="", flush=True)
                        continue

                    send_message(sock, cmd)  # trimite comanda la server

                    if cmd.upper() == "QUIT":
                        running = False
                        break

    except KeyboardInterrupt:
        print("\n[client] Interrupted.")  # Ctrl+C
    finally:
        sock.close()  # inchidem socketul indiferent de motiv
        print("[client] Disconnected.")


if __name__ == "__main__":
    # afiseaza promptul initial
    print("dbg> ", end="", flush=True)
    main()
