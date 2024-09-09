import socket
import threading
import random
import time

print("Script is starting...")

DISCOVERY_PORT = 60000  # Fixed port for discovery
CLIENT_HANDSHAKE_PORTS = [60000, 60001, 60002, 60003]  # Ports for client handshake
HEARTBEAT_INTERVAL = 5  # Seconds between heartbeats
HEARTBEAT_TIMEOUT = 15  # Seconds to wait before considering leader dead
LEADER_BROADCAST_INTERVAL = 3  # Seconds between leader broadcasts

class Server:
    def __init__(self):
        self.data_port = self.get_random_port(49152, 59999)
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind(('0.0.0.0', self.data_port))
        self.server_socket.listen(5)
        self.clients = {}
        self.lock = threading.Lock()
        self.running = True
        self.is_leader = False
        self.identifier = self.generate_identifier()
        self.other_servers = {}
        self.election_in_progress = False
        self.leader_id = None
        self.leader_ip = None
        self.leader_port = None
        self.last_heartbeat = time.time()

    def generate_identifier(self):
        timestamp = int(time.time() * 1000)  # milliseconds
        random_number = random.randint(0, 9999)
        return f"{timestamp}_{random_number}"

    def get_random_port(self, start, end):
        return random.randint(start, end)

    def start_server(self):
        print(f"Server starting with identifier: {self.identifier}")
        print(f"Listening for connections on port {self.data_port}")
        accept_thread = threading.Thread(target=self.accept_connections)
        accept_thread.start()
        self.discover_servers()
        self.start_election()

    def listen_for_client_handshake(self, port):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as handshake_socket:
            handshake_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            handshake_socket.bind(('0.0.0.0', port))
            print(f"Listening for client handshakes on port {port}")
            while self.running:
                try:
                    data, addr = handshake_socket.recvfrom(1024)
                    message = data.decode('utf-8')
                    if message == "REQUEST_CONNECTION_CLIENT":
                        print(f"Received client handshake request from {addr}")
                        if self.is_leader:
                            response = f"{self.leader_ip}:{self.leader_port}"
                            handshake_socket.sendto(response.encode('utf-8'), addr)
                            print(f"Sent handshake response to client: {response}")
                        elif self.leader_ip and self.leader_port:
                            response = f"{self.leader_ip}:{self.leader_port}"
                            handshake_socket.sendto(response.encode('utf-8'), addr)
                            print(f"Redirected client to leader: {response}")
                        else:
                            print("No leader available to handle client request")
                except Exception as e:
                    print(f"Error in client handshake listener on port {port}: {e}")

    def discover_servers(self):
        print("Starting server discovery phase...")
        discovery_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            discovery_socket.bind(('', DISCOVERY_PORT))
        except Exception as e:
            print(f"Error binding to discovery port {DISCOVERY_PORT}: {e}")
            return

        discovery_socket.settimeout(0.5)

        # Start a thread to listen for discovery messages
        threading.Thread(target=self.listen_for_discovery, args=(discovery_socket,), daemon=True).start()

        start_time = time.time()
        while time.time() - start_time < 15:
            message = f"DISCOVER:{self.identifier}:{self.data_port}"
            try:
                discovery_socket.sendto(message.encode('utf-8'), ('<broadcast>', DISCOVERY_PORT))
                print(f"Sent discovery message to port {DISCOVERY_PORT}")
            except Exception as e:
                print(f"Error sending discovery message: {e}")
            time.sleep(1)  # Wait a bit before next broadcast

        print(f"Discovery phase complete. Found {len(self.other_servers)} other servers.")

    def listen_for_discovery(self, discovery_socket):
        while self.running:
            try:
                data, addr = discovery_socket.recvfrom(1024)
                message = data.decode('utf-8')
                if message.startswith("DISCOVER:"):
                    _, other_id, other_port = message.split(':')
                    other_port = int(other_port)
                    if other_id != self.identifier:  # Don't add ourselves
                        self.other_servers[other_id] = (addr[0], other_port)
                        print(f"Discovered server: {other_id} at {addr[0]}:{other_port}")
                    # Always send a response back, even to ourselves
                    response = f"DISCOVER:{self.identifier}:{self.data_port}"
                    discovery_socket.sendto(response.encode('utf-8'), addr)
            except socket.timeout:
                pass
            except Exception as e:
                print(f"Error in discovery listener: {e}")

    def start_election(self):
        if self.election_in_progress:
            return

        self.election_in_progress = True
        print("Starting election process...")
        highest_id = max(list(self.other_servers.keys()) + [self.identifier])

        if highest_id == self.identifier:
            self.become_leader()
        else:
            self.send_election_message(highest_id)

    def send_election_message(self, highest_id):
        for server_id, (ip, port) in self.other_servers.items():
            if server_id > self.identifier:
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.connect((ip, port))
                        s.sendall(f"ELECTION:{highest_id}".encode('utf-8'))
                except:
                    print(f"Failed to send election message to {server_id}")

        # Wait for a response
        time.sleep(5)
        if not self.is_leader:
            self.become_leader()

    def become_leader(self):
        self.is_leader = True
        self.leader_id = self.identifier
        self.leader_ip = socket.gethostbyname(socket.gethostname())
        self.leader_port = self.data_port
        self.election_in_progress = False
        print(f"This server (ID: {self.identifier}) is now the leader")
        for server_id, (ip, port) in self.other_servers.items():
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((ip, port))
                    s.sendall(f"COORDINATOR:{self.identifier}:{self.leader_ip}:{self.leader_port}".encode('utf-8'))
            except:
                print(f"Failed to send coordinator message to {server_id}")
        
        # Start sending heartbeats and leader broadcasts
        threading.Thread(target=self.send_heartbeats, daemon=True).start()
        threading.Thread(target=self.broadcast_leader_info, daemon=True).start()

    def send_heartbeats(self):
        while self.running and self.is_leader:
            for server_id, (ip, port) in self.other_servers.items():
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.connect((ip, port))
                        s.sendall(f"HEARTBEAT:{self.identifier}".encode('utf-8'))
                except:
                    print(f"Failed to send heartbeat to {server_id}")
            time.sleep(HEARTBEAT_INTERVAL)

    def broadcast_leader_info(self):
        broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        
        while self.running and self.is_leader:
            message = f"LEADER:{self.leader_id}:{self.leader_ip}:{self.leader_port}"
            for port in CLIENT_HANDSHAKE_PORTS:
                try:
                    broadcast_socket.sendto(message.encode('utf-8'), ('<broadcast>', port))
                except Exception as e:
                    print(f"Error broadcasting leader info on port {port}: {e}")
            time.sleep(LEADER_BROADCAST_INTERVAL)

    def send_client_heartbeats(self):
        while self.running and self.is_leader:
            with self.lock:
                for client_socket in self.clients.values():
                    try:
                        client_socket.sendall(b"LEADER_HEARTBEAT")
                    except:
                        # Handle disconnected clients
                        pass
            time.sleep(HEARTBEAT_INTERVAL)

    def accept_connections(self):
        while self.running:
            try:
                client_socket, client_address = self.server_socket.accept()
                threading.Thread(target=self.handle_connection, args=(client_socket, client_address)).start()
            except Exception as e:
                if self.running:
                    print(f"Error accepting connection: {e}")
                else:
                    break  # Server is shutting down, exit the loop

    def handle_connection(self, client_socket, client_address):
        while self.running:
            try:
                data = client_socket.recv(1024)
                if data:
                    message = data.decode('utf-8')
                    if message.startswith("ELECTION:"):
                        self.handle_election_message(message)
                    elif message.startswith("COORDINATOR:"):
                        self.handle_coordinator_message(message)
                    elif message.startswith("HEARTBEAT:"):
                        self.handle_heartbeat(message)
                    else:
                        print(f"Message from {client_address}: {message}")
                        self.broadcast_message(message, client_address)
                else:
                    break
            except socket.error as e:
                print(f"Error handling connection from {client_address}: {e}")
                break
        client_socket.close()

    def handle_election_message(self, message):
        _, highest_id = message.split(':')
        if highest_id > self.identifier:
            self.send_election_message(highest_id)
        else:
            self.start_election()

    def handle_coordinator_message(self, message):
        _, leader_id, leader_ip, leader_port = message.split(':')
        leader_port = int(leader_port)
        if leader_id > self.identifier:
            self.is_leader = False
            self.leader_id = leader_id
            self.leader_ip = leader_ip
            self.leader_port = leader_port
            self.election_in_progress = False
            print(f"Server {leader_id} at {leader_ip}:{leader_port} is now the leader")
        else:
            self.start_election()

    def handle_heartbeat(self, message):
        _, sender_id = message.split(':')
        print(f"Received heartbeat from {sender_id}")
        self.last_heartbeat = time.time()

    def broadcast_message(self, message, exclude_address=None):
        with self.lock:
            for client_address, client_socket in self.clients.items():
                if client_address != exclude_address:
                    try:
                        client_socket.sendall(message.encode('utf-8'))
                    except socket.error:
                        self.clients.pop(client_address)

    def monitor_leader(self):
        while self.running:
            if not self.is_leader and self.leader_id:
                if time.time() - self.last_heartbeat > HEARTBEAT_TIMEOUT:
                    print(f"Leader {self.leader_id} is considered dead. Starting new election.")
                    self.leader_id = None
                    self.start_new_election()
            time.sleep(1)

    def start_new_election(self):
        self.other_servers.clear()
        self.discover_servers()
        self.start_election()

    def run(self):
        try:
            self.start_server()
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Keyboard interrupt received. Shutting down...")
        finally:
            self.running = False
            self.server_socket.close()
            print("Server shut down.")

def main():
    server = Server()
    server.run()

if __name__ == "__main__":
    main()