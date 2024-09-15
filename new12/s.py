import socket
import threading
import random
import time
import uuid

is_leader = False
server_id = None
server_uuid = uuid.uuid4()

# Server class to handle the connection and communication
class Server:
    def __init__(self, handshake_ports=[60000, 60001, 60002, 60003]):
        print(f"My UUID is {server_uuid}")
        self.handshake_ports = handshake_ports
        self.handshake_port = None
        self.data_port = self.get_random_port(49152, 59999)
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind(('0.0.0.0', self.data_port))
        self.server_socket.listen(5)
        self.clients = {}
        self.lock = threading.Lock()
        self.running = True
        self.next_server_id = 0

    def get_random_port(self, start, end):
        return random.randint(start, end)

    def start_server(self):
        print(f"Server listening for connections on {self.data_port}")
        accept_thread = threading.Thread(target=self.accept_connections)
        accept_thread.start()
        self.listen_for_handshake()

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
                    response = f"{self.get_ip_address()}:{self.data_port}"
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
        print(f"My UUID is {server_uuid}")
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
                self.server_ip, self.data_port = server_info.split(':')
                self.data_port = int(self.data_port)
                print(f"Received handshake response from {server_address}: IP {self.server_ip}, Port {self.data_port}")
                return
            except socket.timeout:
                print(f"Handshake response timed out on port {port}. Trying next port...")
        print("Failed to receive handshake response from all ports. Starting new election.")
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
        global server_uuid
        self.connected = False
        self.cleanup()
        # Re-run the discovery and election process
        application()



class Discovery:
    def __init__(self, discovery_port=50000, discovery_time=15):
        self.discovery_port = discovery_port
        self.discovery_time = discovery_time
        self.received_uuids = []
        self.stop_event = threading.Event()
    
    def broadcast_uuid(self, server_uuid):
        discovery_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        message = str(server_uuid).encode('utf-8')
        end_time = time.time() + self.discovery_time
        while time.time() < end_time and not self.stop_event.is_set():
            discovery_socket.sendto(message, ('<broadcast>', self.discovery_port))
            time.sleep(1)  # Send every second
        discovery_socket.close()
    
    def listen_for_uuids(self, server_uuid):
        listener_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        listener_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener_socket.bind(('', self.discovery_port))
        listener_socket.settimeout(1)
        end_time = time.time() + self.discovery_time
        while time.time() < end_time and not self.stop_event.is_set():
            try:
                data, addr = listener_socket.recvfrom(1024)
                received_uuid = uuid.UUID(data.decode('utf-8'))
                if received_uuid != server_uuid and received_uuid not in self.received_uuids:
                    self.received_uuids.append(received_uuid)
                    print(f"Discovered server with UUID: {received_uuid}")
            except socket.timeout:
                continue
        listener_socket.close()
    
    def start_discovery(self, server_uuid):
        broadcaster = threading.Thread(target=self.broadcast_uuid, args=(server_uuid,))
        listener = threading.Thread(target=self.listen_for_uuids, args=(server_uuid,))
        broadcaster.start()
        listener.start()
        broadcaster.join()
        listener.join()
        self.stop_event.set()
        return self.received_uuids






def application():
    if is_leader:
        server = Server()
        server.run()
    else:
        server_ip = "255.255.255.255"  # Broadcast IP address for handshake
        client = InactiveServer(server_ip)
        client.run()

if __name__ == "__main__":
    application()