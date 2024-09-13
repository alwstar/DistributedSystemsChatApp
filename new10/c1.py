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

def locate_leader():
    global leader_ip
    print("Searching for leader...")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        udp_socket.settimeout(1)
        attempt = 0
        max_attempts = 5
        while attempt < max_attempts and not shutdown_event.is_set():
            try:
                message = json.dumps({"type": "LEADER_REQUEST", "client_id": client_id}).encode()
                udp_socket.sendto(message, ('<broadcast>', LEADER_LISTEN_PORT))
                response, server_addr = udp_socket.recvfrom(BUFFER_SIZE)
                leader_data = json.loads(response.decode())
                # Check if election is complete
                if leader_data.get("type") == "LEADER_RESPONSE" and leader_data.get("election_complete", False):
                    leader_ip = server_addr[0]
                    print(f"Leader found at {leader_ip}")
                    return True
                else:
                    print("Leader election not complete yet.")
            except socket.timeout:
                print(f"Leader not found. Attempt {attempt + 1}/{max_attempts}")
                attempt += 1
            time.sleep(RECONNECT_INTERVAL)
    leader_ip = None
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
    try:
        data = json.dumps({"type": "CHAT", "client_id": client_id, "message": message}).encode()
        leader_socket.send(data)
        print("Message sent to server")
    except Exception as e:
        print(f"Error sending message: {e}")
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
    while not shutdown_event.is_set():
        try:
            leader_socket.settimeout(1)  # Set a timeout of 1 second
            data = leader_socket.recv(BUFFER_SIZE)
            if data:
                message = json.loads(data.decode())
                if message['type'] == 'BROADCAST':
                    print(f"\nEmpfangene Nachricht von {message['sender_id']}: {message['message']}")
                    print("Geben Sie eine Nachricht ein (oder 'quit' zum Beenden): ", end='', flush=True)
        except socket.timeout:
            continue  # If no data received, continue the loop
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
        except KeyError as e:
            print(f"Missing key in message: {e}")
        except Exception as e:
            print(f"Fehler beim Empfangen von Nachrichten: {e}")
            reconnect()
            break


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
                threading.Thread(target=receive_messages, args=(conn,), daemon=True).start()
    except Exception as e:
        print(f"Error in listen_for_messages: {e}")

def reconnect():
    global leader_ip, leader_socket
    while not shutdown_event.is_set():
        print("Attempting to reconnect...")
        if locate_leader():
            if connect_to_leader():
                print("Reconnected to new leader.")
                return True
        print("Leader not found or connection failed. Retrying...")
        time.sleep(RECONNECT_INTERVAL)
    return False

def main():
    print(f"Client starting with ID: {client_id}")
    
    if not locate_leader():
        print("No leader found. Exiting.")
        return

    if not connect_to_leader():
        print("Failed to connect to leader. Exiting.")
        return

    server_listen_thread = threading.Thread(target=listen_to_server, daemon=True)
    server_listen_thread.start()

    while not shutdown_event.is_set():
        message = input("Enter message (or 'quit' to exit): ")
        if message.lower() == 'quit':
            shutdown_event.set()
            break
        send_message(message)

    if leader_socket:
        leader_socket.close()
    print("Client disconnected.")

if __name__ == "__main__":
    main()