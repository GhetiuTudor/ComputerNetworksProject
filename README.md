# Proiect #16 – Depanarea Programelor la Distanta

Sistem distribuit de depanare (debugging) la distanta pentru un limbaj simplificat de instructiuni aritmetice. Serverul ruleaza in Docker, clientul se conecteaza prin TCP.

## Structura

```
ProjectComputerNetworks/
├── server/
│   ├── server.py            # Punct de intrare – listener TCP pe portul 8524
│   ├── models.py            # ProgramState (variabile, breakpoints, stare, Condition lock)
│   ├── protocol.py          # send_message / receive_message (newline-delimited)
│   ├── program_runner.py    # Executa programe linie cu linie in threaduri dedicate
│   ├── client_handler.py    # Proceseaza comenzile primite de la clienti
│   └── programs/            # Programe aritmetice (.txt)
│       ├── prog1.txt
│       ├── prog2.txt
│       └── prog3.txt
├── client/
│   └── client.py            # Client interactiv (select pentru multiplexare I/O)
├── Dockerfile
└── docker-compose.yml
```

## Pornire

**Server** (in Docker):
```bash
docker compose up --build
```

**Client**:
```bash
python3 client/client.py localhost        # local
python3 client/client.py <IP_SERVER>      # remote
```

## Functionalitati

### Comenzi

| Comanda | Descriere |
|---------|-----------|
| `LIST` | Listeaza toate programele si starile lor |
| `STATUS <program>` | Informatii detaliate (stare, variabile, breakpoints) |
| `ATTACH <program>` | Ataseaza la un program pentru depanare |
| `DETACH` | Detaseaza de la programul curent |
| `RUN <program>` | Porneste executia (doar din starea READY) |
| `BREAK <program> <linie>` | Seteaza un breakpoint (in READY sau PAUSED) |
| `UNBREAK <program> <linie>` | Sterge un breakpoint |
| `CONTINUE` | Reia executia dupa breakpoint |
| `PRINT <variabila>` | Afiseaza valoarea unei variabile (in PAUSED) |
| `SET <variabila> <valoare>` | Modifica o variabila (in PAUSED) |
| `HELP` | Afiseaza lista de comenzi |
| `QUIT` | Deconectare |

### Starile unui program

```
READY ──RUN──► RUNNING ──breakpoint──► PAUSED ──CONTINUE──► RUNNING
                  │                                             │
                  └─────────── all lines executed ──► FINISHED ◄┘
```

### Flux de lucru

```
ATTACH prog3.txt          # ataseaza la program
BREAK prog3.txt 3         # seteaza breakpoint la linia 3
RUN prog3.txt             # porneste executia
                          # ... serverul trimite: PAUSED 3
PRINT x                   # inspectare variabila
SET x 100                 # modificare variabila
CONTINUE                  # reia executia
                          # ... serverul trimite: FINISHED prog3.txt
```

### Limbajul programelor

Instructiuni de forma `variabila = expresie` cu variabile, constante, operatori (`+`, `-`, `*`, `/`) si paranteze:

```
x = 1
y = 2
z = (x + y) * 10
```

## Arhitectura

- **1 thread per client** – fiecare client conectat primeste un thread dedicat
- **1 thread per program** – fiecare program pornit ruleaza in propriul thread
- **Sincronizare** – `threading.Condition` pe fiecare `ProgramState` (wait/notify pentru pauza/reluare)
- **Protocol** – mesaje UTF-8 delimitate cu newline, trimise prin TCP
- **Un singur client per program** – al doilea client care incearca ATTACH primeste eroare
- **Auto-resume la deconectare** – daca clientul se deconecteaza cat programul e oprit pe breakpoint, serverul reia executia automat

## Tehnologii

- Python 3.11 (fara dependente externe)
- `socket` + `threading` (server)
- `select` (client – multiplexare stdin + socket)
- Docker + Docker Compose
