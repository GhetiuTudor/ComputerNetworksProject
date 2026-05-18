"""
protocol.py – protocol de comunicare palin text

Toate mesajele sunt stringuri UTF-8 terminate printr-un caracter newline.
Acest modul a fost creat pt utilitare ca sa ne asiguram socketurile nu sunt atinse direct 
"""

import socket
 
ENCODING = "utf-8" #socketurile trimit bytes 
BUFFER_SIZE = 4096


def send_message(sock: socket.socket, message: str) -> None:
    """adauga new line inainte de trimitere pt ca TCP e stream based si are nevoie de delimitator"""
    data = (message + "\n").encode(ENCODING)
    sock.sendall(data) #garanteaza ca e trimis tot mesajul


def receive_message(sock: socket.socket) -> str | None:
    """
    Primeste un mesaj si il returneaza. Daca socketul e inchis de remote returneaza None 
    """
    data = b"" #byte buffer
    while True:  #pt ca TCP e stream e posibil ca mesajul sa vina in multe pachete 
        try:
            chunk = sock.recv(BUFFER_SIZE)
        except (ConnectionResetError, OSError):
            return None
        if not chunk:
            return None
        data += chunk
        if b"\n" in data:
            break
    return data.decode(ENCODING).strip()


#comenzi universale 

CMD_LIST = "LIST"           # listeaza programele 
CMD_STATUS = "STATUS"       # statutul unui program 
CMD_ATTACH = "ATTACH"       # atasare debugger pt un program 
CMD_DETACH = "DETACH"       # detasare de la debugger 
CMD_QUIT = "QUIT"           # deconectare 
CMD_BREAK = "BREAK"         # breakpoint la linia specificata
CMD_UNBREAK = "UNBREAK"     # scoate breakpoint 
CMD_CONTINUE = "CONTINUE"   # continua executia 
CMD_PRINT = "PRINT"         # afiseaza valoarea unei variabile 
CMD_SET = "SET"             # modifica valoarea unei variabile
CMD_RUN = "RUN"             # porneste programul

RESP_OK = "OK"
RESP_ERROR = "ERROR"
