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
    def __init__(self, send_port, receive_port):
        self.send_port = send_port
        self.receive_port = receive_port
        self.identifier = generate_identifier()  # Eindeutiger Identifier
        self.is_leader = False
        self.leader = self.identifier  # Am Anfang ist jeder Server sein eigener Leader
        self.peers = {}  # {Identifier: Zeitstempel}
        self.leader_election_done = False

    # Server-Discovery via UDP-Broadcast
    def broadcast_presence(self):
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        while True:
            message = f"{self.identifier}|{self.leader}"  # Sende Identifier und momentanen Leader
            for peer_receive_port in [12346, 12348, 12350]:  # Die Empfangsports der anderen Server
                udp_socket.sendto(message.encode('utf-8'), ('127.0.0.1', peer_receive_port))
                print(f"Broadcasting presence: {self.identifier} to port {peer_receive_port}")
            time.sleep(5)  # Alle 5 Sekunden Broadcast senden

    # UDP-Empfänger, um andere Server zu entdecken
    def listen_for_peers(self):
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.bind(("127.0.0.1", self.receive_port))  # Lausche auf dem richtigen Empfangsport
        print(f"Listening for peers on port {self.receive_port}")
        
        while True:
            message, addr = udp_socket.recvfrom(1024)
            print(f"Received message: {message.decode('utf-8')} from {addr}")
            received_identifier, received_leader = message.decode('utf-8').split("|")
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
    # Ports für Senden und Empfangen
    ports = [(12345, 12346), (12347, 12348), (12349, 12350)]  # Unterschiedliche Ports für Senden und Empfangen

    for send_port, receive_port in ports:
        print(f"Starting server with send port {send_port} and receive port {receive_port}")
        server = Server(send_port=send_port, receive_port=receive_port)
        threading.Thread(target=server.start).start()
