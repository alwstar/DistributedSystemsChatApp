import socket
import threading
import time
import json
import struct
import random
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Constants
BUFFER_SIZE = 1024
MULTICAST_GROUP = '239.0.0.1'
MULTICAST_PORT = 5000
SERVER_PORT = 5001
DISCOVERY_PORT = 5002
LCR_PORT = 5003
HEARTBEAT_INTERVAL = 5
LEADER_TIMEOUT = 15

class ChatServer:
    def __init__(self):
        self.id = f"{int(time.time())}-{random.randint(0, 9999):04d}"
        self.ip = socket.gethostbyname(socket.gethostname())
        self.known_servers = set()
        self.chat_rooms = {}
        self.is_leader = False
        self.leader_id = None
        self.last_heartbeat = 0
        self.lock = threading.Lock()
        self.shutdown_event = threading.Event()

    def start(self):
        threading.Thread(target=self.server_discovery).start()
        threading.Thread(target=self.lcr_listener).start()
        threading.Thread(target=self.heartbeat_listener).start()
        threading.Thread(target=self.client_handler).start()
        threading.Thread(target=self.leader_check).start()

        self.initiate_leader_election()

    def server_discovery(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.bind(('', DISCOVERY_PORT))
            while not self.shutdown_event.is_set():
                try:
                    data, addr = s.recvfrom(BUFFER_SIZE)
                    if data == b"SERVER_DISCOVERY":
                        s.sendto(self.id.encode(), addr)
                    elif addr[0] != self.ip:
                        self.known_servers.add((addr[0], data.decode()))
                        logging.info(f"Discovered server: {addr[0]}")
                except Exception as e:
                    logging.error(f"Error in server discovery: {e}")

    def initiate_leader_election(self):
        self.known_servers.add((self.ip, self.id))
        sorted_servers = sorted(self.known_servers, key=lambda x: x[1])
        next_server = sorted_servers[(sorted_servers.index((self.ip, self.id)) + 1) % len(sorted_servers)]
        
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.sendto(json.dumps({"type": "ELECTION", "id": self.id}).encode(), (next_server[0], LCR_PORT))
        logging.info("Initiated leader election")

    def lcr_listener(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.bind((self.ip, LCR_PORT))
            while not self.shutdown_event.is_set():
                try:
                    data, addr = s.recvfrom(BUFFER_SIZE)
                    message = json.loads(data.decode())
                    if message["type"] == "ELECTION":
                        if message["id"] > self.id:
                            next_server = self.get_next_server()
                            s.sendto(data, (next_server[0], LCR_PORT))
                        elif message["id"] < self.id:
                            next_server = self.get_next_server()
                            s.sendto(json.dumps({"type": "ELECTION", "id": self.id}).encode(), (next_server[0], LCR_PORT))
                        else:
                            self.become_leader()
                    elif message["type"] == "LEADER":
                        self.leader_id = message["id"]
                        self.is_leader = (self.id == self.leader_id)
                        if not self.is_leader:
                            next_server = self.get_next_server()
                            s.sendto(data, (next_server[0], LCR_PORT))
                        logging.info(f"New leader elected: {self.leader_id}")
                except Exception as e:
                    logging.error(f"Error in LCR listener: {e}")

    def get_next_server(self):
        sorted_servers = sorted(self.known_servers, key=lambda x: x[1])
        return sorted_servers[(sorted_servers.index((self.ip, self.id)) + 1) % len(sorted_servers)]

    def become_leader(self):
        self.is_leader = True
        self.leader_id = self.id
        next_server = self.get_next_server()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.sendto(json.dumps({"type": "LEADER", "id": self.id}).encode(), (next_server[0], LCR_PORT))
        logging.info("Became the leader")

    def heartbeat_listener(self):
        multicast_group = MULTICAST_GROUP
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', MULTICAST_PORT))
        group = socket.inet_aton(multicast_group)
        mreq = struct.pack('4sL', group, socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        
        while not self.shutdown_event.is_set():
            try:
                data, address = sock.recvfrom(BUFFER_SIZE)
                message = json.loads(data.decode())
                if message['type'] == 'HEARTBEAT':
                    self.last_heartbeat = time.time()
                elif message['type'] == 'CHAT_UPDATE' and not self.is_leader:
                    self.chat_rooms = message['chat_rooms']
            except Exception as e:
                logging.error(f"Error in heartbeat listener: {e}")

    def send_heartbeat(self):
        multicast_group = (MULTICAST_GROUP, MULTICAST_PORT)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.2)
            ttl = struct.pack('b', 1)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
            message = json.dumps({
                'type': 'HEARTBEAT',
                'id': self.id,
                'timestamp': time.time()
            })
            sock.sendto(message.encode(), multicast_group)

    def leader_check(self):
        while not self.shutdown_event.is_set():
            if self.is_leader:
                self.send_heartbeat()
                self.replicate_chat_rooms()
            elif time.time() - self.last_heartbeat > LEADER_TIMEOUT:
                logging.info("Leader timeout, initiating new election")
                self.initiate_leader_election()
            time.sleep(HEARTBEAT_INTERVAL)

    def replicate_chat_rooms(self):
        multicast_group = (MULTICAST_GROUP, MULTICAST_PORT)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            ttl = struct.pack('b', 1)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
            message = json.dumps({
                'type': 'CHAT_UPDATE',
                'chat_rooms': self.chat_rooms
            })
            sock.sendto(message.encode(), multicast_group)

    def client_handler(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self.ip, SERVER_PORT))
            s.listen()
            while not self.shutdown_event.is_set():
                try:
                    conn, addr = s.accept()
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
        logging.info("Server shutting down")

if __name__ == "__main__":
    server = ChatServer()
    try:
        server.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.shutdown()