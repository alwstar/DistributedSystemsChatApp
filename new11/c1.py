import socket
import threading
import time
import json
import random

# Constants
LEADER_LISTEN_PORT = 5000
CLIENT_LISTEN_PORT = 5001
MESSAGE_SEND_PORT = 5002
MESSAGE_RECEIVE_PORT = 5003
BUFFER_SIZE = 1024
RECONNECT_INTERVAL = 5

# Global variables
client_id = f"CLIENT_{random.randint(1000, 9999)}_{int(time.time())}"
leader_ip = None
leader_socket = None
shutdown_event = threading.Event()
leader_socket_lock = threading.Lock()
listen_thread_stop_event = threading.Event()
listen_thread = None


def locate_leader():
    global leader_ip
    print("Searching for leader...")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        udp_socket.settimeout(1)
        while not shutdown_event.is_set():
            try:
                message = json.dumps({"type": "LEADER_REQUEST", "client_id": client_id}).encode()
                udp_socket.sendto(message, ('<broadcast>', LEADER_LISTEN_PORT))
                response, server_addr = udp_socket.recvfrom(BUFFER_SIZE)
                leader_data = json.loads(response.decode())
                if leader_data.get("type") == "LEADER_RESPONSE":
                    leader_ip = server_addr[0]
                    print(f"Leader found at {leader_ip}")
                    return True
            except socket.timeout:
                print("Leader not found. Retrying...")
            time.sleep(RECONNECT_INTERVAL)
    return False

def connect_to_leader():
    global leader_socket
    if not leader_ip:
        print("Leader IP not set. Cannot connect.")
        return False
    
    try:
        leader_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        leader_socket.connect((leader_ip, CLIENT_LISTEN_PORT))
        message = json.dumps({"type": "CONNECT", "client_id": client_id}).encode()
        leader_socket.send(message)
        response = leader_socket.recv(BUFFER_SIZE).decode()
        if json.loads(response).get("status") == "OK":
            print("Connected to leader successfully.")
            return True
        else:
            print("Failed to connect to leader.")
            return False
    except Exception as e:
        print(f"Error connecting to leader: {e}")
        return False

def send_message(message):
    global leader_socket
    with leader_socket_lock:
        if leader_socket:
            try:
                data = json.dumps({"type": "CHAT", "client_id": client_id, "message": message}).encode()
                leader_socket.send(data)
                print("Nachricht an Server gesendet")
            except Exception as e:
                print(f"Fehler beim Senden der Nachricht: {e}")
                reconnect()
        else:
            print("Keine Verbindung zum Server. Versuche erneut zu verbinden.")
            reconnect()


def receive_messages():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(('', CLIENT_LISTEN_PORT))
            sock.listen()
            print(f"Listening for messages on port {CLIENT_LISTEN_PORT}")
            while not shutdown_event.is_set():
                conn, addr = sock.accept()
                threading.Thread(target=handle_incoming_message, args=(conn,), daemon=True).start()
    except Exception as e:
        print(f"Error in receive_messages: {e}")


def listen_to_server():
    global leader_socket
    print("listen_to_server Thread gestartet.")
    listen_thread_stop_event.clear()
    while not shutdown_event.is_set() and not listen_thread_stop_event.is_set():
        try:
            with leader_socket_lock:
                if leader_socket:
                    # Kopieren Sie den Socket, um Race Conditions zu vermeiden
                    sock = leader_socket
                else:
                    print("Kein gültiger leader_socket vorhanden.")
                    break
            try:
                # Setzen Sie das Timeout außerhalb des Locks
                sock.settimeout(1)
                data = sock.recv(BUFFER_SIZE)
            except socket.timeout:
                continue  # Keine Daten empfangen, Schleife fortsetzen
            except Exception as e:
                print(f"Fehler beim Empfangen von Daten: {e}")
                listen_thread_stop_event.set()
                break
            if data:
                message = json.loads(data.decode())
                print(f"Nachricht vom Server empfangen: {message}")  # Debug-Ausgabe
                message_type = message.get('type')
                if message_type == 'BROADCAST':
                    print(f"\nEmpfangene Nachricht von {message['sender_id']}: {message['message']}")
                    print("Geben Sie eine Nachricht ein (oder 'quit' zum Beenden): ", end='', flush=True)
                elif message_type == 'reconnect':
                    print("Server hat einen Reconnect angefordert.")
                    listen_thread_stop_event.set()
                    # Beenden Sie die Schleife, damit der Thread sauber beendet wird
                    break
                else:
                    print(f"Unbekannter Nachrichtentyp: {message_type}")
            else:
                # Wenn keine Daten empfangen wurden, Verbindung verloren
                print("Verbindung zum Server verloren.")
                listen_thread_stop_event.set()
                break
        except json.JSONDecodeError as e:
            print(f"Fehler beim Dekodieren von JSON: {e}")
        except Exception as e:
            print(f"Fehler beim Empfangen von Nachrichten: {e}")
            listen_thread_stop_event.set()
            break
    print("listen_to_server Thread beendet.")


def handle_incoming_message(conn):
    try:
        with conn:
            while not shutdown_event.is_set():
                data = conn.recv(BUFFER_SIZE)
                if not data:
                    break
                message = json.loads(data.decode())
                if message['type'] == 'BROADCAST':
                    print(f"\nReceived message from {message['sender_id']}: {message['message']}")
                    print("Enter message (or 'quit' to exit): ", end='', flush=True)
    except Exception as e:
        print(f"Error handling incoming message: {e}")

def listen_for_messages():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(('', CLIENT_LISTEN_PORT))
            sock.listen()
            print(f"Listening for messages on port {CLIENT_LISTEN_PORT}")
            while not shutdown_event.is_set():
                conn, addr = sock.accept()
                threading.Thread(target=receive_message, args=(conn,), daemon=True).start()
    except Exception as e:
        print(f"Error in listen_for_messages: {e}")

def reconnect():
    global leader_socket, listen_thread
    print("Versuche, erneut zu verbinden...")
    # Signalisiert dem listen_to_server-Thread, dass er stoppen soll
    listen_thread_stop_event.set()
    # Wartet darauf, dass der listen_to_server-Thread beendet wird
    if listen_thread is not None:
        listen_thread.join()
        listen_thread = None
    # Schließt den alten Socket
    with leader_socket_lock:
        if leader_socket:
            try:
                leader_socket.close()
            except Exception as e:
                print(f"Fehler beim Schließen des Sockets: {e}")
            leader_socket = None
    while not shutdown_event.is_set():
        if locate_leader() and connect_to_leader():
            print("Erneute Verbindung erfolgreich.")
            # Startet den listen_to_server-Thread neu
            listen_thread_stop_event.clear()
            listen_thread = threading.Thread(target=listen_to_server, daemon=True)
            listen_thread.start()
            break
        else:
            time.sleep(RECONNECT_INTERVAL)



def main():
    global listen_thread
    print(f"Client startet mit ID: {client_id}")
    
    if not locate_leader():
        print("Kein Leader gefunden. Beende.")
        return

    if not connect_to_leader():
        print("Verbindung zum Leader fehlgeschlagen. Beende.")
        return

    # Startet den Thread zum Empfangen von Nachrichten vom Server
    listen_thread_stop_event.clear()
    listen_thread = threading.Thread(target=listen_to_server, daemon=True)
    listen_thread.start()

    while not shutdown_event.is_set():
        message = input("Geben Sie eine Nachricht ein (oder 'quit' zum Beenden): ")
        if message.lower() == 'quit':
            shutdown_event.set()
            # Signalisiert dem listen_to_server-Thread, dass er stoppen soll
            listen_thread_stop_event.set()
            break
        send_message(message)

    # Wartet darauf, dass der listen_to_server-Thread beendet wird
    if listen_thread is not None:
        listen_thread.join()

    if leader_socket:
        leader_socket.close()
    print("Client getrennt.")

if __name__ == "__main__":
    main()