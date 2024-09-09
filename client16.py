import socket
import threading
import time

CLIENT_HANDSHAKE_PORTS = [60000, 60001, 60002, 60003]
LEADER_HEARTBEAT_TIMEOUT = 12
RECONNECTION_DELAY = 5

class Client:
    def __init__(self):
        self.leader_ip = None
        self.leader_port = None
        self.socket = None
        self.connected = False
        self.heartbeat_interval = 1
        self.heartbeat_thread = None
        self.receive_thread = None
        self.terminate = False
        self.last_leader_heartbeat = time.time()

    def listen_for_leader(self):
        leader_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        leader_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        leader_socket.bind(('', CLIENT_HANDSHAKE_PORTS[0]))

        while not self.terminate:
            try:
                data, addr = leader_socket.recvfrom(1024)
                message = data.decode('utf-8')
                if message.startswith("LEADER:"):
                    _, leader_id, new_leader_ip, new_leader_port = message.split(':')
                    new_leader_port = int(new_leader_port)
                    if (new_leader_ip, new_leader_port) != (self.leader_ip, self.leader_port):
                        print(f"New leader detected: {new_leader_ip}:{new_leader_port}")
                        self.leader_ip = new_leader_ip
                        self.leader_port = new_leader_port
                        if self.connected:
                            self.reconnect_to_leader()
                        else:
                            self.connect_to_leader()
            except Exception as e:
                print(f"Error listening for leader: {e}")

    def connect_to_leader(self):
        if not self.leader_ip or not self.leader_port:
            print("No leader information available. Waiting for leader broadcast...")
            return

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.leader_ip, self.leader_port))
            self.connected = True
            self.terminate = False
            print(f"Connected to leader at ({self.leader_ip}, {self.leader_port})")
            self.start_heartbeat()
            self.start_receiving()
        except socket.error as e:
            print(f"Error connecting to leader: {e}. Will retry on next leader broadcast.")
            self.connected = False
            time.sleep(RECONNECTION_DELAY)

    def reconnect_to_leader(self):
        print("Reconnecting to new leader...")
        self.cleanup()
        time.sleep(RECONNECTION_DELAY)
        self.connect_to_leader()

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
                    if message == "LEADER_HEARTBEAT":
                        self.last_leader_heartbeat = time.time()
                    elif message != "HEARTBEAT_ACK":
                        print(f"Message from leader: {message}")
                else:
                    print("No data received, leader may have disconnected")
                    self.connected = False
            except socket.error as e:
                print(f"Error receiving data: {e}")
                self.connected = False

    def monitor_leader_heartbeat(self):
        while not self.terminate:
            if self.connected and time.time() - self.last_leader_heartbeat > LEADER_HEARTBEAT_TIMEOUT:
                print("Leader heartbeat timeout. Disconnecting and waiting for new leader...")
                self.connected = False
                self.cleanup()
            time.sleep(1)

    def cleanup(self):
        self.connected = False
        if self.socket:
            self.socket.close()
        if self.heartbeat_thread and threading.current_thread() != self.heartbeat_thread:
            self.heartbeat_thread.join()
        if self.receive_thread and threading.current_thread() != self.receive_thread:
            self.receive_thread.join()

    def send_message(self, message):
        if self.connected:
            try:
                self.socket.sendall(message.encode('utf-8'))
                print(f"Sent message to leader: {message}")
            except socket.error as e:
                print(f"Error sending message: {e}")
                self.connected = False

    def run(self):
        leader_listener_thread = threading.Thread(target=self.listen_for_leader, daemon=True)
        leader_listener_thread.start()

        heartbeat_monitor_thread = threading.Thread(target=self.monitor_leader_heartbeat, daemon=True)
        heartbeat_monitor_thread.start()

        try:
            while True:
                if self.connected:
                    user_input = input("Enter message to send to leader (or 'exit' to quit): ")
                    if user_input.lower() == 'exit':
                        break
                    self.send_message(user_input)
                else:
                    print("Not connected to a leader. Waiting for leader broadcast...")
                    time.sleep(5)
        except KeyboardInterrupt:
            print("\nClient shutting down...")
        finally:
            self.terminate = True
            self.cleanup()
            print("Client shutdown complete.")

if __name__ == "__main__":
    client = Client()
    client.run()