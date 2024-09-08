import socket
import threading
import time
import random
import uuid

# Funktion um den einzigartigen Identifier zu erstellen
def generate_identifier():
    mac = uuid.getnode()  # MAC-Adresse holen
    timestamp = int(time.time())  # Zeitstempel
    random_number = random.randint(0, 9999)  # Zufällige Zahl
    return f"{mac}-{timestamp}-{random_number}"

class Server:
    def __init__(self, port):
        self.port = port
        self.identifier = generate_identifier()  # Eindeutiger Identifier
        self.is_leader = False
        self.leader = None
        self.peers = {}

    # Server-Discovery via UDP-Broadcast
    def broadcast_presence(self):
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while True:
            message = f"Server {self.identifier} present"
            udp_socket.sendto(message.encode('utf-8'), ('<broadcast>', self.port))
            time.sleep(5)  # Alle 5 Sekunden Broadcast senden

    # UDP-Empfänger, um andere Server zu entdecken
    def listen_for_peers(self):
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.bind(("", self.port))
        while True:
            message, addr = udp_socket.recvfrom(1024)
            msg = message.decode('utf-8')
            sender_id = msg.split(" ")[1]
            if sender_id != self.identifier:  # Sich selbst ignorieren
                self.peers[sender_id] = time.time()
                print(f"Discovered peer: {sender_id}")

    # Leader-Election auf Basis des höchsten Identifiers
    def elect_leader(self):
        while True:
            time.sleep(10)  # Alle 10 Sekunden eine neue Wahl
            if not self.leader or self.leader not in self.peers:
                self.leader = max(self.peers.keys(), default=self.identifier)
                self.is_leader = self.leader == self.identifier
                if self.is_leader:
                    print(f"I am the leader: {self.identifier}")
                else:
                    print(f"Leader is: {self.leader}")

    # Heartbeat, um die anderen Server zu prüfen
    def heartbeat(self):
        while True:
            time.sleep(3)  # Alle 3 Sekunden Heartbeat
            current_time = time.time()
            for peer, last_seen in list(self.peers.items()):
                if current_time - last_seen > 10:  # Wenn ein Server länger als 10 Sekunden nicht gesehen wurde
                    print(f"Peer {peer} is offline")
                    del self.peers[peer]

    # Startet alle Funktionen in separaten Threads
    def start(self):
        threading.Thread(target=self.broadcast_presence).start()
        threading.Thread(target=self.listen_for_peers).start()
        threading.Thread(target=self.elect_leader).start()
        threading.Thread(target=self.heartbeat).start()

# Liste von Ports
ports = [12345, 12346, 12347, 12348, 12349]

if __name__ == "__main__":
    for port in ports:
        print(f"Starting server on port: {port}")
        server = Server(port=port)
        threading.Thread(target=server.start).start()
