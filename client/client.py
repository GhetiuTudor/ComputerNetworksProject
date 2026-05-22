"""
clientul interactiv - se conecteaza la server prin TCP
trimite comenzi introduse de utilizator si afiseaza raspunsurile primite

Foloseste doua threaduri:
  - thread-ul principal: citeste comenzi de la tastatura si le trimite
  - thread-ul reader: citeste continuu mesaje de la server si le afiseaza

Aceasta arhitectura rezolva problema notificarilor asincrone (PAUSED, FINISHED)
care pot veni in orice moment, nu doar ca raspuns la o comanda.
"""

import socket
import sys
import threading
import time


SERVER_HOST = "localhost"   # adresa implicita a serverului
SERVER_PORT = 9000          # portul implicit pe care asculta serverul

ENCODING = "utf-8"          # codificarea folosita pentru mesaje
BUFFER_SIZE = 4096          # dimensiunea maxima a unui chunk citit din socket

# event folosit pentru a semnaliza thread-ului reader sa se opreasca
stop_event = threading.Event()


# trimite un mesaj catre server, adaugand delimitatorul newline
def send_message(sock: socket.socket, message: str) -> None:
    """
    Trimite un mesaj prin socket catre server.
    Adauga un caracter newline la sfarsit deoarece protocolul
    foloseste newline ca delimitator intre mesaje.
    """
    # encode transforma stringul in bytes, sendall garanteaza trimiterea completa
    sock.sendall((message + "\n").encode(ENCODING))


# thread-ul de citire – ruleaza in background si printeaza tot ce vine de la server
def reader_thread(sock: socket.socket) -> None:
    """
    Thread dedicat citirii mesajelor de la server.

    Citeste continuu din socket si afiseaza fiecare mesaj pe ecran.
    Aceasta abordare permite:
    - primirea notificarilor asincrone (PAUSED, FINISHED) in orice moment
    - afisarea corecta a raspunsurilor multi-linie (LIST, HELP)
    - evitarea problemei de 'raspunsuri decalate' din modelul sincron

    Thread-ul se opreste cand socketul este inchis sau stop_event este setat.
    """
    buf = b""  # buffer de bytes pentru acumularea datelor primite fragmentat
    while not stop_event.is_set():
        try:
            chunk = sock.recv(BUFFER_SIZE)  # citeste un bloc de date din socket
        except (ConnectionResetError, OSError):
            # eroare de conexiune – socketul a fost inchis sau resetat
            if not stop_event.is_set():
                print("\n[client] Server closed the connection.")
            break
        if not chunk:
            # recv() returneaza bytes gol = conexiune inchisa de server
            if not stop_event.is_set():
                print("\n[client] Server closed the connection.")
            break

        buf += chunk  # adauga chunk-ul la buffer

        # proceseaza toate mesajele complete din buffer
        # fiecare mesaj e terminat cu newline (\n)
        # pot exista mai multe mesaje in acelasi chunk (ex: LIST cu 3 programe)
        while b"\n" in buf:
            # split(maxsplit=1) separa primul mesaj de restul buffer-ului
            line, buf = buf.split(b"\n", 1)
            msg = line.decode(ENCODING).rstrip()  # decodifica si elimina whitespace
            if msg:
                print(msg)  # afiseaza mesajul primit


# functia principala - creeaza conexiunea si ruleaza bucla de comenzi
def main() -> None:
    """
    Punctul de intrare al clientului.

    1. Se conecteaza la server prin TCP
    2. Porneste thread-ul reader in background (citeste si afiseaza raspunsuri)
    3. Intra in bucla principala unde citeste comenzi de la tastatura si le trimite
    4. La QUIT sau Ctrl+C, inchide conexiunea
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

    # porneste thread-ul reader in background
    # daemon=True: thread-ul se opreste automat cand procesul principal se termina
    t = threading.Thread(target=reader_thread, args=(sock,), daemon=True)
    t.start()

    # asteapta putin pentru a primi si afisa mesajul WELCOME inainte de prompt
    time.sleep(0.2)

    try:
        while True:  # bucla principala de citire comenzi
            try:
                cmd = input("dbg> ").strip()  # citeste comanda de la utilizator
            except EOFError:
                cmd = "QUIT"  # Ctrl+D trimite QUIT automat

            if not cmd:
                continue  # ignora liniile goale

            send_message(sock, cmd)  # trimite comanda la server
            # raspunsul va fi citit si afisat automat de reader_thread

            # asteapta putin pentru ca reader_thread sa primeasca si afiseze
            # raspunsul inainte ca input() sa afiseze un nou prompt "dbg>"
            time.sleep(0.15)

            if cmd.upper() == "QUIT":
                time.sleep(0.3)  # asteapta putin sa primeasca raspunsul BYE
                break

    except KeyboardInterrupt:
        print("\n[client] Interrupted.")  # Ctrl+C
    finally:
        stop_event.set()  # semnalizeaza reader_thread sa se opreasca
        sock.close()      # inchidem socketul
        print("[client] Disconnected.")


if __name__ == "__main__":
    main()
