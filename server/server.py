"""
"""

import socket
import sys
import threading

from models import ProgramState, ExecutionStatus
from program_runner import load_programs
from client_handler import handle_client

HOST = "0.0.0.0"
PORT = 5000


def main() -> None:
    
    programs = load_programs()
    if not programs:
        print("[server] No programs found — the server will still accept clients.")
    else:
        print(f"[server] Loaded {len(programs)} program(s) in READY state.")

   
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen()
    
    server_sock.settimeout(1.0)
    print(f"[server] Listening on {HOST}:{PORT}")


    client_sockets: list[socket.socket] = []
    client_sockets_lock = threading.Lock()

    def _handle_and_track(csock, caddr, progs):
        """Wrapper that registers/unregisters the client socket."""
        with client_sockets_lock:
            client_sockets.append(csock)
        try:
            handle_client(csock, caddr, progs)
        finally:
            with client_sockets_lock:
                try:
                    client_sockets.remove(csock)
                except ValueError:
                    pass

    try:
        while True:
            try:
                client_sock, client_addr = server_sock.accept()
            except socket.timeout:
                continue 
            t = threading.Thread(
                target=_handle_and_track,
                args=(client_sock, client_addr, programs),
                name=f"client-{client_addr[0]}:{client_addr[1]}",
                daemon=True,
            )
            t.start()
    except KeyboardInterrupt:
        print("\n[server] Shutting down gracefully...")
    finally:
       
        server_sock.close()

        with client_sockets_lock:
            for csock in client_sockets:
                try:
                    csock.close()
                except OSError:
                    pass
            client_sockets.clear()

        for name, state in programs.items():
            with state.condition:
                if state.status == ExecutionStatus.PAUSED:
                    state.status = ExecutionStatus.RUNNING
                    state.condition.notify_all()
                    print(f"[server] Auto-resumed {name} for shutdown")

        print("[server] Bye.")


if __name__ == "__main__":
    main()

