"""
clientul interactiv - se conecteza la server prin TCP 
"""

import socket
import sys


SERVER_HOST = "localhost"   
SERVER_PORT = 9000

ENCODING = "utf-8"
BUFFER_SIZE = 4096


def send_message(sock: socket.socket, message: str) -> None:
    """
    """
    sock.sendall((message + "\n").encode(ENCODING))


def receive_message(sock: socket.socket) -> str | None:
    """
    """
    data = b""
    while True:
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


def main() -> None:
    host = SERVER_HOST
    port = SERVER_PORT

    
    if len(sys.argv) >= 2:
        host = sys.argv[1]
    if len(sys.argv) >= 3:
        port = int(sys.argv[2])

    print(f"[client] Connecting to {host}:{port} ...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
    except ConnectionRefusedError:
        print("[client] Connection refused. Is the server running?")
        sys.exit(1)

    welcome = receive_message(sock)
    if welcome:
        print(welcome)
    try:
        while True:
            try:
                cmd = input("dbg> ").strip()
            except EOFError:
                cmd = "QUIT"

            if not cmd:
                continue

            send_message(sock, cmd)

            response = receive_message(sock)
            if response is None:
                print("[client] Server closed the connection.")
                break

            print(response)

            if cmd.upper() == "QUIT":
                break

    except KeyboardInterrupt:
        print("\n[client] Interrupted.")
    finally:
        sock.close()
        print("[client] Disconnected.")


if __name__ == "__main__":
    main()
