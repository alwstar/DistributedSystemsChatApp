import socket
import threading
import time
import json
import random
import sys

# Constants
UDP_PORT = 42000
TCP_BASE_PORT = 6000
BUFFER_SIZE = 1024

# Global variables
server_id = f"SERVER_{random.randint(1000, 9999)}"
tcp_port = None
connected_servers = {}
leader = None
is_active = True
shutdown_event = threading.Event()

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

def broadcast_presence():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while not shutdown_event.is_set():
            message = create_json_message("server_available", id=server_id, port=tcp_port)
            try:
                udp_socket.sendto(message, ('<broadcast>', UDP_PORT))
                print(f"Broadcast sent: Server {server_id} available on port {tcp_port}")
            except Exception as e:
                print(f"Error sending broadcast: {e}")
            time.sleep(5)

def listen_for_broadcasts():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp_socket.bind(('', UDP_PORT))
        print(f"Listening for broadcasts on UDP port {UDP_PORT}")
        while not shutdown_event.is_set():
            try:
                data, addr = udp_socket.recvfrom(BUFFER_SIZE)
                message_type, message_data = parse_json_message(data.decode())
                if message_type == "server_available" and message_data['id'] != server_id:
                    print(f"Discovered server: {message_data['id']} on {addr[0]}:{message_data['port']}")
                    connect_to_server(addr[0], int(message_data['port']), message_data['id'])
            except Exception as e:
                print(f"Error receiving broadcast: {e}")

def connect_to_server(ip, port, server_id):
    if server_id not in connected_servers:
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.connect((ip, port))
            connected_servers[server_id] = {'socket': server_socket, 'address': ip, 'port': port}
            print(f"Connected to server {server_id} at {ip}:{port}")
            threading.Thread(target=handle_server_connection, args=(server_socket, server_id)).start()
        except Exception as e:
            print(f"Error connecting to server {server_id}: {e}")

def handle_server_connection(server_socket, remote_server_id):
    while not shutdown_event.is_set():
        try:
            data = server_socket.recv(BUFFER_SIZE)
            if not data:
                break
            message_type, message_data = parse_json_message(data.decode())
            handle_message(message_type, message_data, remote_server_id)
        except Exception as e:
            print(f"Error handling connection with server {remote_server_id}: {e}")
            break
    
    if remote_server_id in connected_servers:
        del connected_servers[remote_server_id]
    print(f"Connection with server {remote_server_id} closed")

def handle_message(message_type, message_data, sender_id):
    global leader
    if message_type == "election":
        handle_election(message_data, sender_id)
    elif message_type == "leader_announcement":
        leader = message_data['leader_id']
        print(f"New leader announced: {leader}")
    # Add more message handlers as needed

def handle_election(election_data, sender_id):
    global leader
    if election_data['candidate_id'] > server_id:
        forward_election(election_data)
    elif election_data['candidate_id'] < server_id:
        start_election()
    else:
        leader = server_id
        announce_leader()

def start_election():
    election_message = create_json_message("election", candidate_id=server_id)
    for srv_id, srv_info in connected_servers.items():
        try:
            srv_info['socket'].send(election_message)
        except Exception as e:
            print(f"Error sending election message to {srv_id}: {e}")

def forward_election(election_data):
    election_message = create_json_message("election", **election_data)
    for srv_id, srv_info in connected_servers.items():
        if srv_id != election_data['candidate_id']:
            try:
                srv_info['socket'].send(election_message)
            except Exception as e:
                print(f"Error forwarding election message to {srv_id}: {e}")

def announce_leader():
    leader_message = create_json_message("leader_announcement", leader_id=server_id)
    for srv_id, srv_info in connected_servers.items():
        try:
            srv_info['socket'].send(leader_message)
        except Exception as e:
            print(f"Error announcing leader to {srv_id}: {e}")

def accept_connections():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket:
        tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tcp_socket.bind(('', tcp_port))
        tcp_socket.listen()
        print(f"Listening for TCP connections on port {tcp_port}")
        while not shutdown_event.is_set():
            try:
                client_socket, addr = tcp_socket.accept()
                print(f"Accepted connection from {addr}")
                threading.Thread(target=handle_new_connection, args=(client_socket, addr)).start()
            except Exception as e:
                print(f"Error accepting connection: {e}")

def handle_new_connection(client_socket, addr):
    try:
        data = client_socket.recv(BUFFER_SIZE)
        message_type, message_data = parse_json_message(data.decode())
        if message_type == "server_hello":
            remote_server_id = message_data['id']
            connected_servers[remote_server_id] = {'socket': client_socket, 'address': addr[0], 'port': addr[1]}
            print(f"Server {remote_server_id} connected from {addr}")
            threading.Thread(target=handle_server_connection, args=(client_socket, remote_server_id)).start()
        else:
            print(f"Unexpected message type from {addr}: {message_type}")
            client_socket.close()
    except Exception as e:
        print(f"Error handling new connection from {addr}: {e}")
        client_socket.close()

def display_status():
    print(f"\nServer ID: {server_id}")
    print(f"TCP Port: {tcp_port}")
    print(f"Current leader: {leader if leader else 'No leader elected'}")
    print("Connected servers:")
    for srv_id, srv_info in connected_servers.items():
        print(f"  {srv_id} at {srv_info['address']}:{srv_info['port']}")

def main():
    global tcp_port, leader

    tcp_port = find_available_port(TCP_BASE_PORT)
    print(f"Server starting - ID: {server_id}, TCP Port: {tcp_port}")

    threading.Thread(target=broadcast_presence, daemon=True).start()
    threading.Thread(target=listen_for_broadcasts, daemon=True).start()
    threading.Thread(target=accept_connections, daemon=True).start()

    time.sleep(2)  # Give some time for initial connections

    if not connected_servers:
        print("No other servers found. This server is the leader.")
        leader = server_id
    else:
        start_election()

    while not shutdown_event.is_set():
        cmd = input("\nEnter command (status/quit): ").lower()
        if cmd == 'status':
            display_status()
        elif cmd == 'quit':
            print("Shutting down server...")
            shutdown_event.set()
            break
        else:
            print("Unknown command. Available commands: status, quit")

    for srv_info in connected_servers.values():
        srv_info['socket'].close()

if __name__ == "__main__":
    main()