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
SEARCH_TIME = 10  # Time to search for other servers
ELECTION_TIMEOUT = 15  # Timeout for election process
CONNECTION_TIMEOUT = 10  # Timeout for initial connection
HEARTBEAT_INTERVAL = 5  # Interval for sending heartbeats
LEADER_CHECK_INTERVAL = 10  # Interval for checking leader status

# Global variables
server_id = f"SERVER_{random.randint(1000, 9999)}"
tcp_port = None
connected_servers = {}
leader = None
is_active = True
shutdown_event = threading.Event()
ring_formed = threading.Event()
election_in_progress = threading.Event()
all_servers_ready = threading.Event()

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
        end_time = time.time() + SEARCH_TIME
        while time.time() < end_time and not shutdown_event.is_set():
            message = create_json_message("server_available", id=server_id, port=tcp_port)
            try:
                udp_socket.sendto(message, ('<broadcast>', UDP_PORT))
                print(f"Broadcast sent: Server {server_id} available on port {tcp_port}")
            except Exception as e:
                print(f"Error sending broadcast: {e}")
            time.sleep(1)
    print("Server search completed.")
    ring_formed.set()

def listen_for_broadcasts():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp_socket.bind(('', UDP_PORT))
        udp_socket.settimeout(1)  # Set a timeout for the socket
        print(f"Listening for broadcasts on UDP port {UDP_PORT}")
        end_time = time.time() + SEARCH_TIME
        while time.time() < end_time and not shutdown_event.is_set():
            try:
                data, addr = udp_socket.recvfrom(BUFFER_SIZE)
                message_type, message_data = parse_json_message(data.decode())
                if message_type == "server_available" and message_data['id'] != server_id:
                    if message_data['id'] not in connected_servers:
                        print(f"Discovered server: {message_data['id']} on {addr[0]}:{message_data['port']}")
                        threading.Thread(target=connect_to_server, args=(addr[0], int(message_data['port']), message_data['id'])).start()
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Error receiving broadcast: {e}")
    print("Broadcast listening completed.")

def connect_to_server(ip, port, remote_server_id):
    if remote_server_id not in connected_servers and remote_server_id != server_id:
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.settimeout(CONNECTION_TIMEOUT)
            server_socket.connect((ip, port))
            server_socket.send(create_json_message("server_hello", id=server_id))
            response = server_socket.recv(BUFFER_SIZE)
            message_type, _ = parse_json_message(response.decode())
            if message_type == "server_hello_ack":
                connected_servers[remote_server_id] = {'socket': server_socket, 'address': ip, 'port': port}
                print(f"Successfully connected to server {remote_server_id} at {ip}:{port}")
                threading.Thread(target=handle_server_connection, args=(server_socket, remote_server_id)).start()
                threading.Thread(target=send_heartbeat, args=(server_socket, remote_server_id)).start()
            else:
                print(f"Unexpected response from server {remote_server_id}")
                server_socket.close()
        except Exception as e:
            print(f"Error connecting to server {remote_server_id}: {e}")

def handle_server_connection(server_socket, remote_server_id):
    server_socket.settimeout(CONNECTION_TIMEOUT)
    while not shutdown_event.is_set():
        try:
            data = server_socket.recv(BUFFER_SIZE)
            if not data:
                break
            message_type, message_data = parse_json_message(data.decode())
            handle_message(message_type, message_data, remote_server_id)
        except socket.timeout:
            continue
        except Exception as e:
            print(f"Error handling connection with server {remote_server_id}: {e}")
            break
    
    if remote_server_id in connected_servers:
        del connected_servers[remote_server_id]
    print(f"Connection with server {remote_server_id} closed")

def send_heartbeat(server_socket, remote_server_id):
    while not shutdown_event.is_set() and remote_server_id in connected_servers:
        try:
            server_socket.send(create_json_message("heartbeat"))
            time.sleep(HEARTBEAT_INTERVAL)
        except Exception as e:
            print(f"Error sending heartbeat to {remote_server_id}: {e}")
            break

def handle_message(message_type, message_data, sender_id):
    global leader
    if message_type == "election":
        handle_election(message_data, sender_id)
    elif message_type == "leader_announcement":
        leader = message_data['leader_id']
        print(f"Leader announced: {leader}")
        if leader != server_id:
            print(f"This server acknowledges {leader} as the leader")
        election_in_progress.clear()
    elif message_type == "heartbeat":
        # Heartbeat received, connection is still alive
        pass
    elif message_type == "ready_for_election":
        all_servers_ready.set()
    elif message_type == "leader_check":
        if leader == server_id:
            try:
                connected_servers[sender_id]['socket'].send(create_json_message("leader_alive"))
            except Exception as e:
                print(f"Error responding to leader check from {sender_id}: {e}")

def handle_election(election_data, sender_id):
    global leader
    candidate_id = election_data['candidate_id']
    print(f"Received election message from {sender_id} with candidate {candidate_id}")
    if candidate_id > server_id:
        forward_election(election_data)
    elif candidate_id < server_id:
        start_election()
    else:
        leader = server_id
        announce_leader()

def start_election():
    global leader
    if not election_in_progress.is_set():
        election_in_progress.set()
        leader = None  # Reset leader
        print(f"Starting election with candidate ID: {server_id}")
        election_message = create_json_message("election", candidate_id=server_id)
        next_server = get_next_server_in_ring()
        if next_server:
            try:
                connected_servers[next_server]['socket'].send(election_message)
            except Exception as e:
                print(f"Error sending election message to {next_server}: {e}")
                election_in_progress.clear()
        
        # Set a timeout for the election process
        threading.Timer(ELECTION_TIMEOUT, end_election_timeout).start()

def end_election_timeout():
    global leader
    if election_in_progress.is_set():
        print("Election timeout reached. Assuming leadership.")
        leader = server_id
        announce_leader()
        election_in_progress.clear()

def forward_election(election_data):
    election_message = create_json_message("election", **election_data)
    next_server = get_next_server_in_ring()
    if next_server:
        try:
            connected_servers[next_server]['socket'].send(election_message)
        except Exception as e:
            print(f"Error forwarding election message to {next_server}: {e}")

def announce_leader():
    print(f"Announcing self as leader: {server_id}")
    leader_message = create_json_message("leader_announcement", leader_id=server_id)
    for srv_id, srv_info in connected_servers.items():
        try:
            srv_info['socket'].send(leader_message)
        except Exception as e:
            print(f"Error announcing leader to {srv_id}: {e}")

def get_next_server_in_ring():
    if not connected_servers:
        return None
    server_ids = sorted(list(connected_servers.keys()) + [server_id])
    current_index = server_ids.index(server_id)
    next_index = (current_index + 1) % len(server_ids)
    next_server_id = server_ids[next_index]
    return next_server_id if next_server_id != server_id else None

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
            if remote_server_id not in connected_servers and remote_server_id != server_id:
                connected_servers[remote_server_id] = {'socket': client_socket, 'address': addr[0], 'port': addr[1]}
                print(f"Server {remote_server_id} connected from {addr}")
                client_socket.send(create_json_message("server_hello_ack"))
                threading.Thread(target=handle_server_connection, args=(client_socket, remote_server_id)).start()
                threading.Thread(target=send_heartbeat, args=(client_socket, remote_server_id)).start()
            else:
                print(f"Duplicate connection attempt from {remote_server_id}. Ignoring.")
                client_socket.close()
        else:
            print(f"Unexpected message type from {addr}: {message_type}")
            client_socket.close()
    except Exception as e:
        print(f"Error handling new connection from {addr}: {e}")
        client_socket.close()

def check_leader_status():
    global leader
    while not shutdown_event.is_set():
        time.sleep(LEADER_CHECK_INTERVAL)
        if leader and leader != server_id:
            try:
                leader_socket = connected_servers[leader]['socket']
                leader_socket.send(create_json_message("leader_check"))
                # Wait for response
                leader_socket.settimeout(5)
                response = leader_socket.recv(BUFFER_SIZE)
                message_type, _ = parse_json_message(response.decode())
                if message_type != "leader_alive":
                    raise Exception("Invalid leader response")
            except Exception as e:
                print(f"Leader {leader} seems to be down: {e}")
                leader = None
                start_election()
        elif not leader:
            start_election()

def display_status():
    print(f"\nServer ID: {server_id}")
    print(f"TCP Port: {tcp_port}")
    print(f"Current leader: {leader if leader else 'No leader elected'}")
    print("Connected servers:")
    for srv_id, srv_info in connected_servers.items():
        if srv_id != server_id:
            print(f"  {srv_id} at {srv_info['address']}:{srv_info['port']}")

def main():
    global tcp_port, leader

    if len(sys.argv) > 1:
        tcp_port = int(sys.argv[1])
    else:
        tcp_port = find_available_port(TCP_BASE_PORT)
    
    print(f"Server starting - ID: {server_id}, TCP Port: {tcp_port}")

    threading.Thread(target=broadcast_presence, daemon=True).start()
    threading.Thread(target=listen_for_broadcasts, daemon=True).start()
    threading.Thread(target=accept_connections, daemon=True).start()
    threading.Thread(target=check_leader_status, daemon=True).start()

    ring_formed.wait()  # Wait for the ring to be formed
    time.sleep(2)  # Give more time for final connections

    print("Ring formed. Waiting for all servers to be ready.")
    for srv_id in connected_servers:
        try:
            connected_servers[srv_id]['socket'].send(create_json_message("ready_for_election"))
        except Exception as e:
            print(f"Error sending ready message to {srv_id}: {e}")

    all_servers_ready.wait(timeout=5)  # Wait for all servers to be ready, with a timeout

    print("Starting initial leader election.")
    if connected_servers:
        start_election()
    else:
        print("No other servers found. This server is the leader.")
        leader = server_id
        announce_leader()

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