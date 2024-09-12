import socket
import threading
import time
import json
import random
import sys

# Constants
SERVER_DISCOVERY_PORT = 5000
CLIENT_BASE_PORT = 8001
BUFFER_SIZE = 1024
RECONNECT_INTERVAL = 5

# Global variables
client_id = f"CLIENT_{random.randint(1000, 9999)}"
client_port = None
server_ip = None
server_port = None
shutdown_event = threading.Event()
connected_event = threading.Event()

def create_json_message(message_type, **kwargs):
    return json.dumps({"type": message_type, **kwargs}).encode()

def parse_json_message(json_string):
    data = json.loads(json_string)
    return data.pop("type"), data

def find_available_port(start_port):
    port = start_port
    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', port))
                return port
        except OSError:
            port += 1

def locate_server():
    global server_ip, server_port
    print("Searching for server...")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        udp_socket.settimeout(1)
        attempts = 0
        while not shutdown_event.is_set() and attempts < 10:
            try:
                message = create_json_message("CLIENT_DISCOVERY", client_id=client_id, client_port=client_port)
                udp_socket.sendto(message, ('<broadcast>', SERVER_DISCOVERY_PORT))
                response, server_addr = udp_socket.recvfrom(BUFFER_SIZE)
                server_data = json.loads(response.decode())
                if server_data.get("type") == "SERVER_RESPONSE":
                    server_ip = server_addr[0]
                    server_port = server_data["tcp_port"]
                    print(f"Server found at {server_ip}:{server_port}")
                    return True
            except socket.timeout:
                print("Server not found. Retrying...")
            attempts += 1
            time.sleep(RECONNECT_INTERVAL)
    return False

def connect_to_server():
    global server_ip, server_port
    if not server_ip or not server_port:
        print("Server IP or port not set. Cannot connect.")
        return False
    
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((server_ip, server_port))
            message = create_json_message("CONNECT", client_id=client_id, client_port=client_port)
            sock.send(message)
            response = sock.recv(BUFFER_SIZE).decode()
            if json.loads(response).get("status") == "OK":
                print("Connected to server successfully.")
                connected_event.set()
                return True
            else:
                print("Failed to connect to server.")
                return False
    except Exception as e:
        print(f"Error connecting to server: {e}")
        return False

def send_message(message):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((server_ip, server_port))
            data = create_json_message("CHAT", client_id=client_id, message=message)
            sock.send(data)
    except Exception as e:
        print(f"Error sending message: {e}")
        connected_event.clear()

def receive_messages():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('', client_port))
        sock.listen(1)
        print(f"Listening for messages on port {client_port}")
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

def user_input_handler():
    while not shutdown_event.is_set():
        if not connected_event.is_set():
            print("Not connected to server. Attempting to reconnect...")
            if locate_server() and connect_to_server():
                print("Reconnected to server.")
            else:
                print("Failed to reconnect. Please try again later.")
                time.sleep(RECONNECT_INTERVAL)
                continue

        message = input("Enter message (or 'quit' to exit): ")
        if message.lower() == 'quit':
            shutdown_event.set()
            break
        send_message(message)

def main():
    global client_port

    if len(sys.argv) > 1:
        client_port = int(sys.argv[1])
    else:
        client_port = find_available_port(CLIENT_BASE_PORT)

    print(f"Client starting - ID: {client_id}, Port: {client_port}")
    
    if not locate_server():
        print("Failed to locate a server. Exiting.")
        return

    if not connect_to_server():
        print("Failed to connect to the server. Exiting.")
        return

    receive_thread = threading.Thread(target=receive_messages, daemon=True)
    receive_thread.start()

    input_thread = threading.Thread(target=user_input_handler, daemon=True)
    input_thread.start()

    try:
        while not shutdown_event.is_set():
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nInterrupt received, shutting down...")
        shutdown_event.set()

    print("Client disconnected.")

if __name__ == "__main__":
    main()