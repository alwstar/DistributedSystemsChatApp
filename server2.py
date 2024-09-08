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
    def __init__(self):
        self.broadcast_port = 50000  # Fester Broadcast-Port
        self.receive_port = random.randint(10000, 60000)  # Zufälliger Empfangsport
        self.identifier = generate_identifier()  # Eindeutiger Identifier
        self.is_leader = False
        self.leader = self.identifier  # Am Anfang ist jeder Server sein eigener Leader
        self.peers = {}  # {Identifier: Zeitstempel}
        self.leader_election_done = False

    # Server-Discovery via UDP-Broadcast
    def broadcast_presence(self):
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while True:
            message = f"{self.identifier}|{self.leader}|{self.receive_port}"  # Sende Identifier und momentanen Leader
            udp_socket.sendto(message.encode('utf-8'), ('<broadcast>', self.broadcast_port))
            print(f"Broadcasting presence: {self.identifier} on receive port {self.receive_port}")
            time.sleep(5)  # Alle 5 Sekunden Broadcast senden

    # UDP-Empfänger, um andere Server zu entdecken
    def listen_for_peers(self):
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.bind(("0.0.0.0", self.receive_port))  # Lausche auf einem zufälligen Empfangsport
        print(f"Listening for peers on port {self.receive_port}")
        
        while True:
            message, addr = udp_socket.recvfrom(1024)
            print(f"Received message: {message.decode('utf-8')} from {addr}")
            received_identifier, received_leader, _ = message.decode('utf-8').split("|")
            if received_identifier != self.identifier:  # Sich selbst ignorieren
                self.peers[received_identifier] = time.time()  # Aktualisiere Peers
                print(f"Discovered peer: {received_identifier}, reported leader: {received_leader}")
                if not self.leader_election_done:
                    self.check_leader(received_identifier)

    # Leader-Election auf Basis des höchsten Identifiers
    def check_leader(self, received_identifier):
        if received_identifier > self.leader:
            self.leader = received_identifier
            print(f"New leader elected: {self.leader}")
        elif received_identifier == self.leader:
            print(f"Leader remains: {self.leader}")

        self.leader_election_done = True

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
        time.sleep(1)  # Füge eine kleine Verzögerung hinzu, um sicherzustellen, dass alles bereit ist
        threading.Thread(target=self.listen_for_peers).start()
        threading.Thread(target=self.heartbeat).start()

# Beispiel zur Nutzung des Servers
if __name__ == "__main__":
    print(f"Starting a new server...")
    server = Server()
    threading.Thread(target=server.start).start()
