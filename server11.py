import socket
import threading
import time
import json
import struct
import random
import logging
import sys

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Constants
BUFFER_SIZE = 1024
MULTICAST_GROUP = '239.0.0.1'
MULTICAST_PORT = 5000
HEARTBEAT_INTERVAL = 5
LEADER_TIMEOUT = 30  # Increased from 15 to 30 seconds
DISCOVERY_TIMEOUT = 20  # New constant for discovery timeout
ELECTION_COOLDOWN = 10  # New constant for election cooldown

class ChatServer:
    def __init__(self, server_port, lcr_port, discovery_port):
        self.id = f"{int(time.time())}-{random.randint(0, 9999):04d}"
        self.ip = '127.0.0.1'  # Use localhost for single machine testing
        self.server_port = server_port
        self.lcr_port = lcr_port
        self.discovery_port = discovery_port
        self.known_servers = set()
        self.chat_rooms = {}
        self.is_leader = False
        self.leader_id = None
        self.last_heartbeat = 0
        self.lock = threading.Lock()
        self.shutdown_event = threading.Event()
        self.discovery_complete = threading.Event()
        self.last_election_time = 0

        # Create and bind sockets
        self.lcr_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.lcr_socket.bind((self.ip, self.lcr_port))

        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client_socket.bind((self.ip, self.server_port))
        self.client_socket.listen()

        self.discovery_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.discovery_socket.bind((self.ip, self.discovery_port))

        # Multicast socket setup
        self.multicast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.multicast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.multicast_socket.bind(('', MULTICAST_PORT))
        group = socket.inet_aton(MULTICAST_GROUP)
        mreq = struct.pack('4sL', group, socket.INADDR_ANY)
        self.multicast_socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    def start(self):
        threading.Thread(target=self.server_discovery).start()
        threading.Thread(target=self.lcr_listener).start()
        threading.Thread(target=self.heartbeat_listener).start()
        threading.Thread(target=self.client_handler).start()
        threading.Thread(target=self.leader_check).start()

        # Wait for initial discovery
        time.sleep(DISCOVERY_TIMEOUT)
        self.discovery_complete.set()

        self.initiate_leader_election()

    def server_discovery(self):
        self.broadcast_discovery()
        start_time = time.time()
        while not self.shutdown_event.is_set():
            try:
                self.discovery_socket.settimeout(1)
                data, addr = self.discovery_socket.recvfrom(BUFFER_SIZE)
                if data == b"SERVER_DISCOVERY":
                    self.discovery_socket.sendto(f"{self.id}:{self.server_port}:{self.lcr_port}".encode(), addr)
                elif addr[0] == self.ip and int(data.split(b':')[1]) != self.server_port:
                    server_id, server_port, lcr_port = data.decode().split(':')
                    self.known_servers.add((self.ip, int(server_port), int(lcr_port), server_id))
                    logging.info(f"Discovered server: {self.ip}:{server_port}")
                
                if time.time() - start_time > DISCOVERY_TIMEOUT and not self.discovery_complete.is_set():
                    self.discovery_complete.set()
                    logging.info("Initial discovery phase complete")
            except socket.timeout:
                continue
            except Exception as e:
                logging.error(f"Error in server discovery: {e}")

    def broadcast_discovery(self):
        discovery_message = b"SERVER_DISCOVERY"
        for port in range(5000, 6000):  # Adjust range as needed
            if port != self.discovery_port:
                try:
                    self.discovery_socket.sendto(discovery_message, (self.ip, port))
                except:
                    pass

    def initiate_leader_election(self):
        if time.time() - self.last_election_time < ELECTION_COOLDOWN:
            logging.info("Election cooldown in effect. Skipping this election initiation.")
            return

        self.last_election_time = time.time()
        self.known_servers.add((self.ip, self.server_port, self.lcr_port, self.id))
        sorted_servers = sorted(self.known_servers, key=lambda x: x[3])
        next_server = sorted_servers[(sorted_servers.index((self.ip, self.server_port, self.lcr_port, self.id)) + 1) % len(sorted_servers)]
        
        message = json.dumps({"type": "ELECTION", "id": self.id}).encode()
        self.lcr_socket.sendto(message, (next_server[0], next_server[2]))
        logging.info("Initiated leader election")

    def lcr_listener(self):
        while not self.shutdown_event.is_set():
            try:
                data, addr = self.lcr_socket.recvfrom(BUFFER_SIZE)
                message = json.loads(data.decode())
                if message["type"] == "ELECTION":
                    if message["id"] > self.id:
                        next_server = self.get_next_server()
                        self.lcr_socket.sendto(data, (next_server[0], next_server[2]))
                    elif message["id"] < self.id:
                        next_server = self.get_next_server()
                        new_message = json.dumps({"type": "ELECTION", "id": self.id}).encode()
                        self.lcr_socket.sendto(new_message, (next_server[0], next_server[2]))
                    else:
                        self.become_leader()
                elif message["type"] == "LEADER":
                    self.leader_id = message["id"]
                    self.is_leader = (self.id == self.leader_id)
                    if not self.is_leader:
                        next_server = self.get_next_server()
                        self.lcr_socket.sendto(data, (next_server[0], next_server[2]))
                    logging.info(f"New leader elected: {self.leader_id}")
            except Exception as e:
                logging.error(f"Error in LCR listener: {e}")

    def get_next_server(self):
        sorted_servers = sorted(self.known_servers, key=lambda x: x[3])
        return sorted_servers[(sorted_servers.index((self.ip, self.server_port, self.lcr_port, self.id)) + 1) % len(sorted_servers)]

    def become_leader(self):
        self.is_leader = True
        self.leader_id = self.id
        next_server = self.get_next_server()
        message = json.dumps({"type": "LEADER", "id": self.id}).encode()
        self.lcr_socket.sendto(message, (next_server[0], next_server[2]))
        logging.info("Became the leader")

    def heartbeat_listener(self):
        while not self.shutdown_event.is_set():
            try:
                self.multicast_socket.settimeout(1)
                data, address = self.multicast_socket.recvfrom(BUFFER_SIZE)
                message = json.loads(data.decode())
                if message['type'] == 'HEARTBEAT':
                    self.last_heartbeat = time.time()
                elif message['type'] == 'CHAT_UPDATE' and not self.is_leader:
                    self.chat_rooms = message['chat_rooms']
            except socket.timeout:
                continue
            except Exception as e:
                logging.error(f"Error in heartbeat listener: {e}")

    def send_heartbeat(self):
        multicast_group = (MULTICAST_GROUP, MULTICAST_PORT)
        message = json.dumps({
            'type': 'HEARTBEAT',
            'id': self.id,
            'timestamp': time.time()
        })
        self.multicast_socket.sendto(message.encode(), multicast_group)

    def leader_check(self):
        while not self.shutdown_event.is_set():
            if self.is_leader:
                self.send_heartbeat()
                self.replicate_chat_rooms()
            elif self.discovery_complete.is_set() and time.time() - self.last_heartbeat > LEADER_TIMEOUT:
                logging.info("Leader timeout, initiating new election")
                self.initiate_leader_election()
            time.sleep(HEARTBEAT_INTERVAL)

    def replicate_chat_rooms(self):
        multicast_group = (MULTICAST_GROUP, MULTICAST_PORT)
        message = json.dumps({
            'type': 'CHAT_UPDATE',
            'chat_rooms': self.chat_rooms
        })
        self.multicast_socket.sendto(message.encode(), multicast_group)

    def client_handler(self):
        while not self.shutdown_event.is_set():
            try:
                conn, addr = self.client_socket.accept()
                threading.Thread(target=self.handle_client, args=(conn, addr)).start()
            except Exception as e:
                logging.error(f"Error accepting client connection: {e}")

    def handle_client(self, conn, addr):
        with conn:
            try:
                data = conn.recv(BUFFER_SIZE)
                message = json.loads(data.decode())
                if message['type'] == 'JOIN':
                    self.join_chat_room(conn, addr, message['room'])
                elif message['type'] == 'SEND':
                    self.send_chat_message(addr, message['room'], message['content'])
            except Exception as e:
                logging.error(f"Error handling client {addr}: {e}")

    def join_chat_room(self, conn, addr, room):
        with self.lock:
            if room not in self.chat_rooms:
                self.chat_rooms[room] = set()
            self.chat_rooms[room].add(addr)
        conn.sendall(b"Joined the chat room")
        if self.is_leader:
            self.replicate_chat_rooms()

    def send_chat_message(self, addr, room, content):
        if room in self.chat_rooms and addr in self.chat_rooms[room]:
            message = f"{addr}: {content}"
            for client in self.chat_rooms[room]:
                if client != addr:
                    try:
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                            s.connect(client)
                            s.sendall(message.encode())
                    except Exception as e:
                        logging.error(f"Error sending message to {client}: {e}")
        else:
            logging.warning(f"Client {addr} not in room {room}")

    def shutdown(self):
        self.shutdown_event.set()
        self.lcr_socket.close()
        self.client_socket.close()
        self.discovery_socket.close()
        self.multicast_socket.close()
        logging.info("Server shutting down")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python server.py <server_port> <lcr_port> <discovery_port>")
        sys.exit(1)

    server_port = int(sys.argv[1])
    lcr_port = int(sys.argv[2])
    discovery_port = int(sys.argv[3])

    server = ChatServer(server_port, lcr_port, discovery_port)
    try:
        server.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.shutdown()