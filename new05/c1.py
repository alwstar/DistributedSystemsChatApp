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
client_id = f"CLIENT_{random.randint(1000, 9999)}"
leader_ip = None
leader_socket = None
shutdown_event = threading.Event()

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
    try:
        data = json.dumps({"type": "CHAT", "client_id": client_id, "message": message}).encode()
        leader_socket.send(data)
        response = leader_socket.recv(BUFFER_SIZE).decode()
        print(f"Server response: {json.loads(response)['status']}")
    except Exception as e:
        print(f"Error sending message: {e}")
        reconnect()

def receive_messages():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('', MESSAGE_RECEIVE_PORT))
        sock.listen(1)
        print(f"Listening for messages on port {MESSAGE_RECEIVE_PORT}")
        while not shutdown_event.is_set():
            try:
                conn, addr = sock.accept()
                with conn:
                    data = conn.recv(BUFFER_SIZE)
                    if data:
                        message = json.loads(data.decode())
                        print(f"{message['sender_id']}: {message['content']}")
            except Exception as e:
                print(f"Error receiving message: {e}")

def reconnect():
    global leader_socket
    while not shutdown_event.is_set():
        print("Attempting to reconnect...")
        if locate_leader() and connect_to_leader():
            break
        time.sleep(RECONNECT_INTERVAL)

def main():
    print(f"Client starting with ID: {client_id}")
    
    if not locate_leader():
        print("Failed to locate a leader. Exiting.")
        return

    if not connect_to_leader():
        print("Failed to connect to the leader. Exiting.")
        return

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