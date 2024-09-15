import socket
import threading
import random
import time
import uuid

is_leader = False
server_id = None
all_servers = {}

DISCOVERY_PORT = 55555
DATA_PORT_RANGE = (49152, 65535)

class Server:
    def __init__(self):
        self.uuid = uuid.uuid4().int
        self.data_port = self.get_random_port(*DATA_PORT_RANGE)
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind(('0.0.0.0', self.data_port))
        self.server_socket.listen(5)
        self.clients = {}
        self.lock = threading.Lock()
        self.running = True

    def get_random_port(self, start, end):
        return random.randint(start, end)

    def start_server(self):
        print(f"Server (UUID: {self.uuid}) listening for connections on port {self.data_port}")
        accept_thread = threading.Thread(target=self.accept_connections)
        accept_thread.start()

    def accept_connections(self):
        while self.running:
            try:
                client_socket, client_address = self.server_socket.accept()
                print(f"Accepted connection from {client_address}")
                with self.lock:
                    self.clients[client_address] = client_socket
                threading.Thread(target=self.handle_client, args=(client_socket, client_address)).start()
            except Exception as e:
                print(f"Error accepting connection: {e}")

    def handle_client(self, client_socket, client_address):
        while self.running:
            try:
                data = client_socket.recv(1024)
                if data:
                    message = data.decode('utf-8')
                    if message == "HEARTBEAT":
                        client_socket.sendall(b"HEARTBEAT_ACK")
                    else:
                        print(f"Message from {client_address}: {message}")
                        self.broadcast_message(message, client_address)
                else:
                    self.remove_client(client_address)
                    break
            except socket.error as e:
                print(f"Error with client {client_address}: {e}")
                self.remove_client(client_address)
                break

    def broadcast_message(self, message, exclude_address=None):
        with self.lock:
            for client_address, client_socket in self.clients.items():
                if client_address != exclude_address:
                    try:
                        client_socket.sendall(message.encode('utf-8'))
                    except socket.error as e:
                        print(f"Error sending message to {client_address}: {e}")
                        self.remove_client(client_address)

    def remove_client(self, client_address):
        with self.lock:
            if client_address in self.clients:
                self.clients[client_address].close()
                del self.clients[client_address]
                print(f"Removed client {client_address}")

    def stop_server(self):
        self.running = False
        self.server_socket.close()
        with self.lock:
            for client_socket in self.clients.values():
                client_socket.close()
        self.clients.clear()
        print("Server stopped")

    def run(self):
        try:
            self.start_server()
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop_server()

class InactiveServer:
    def __init__(self):
        self.uuid = uuid.uuid4().int
        self.data_port = self.get_random_port(*DATA_PORT_RANGE)
        self.socket = None
        self.connected = False
        self.heartbeat_interval = 1
        self.heartbeat_thread = None
        self.receive_thread = None
        self.terminate = False

    def get_random_port(self, start, end):
        return random.randint(start, end)

    def discover_servers(self):
        global all_servers
        discovery_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        discovery_socket.bind(('', DISCOVERY_PORT))
        discovery_socket.settimeout(0.5)

        message = f"DISCOVER:{self.uuid}:{self.data_port}"
        start_time = time.time()

        while time.time() - start_time < 10:  # 15-second discovery window
            discovery_socket.sendto(message.encode(), ('<broadcast>', DISCOVERY_PORT))
            
            try:
                while True:
                    data, addr = discovery_socket.recvfrom(1024)
                    response = data.decode()
                    if response.startswith("DISCOVER:"):
                        # Reply to discovery messages
                        reply = f"ANNOUNCE:{self.uuid}:{self.data_port}"
                        discovery_socket.sendto(reply.encode(), addr)
                    elif response.startswith("ANNOUNCE:"):
                        # Process announcements
                        _, uuid, port = response.split(':')
                        uuid = int(uuid)
                        port = int(port)
                        if uuid != self.uuid and uuid not in all_servers:
                            all_servers[uuid] = (addr[0], port)
                            print(f"Discovered server: UUID {uuid}, IP {addr[0]}, Port {port}")
            except socket.timeout:
                pass

        discovery_socket.close()
        print(f"Discovery complete. Found {len(all_servers)} other servers.")

    def elect_leader(self):
        global is_leader, server_id
        all_uuids = list(all_servers.keys()) + [self.uuid]
        highest_uuid = max(all_uuids)
        
        if self.uuid == highest_uuid:
            print(f"This server has the highest UUID ({self.uuid}). Becoming the leader.")
            is_leader = True
            server_id = self.uuid
        else:
            print(f"Server with UUID {highest_uuid} is the leader. Remaining as inactive server.")
            is_leader = False
            server_id = self.uuid

    def connect_to_leader(self):
        if is_leader:
            return

        leader_uuid = max(all_servers.keys())
        leader_ip, leader_port = all_servers[leader_uuid]

        max_retries = 10
        retry_count = 0

        while not self.connected and retry_count < max_retries:
            try:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.connect((leader_ip, leader_port))
                self.connected = True
                self.terminate = False
                print(f"Connected to leader at ({leader_ip}, {leader_port})")
                self.start_heartbeat()
                self.start_receiving()
            except socket.error as e:
                print(f"Error connecting to leader: {e}. Retrying in 1 second... (Attempt {retry_count + 1}/{max_retries})")
                time.sleep(1)
                retry_count += 1

        if not self.connected:
            print("Failed to connect to the leader after multiple attempts. Starting a new election.")
            self.election()

    def start_heartbeat(self):
        if self.connected:
            self.heartbeat_thread = threading.Thread(target=self.send_heartbeat)
            self.heartbeat_thread.start()

    def send_heartbeat(self):
        while self.connected and not self.terminate:
            try:
                self.socket.sendall(b"HEARTBEAT")
                time.sleep(self.heartbeat_interval)
            except socket.error as e:
                print(f"Error sending heartbeat: {e}")
                self.connected = False
                self.cleanup()
                self.connect_to_leader()

    def start_receiving(self):
        if self.connected:
            self.receive_thread = threading.Thread(target=self.receive_data)
            self.receive_thread.start()

    def receive_data(self):
        while self.connected and not self.terminate:
            try:
                data = self.socket.recv(1024)
                if data:
                    message = data.decode('utf-8')
                    if message != "HEARTBEAT_ACK":
                        print(f"Message from leader: {message}")
                else:
                    print("No heartbeat received. Starting new leader election")
                    self.election()
            except socket.error as e:
                print(f"Error receiving data: {e}")
                self.connected = False
                self.cleanup()
                self.connect_to_leader()

    def cleanup(self):
        self.terminate = True
        if self.socket:
            self.socket.close()
        if self.heartbeat_thread and threading.current_thread() != self.heartbeat_thread:
            self.heartbeat_thread.join()
        if self.receive_thread and threading.current_thread() != self.receive_thread:
            self.receive_thread.join()

    def run(self):
        self.discover_servers()
        self.elect_leader()
        if is_leader:
            application()
        else:
            self.connect_to_leader()

    def election(self):
        global is_leader, server_id, all_servers
        self.connected = False
        self.cleanup()
        all_servers.clear()
        self.discover_servers()
        self.elect_leader()
        if is_leader:
            application()
        else:
            self.connect_to_leader()

def application():
    if is_leader:
        server = Server()
        server.run()
    else:
        client = InactiveServer()
        client.run()

if __name__ == "__main__":
    application()