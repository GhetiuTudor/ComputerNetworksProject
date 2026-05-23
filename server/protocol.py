"""
protocol.py – protocol de comunicare plain text

Toate mesajele sunt stringuri UTF-8 terminate printr-un caracter newline.
Acest modul a fost creat ca utilitar pentru a ne asigura ca socketurile
nu sunt atinse direct din alte module - orice comunicare trece prin
functiile send_message si receive_message.
"""

import socket

ENCODING = "utf-8"   # socketurile trimit bytes, deci folosim UTF-8 pt conversie
BUFFER_SIZE = 4096   # dimensiunea maxima a unui chunk citit dintr-un recv()


# trimite un mesaj complet prin socket, cu delimitator newline
def send_message(sock: socket.socket, message: str) -> None:
    """
    Trimite un mesaj prin socket, adaugand newline ca delimitator.
    TCP este stream-based si are nevoie de un delimitator ca receptorul
    sa stie unde se termina un mesaj. Folosim sendall() care garanteaza
    ca intregul mesaj este trimis (spre deosebire de send() care poate
    trimite partial).
    """
    data = (message + "\n").encode(ENCODING)  # converteste string -> bytes + delimitator
    sock.sendall(data)  # garanteaza ca tot mesajul e trimis complet


# primeste un mesaj complet din socket, citind pana la newline
def receive_message(sock: socket.socket) -> str | None:
    """
    Primeste un mesaj complet din socket si il returneaza ca string.
    Daca socketul este inchis de cealalta parte, returneaza None.

    Deoarece TCP este stream-based, este posibil ca mesajul sa vina
    fragmentat in mai multe pachete - citim in bucla pana gasim
    delimitatorul newline.
    """
    data = b""  # buffer de bytes pentru acumularea datelor primite
    while True:  # citim in bucla deoarece TCP poate fragmenta mesajele
        try:
            chunk = sock.recv(BUFFER_SIZE)  # citeste un bloc de date
        except (ConnectionResetError, OSError):
            return None  # eroare de conexiune - socketul a fost resetat
        if not chunk:
            return None  # recv() returneaza bytes gol = conexiune inchisa
        data += chunk  # adauga chunk-ul la buffer
        if b"\n" in data:  # am gasit delimitatorul - mesajul e complet
            break
    return data.decode(ENCODING).strip()  # decodifica bytes -> string si elimina whitespace
