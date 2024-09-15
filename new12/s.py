import socket
import threading
import random
import time

is_leader = False
server_id = None

# Server class to handle the connection and communication
class Server:
    def __init__(self, handshake_ports=[60000, 60001, 60002, 60003]):
        self.handshake_ports = handshake_ports
        self.handshake_port = None
        self.data_port = self.get_random_port(49152, 59999)
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind(('0.0.0.0', self.data_port))
        self.server_socket.listen(5)
        self.clients = {}
        self.other_servers = {}
        self.lock = threading.Lock()
        self.running = True
        self.next_server_id = 0
        self.is_leader = False
        self.server_id = random.randint(1, 1000000)  # Generate a random ID
        self.leader_id = None
        self.leader_heartbeat = time.time()

    def get_random_port(self, start, end):
        return random.randint(start, end)

    def start_server(self):
        print(f"Server (ID: {self.server_id}) starting on {self.get_ip_address()}:{self.data_port}")
        self.discover_servers()
        self.form_ring()
        self.start_election()
        if self.is_leader:
            self.announce_leader()
        self.listen_for_connections()

    # Discover other servers in the network

    def discover_servers(self):
        discovery_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        discovery_socket.settimeout(2)

        for port in self.handshake_ports:
            message = f"DISCOVER:{self.server_id}:{self.get_ip_address()}:{self.data_port}"
            discovery_socket.sendto(message.encode(), ('<broadcast>', port))

        start_time = time.time()
        while time.time() - start_time < 5:  # Discovery period of 5 seconds
            try:
                data, addr = discovery_socket.recvfrom(1024)
                message = data.decode()
                if message.startswith("DISCOVER:"):
                    _, server_id, ip, port = message.split(':')
                    server_id = int(server_id)
                    port = int(port)
                    if server_id != self.server_id:
                        self.other_servers[server_id] = (ip, port)
                        print(f"Discovered server: ID {server_id} at {ip}:{port}")
            except socket.timeout:
                pass

        discovery_socket.close()
        print(f"Server discovery complete. Found {len(self.other_servers)} other servers.")

    def form_ring(self):
        all_ids = sorted(list(self.other_servers.keys()) + [self.server_id])
        if len(all_ids) > 1:
            next_index = (all_ids.index(self.server_id) + 1) % len(all_ids)
            next_id = all_ids[next_index]
            self.next_server = self.other_servers[next_id] if next_id != self.server_id else (self.get_ip_address(), self.data_port)
        else:
            self.next_server = (self.get_ip_address(), self.data_port)
        
        print(f"Ring formed. Next server is {'self' if self.next_server[0] == self.get_ip_address() else self.next_server}")

    def start_election(self):
        print("Starting leader election...")
        election_message = f"ELECTION:{self.server_id}"
        self.send_to_next(election_message)
        
        highest_id = self.server_id
        while True:
            data = self.receive_from_previous()
            if data.startswith("ELECTION:"):
                received_id = int(data.split(':')[1])
                if received_id > highest_id:
                    highest_id = received_id
                    self.send_to_next(f"ELECTION:{highest_id}")
                elif received_id < self.server_id:
                    self.send_to_next(f"ELECTION:{self.server_id}")
                else:  # received_id == self.server_id
                    self.leader_id = self.server_id
                    self.is_leader = True
                    print(f"Election complete. Server {self.server_id} is the new leader.")
                    break

    def announce_leader(self):
        if self.is_leader:
            announcement = f"LEADER:{self.server_id}"
            self.send_to_next(announcement)
            print(f"Announced self as leader (ID: {self.server_id})")

    def send_to_next(self, message):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect(self.next_server)
            s.sendall(message.encode())

    def receive_from_previous(self):
        conn, addr = self.server_socket.accept()
        with conn:
            data = conn.recv(1024).decode()
            return data

    def listen_for_connections(self):
        while self.running:
            conn, addr = self.server_socket.accept()
            threading.Thread(target=self.handle_connection, args=(conn, addr)).start()

    def handle_connection(self, conn, addr):
        with conn:
            data = conn.recv(1024).decode()
            if data.startswith("ELECTION:"):
                self.handle_election_message(data)
            elif data.startswith("LEADER:"):
                self.handle_leader_announcement(data)
            # Handle other types of messages (e.g., client connections) here

    def handle_election_message(self, message):
        received_id = int(message.split(':')[1])
        if received_id > self.server_id:
            self.send_to_next(message)
        elif received_id < self.server_id:
            self.send_to_next(f"ELECTION:{self.server_id}")
        else:  # received_id == self.server_id
            self.leader_id = self.server_id
            self.is_leader = True
            print(f"Election complete. Server {self.server_id} is the new leader.")
            self.announce_leader()

    def handle_leader_announcement(self, message):
        leader_id = int(message.split(':')[1])
        if leader_id != self.server_id:
            self.leader_id = leader_id
            self.is_leader = False
            print(f"New leader announced: Server {leader_id}")
            self.send_to_next(message)






    # 

    def listen_for_handshake(self):
        for port in self.handshake_ports:
            try:
                handshake_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                handshake_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                handshake_socket.bind(('0.0.0.0', port))
                self.handshake_port = port
                print(f"Server listening for handshake on {self.handshake_port}")
                break
            except socket.error as e:
                print(f"Port {port} is in use, trying the next port.")

        while self.running:
            try:
                data, addr = handshake_socket.recvfrom(1024)
                message = data.decode('utf-8')
                if message == "REQUEST_CONNECTION_CLIENT":
                    response = f"{self.get_ip_address()}:{self.data_port}"
                    handshake_socket.sendto(response.encode('utf-8'), addr)
                    print(f"Handshake response sent to {addr}: {response}")
                elif message == "REQUEST_CONNECTION_INACTIVE_SERVER":
                    response = f"{self.get_ip_address()}:{self.data_port}:{self.next_server_id}"
                    self.next_server_id += 1
                    handshake_socket.sendto(response.encode('utf-8'), addr)
                    print(f"Handshake response sent to {addr}: {response}")
            except Exception as e:
                print(f"Error during handshake: {e}")
                break

    def get_ip_address(self):
        hostname = socket.gethostname()
        ip_address = socket.gethostbyname(hostname)
        return ip_address

    def accept_connections(self):
        while self.running:
            client_socket, client_address = self.server_socket.accept()
            print(f"Accepted connection from {client_address}")
            with self.lock:
                self.clients[client_address] = client_socket
            threading.Thread(target=self.handle_client, args=(client_socket, client_address)).start()

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
        except KeyboardInterrupt:
            self.stop_server()

class InactiveServer:
    def __init__(self, server_ip, handshake_ports=[60000, 60001, 60002]):
        self.server_ip = server_ip
        self.handshake_ports = handshake_ports
        self.data_port = None
        self.socket = None
        self.connected = False
        self.heartbeat_interval = 1
        self.heartbeat_thread = None
        self.receive_thread = None
        self.terminate = False

    def connect_to_server(self):
        self.perform_handshake()
        while not self.connected:
            try:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.connect((self.server_ip, self.data_port))
                self.connected = True
                self.terminate = False
                print(f"Connected to server at ({self.server_ip}, {self.data_port})")
                print("Waiting for server to fail")
                self.start_heartbeat()
                self.start_receiving()
            except socket.error as e:
                print(f"Error connecting to server: {e}. Retrying in 1 seconds...")
                time.sleep(1)

    def perform_handshake(self):
        global server_id
        for port in self.handshake_ports:
            handshake_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            handshake_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            handshake_socket.settimeout(0.1)
            handshake_message = "REQUEST_CONNECTION_INACTIVE_SERVER"
            handshake_socket.sendto(handshake_message.encode('utf-8'), ('<broadcast>', port))
            print(f"Sent handshake request to broadcast address on port {port}")
            try:
                response, server_address = handshake_socket.recvfrom(1024)
                server_info = response.decode('utf-8')
                self.server_ip, self.data_port, server_id = server_info.split(':')
                self.data_port = int(self.data_port)
                server_id = int(server_id)
                print(f"Received handshake response from {server_address}: IP {self.server_ip}, Port {self.data_port}, Server ID {server_id}")
                return
            except socket.timeout:
                print(f"Handshake response timed out on port {port}. Trying next port...")
        if server_id is None:
            print("Failed to receive handshake response from all ports. Retrying...")
            time.sleep(0.1)
            self.perform_handshake()
        else:
            print("Failed to receive handshake response from all ports. Becoming new leader")
            server_id = 0
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
                self.connect_to_server()

    def start_receiving(self):
        if self.connected:
            self.receive_thread = threading.Thread(target=self.receive_data)
            self.receive_thread.start()

    def receive_data(self):
        global is_leader
        while self.connected and not self.terminate:
            try:
                data = self.socket.recv(1024)
                if data:
                    message = data.decode('utf-8')
                    if message != "HEARTBEAT_ACK":
                        print(f"Message from server: {message}")
                else:
                    print("No heartbeat received. Starting Leader election")
                    self.election()
            except socket.error as e:
                print(f"Error receiving data: {e}")
                self.connected = False
                self.cleanup()
                self.connect_to_server()

    def cleanup(self):
        self.terminate = True
        if self.socket:
            self.socket.close()
        if self.heartbeat_thread and threading.current_thread() != self.heartbeat_thread:
            self.heartbeat_thread.join()
        if self.receive_thread and threading.current_thread() != self.receive_thread:
            self.receive_thread.join()

    def run(self):
        self.connect_to_server()

    def election(self):
        global is_leader
        global server_id
        self.connected = False
        self.cleanup()
        if server_id == 0:
            is_leader = True
            application()
        else:
            is_leader = False
            time.sleep(server_id)
            server_ip = "255.255.255.255"  # Broadcast IP address for handshake
            client = InactiveServer(server_ip)
            client.run()

def application():
    if is_leader:
        server = Server()
        server.run()
    else:
        server_ip = "255.255.255.255"  # Broadcast IP address for handshake
        client = InactiveServer(server_ip)
        client.run()

if __name__ == "__main__":
    if input("Leader? Please enter y/n: ").lower() == "y":
        is_leader = True
    else:
        is_leader = False
    application()