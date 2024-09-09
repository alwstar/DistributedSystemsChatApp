import socket
import threading
import time

class Client:
    def __init__(self, server_ip, handshake_ports=[60000, 60001, 60002, 60003]):
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
        retry_count = 0
        while not self.connected and retry_count < 5:
            if self.perform_handshake():
                try:
                    self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.socket.connect((self.server_ip, self.data_port))
                    self.connected = True
                    self.terminate = False
                    print(f"Connected to server at ({self.server_ip}, {self.data_port})")
                    self.start_heartbeat()
                    self.start_receiving()
                    return
                except socket.error as e:
                    print(f"Error connecting to server: {e}. Retrying...")
            retry_count += 1
            time.sleep(2)
        print("Failed to connect to server after multiple attempts.")

    def perform_handshake(self):
        for port in self.handshake_ports:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as handshake_socket:
                    handshake_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    handshake_socket.settimeout(2)  # Increased timeout
                    handshake_message = "REQUEST_CONNECTION_CLIENT"
                    handshake_socket.sendto(handshake_message.encode('utf-8'), ('<broadcast>', port))
                    print(f"Sent handshake request to broadcast address on port {port}")

                    start_time = time.time()
                    while time.time() - start_time < 5:  # Wait for up to 5 seconds
                        try:
                            response, server_address = handshake_socket.recvfrom(1024)
                            server_info = response.decode('utf-8')
                            self.server_ip, self.data_port = server_info.split(':')
                            self.data_port = int(self.data_port)
                            print(f"Received handshake response from {server_address}: IP {self.server_ip}, Port {self.data_port}")
                            return True
                        except socket.timeout:
                            print(f"No response yet on port {port}, continuing to listen...")
            except Exception as e:
                print(f"Error during handshake on port {port}: {e}")
        print("Failed to receive handshake response from all ports.")
        return False

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
        while self.connected and not self.terminate:
            try:
                data = self.socket.recv(1024)
                if data:
                    message = data.decode('utf-8')
                    if message != "HEARTBEAT_ACK":
                        print(f"Message from server: {message}")
                else:
                    print("No data received, server may have disconnected")
                    self.connected = False
                    self.cleanup()
                    self.connect_to_server()
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

    def send_message(self, message):
        if self.connected:
            try:
                self.socket.sendall(message.encode('utf-8'))
                print(f"Sent message to server: {message}")
            except socket.error as e:
                print(f"Error sending message: {e}")
                self.connected = False
                self.cleanup()
                self.connect_to_server()

    def run(self):
        try:
            self.connect_to_server()
            if not self.connected:
                print("Failed to connect to any server. Exiting.")
                return
            while True:
                user_input = input("Enter message to send to server (or 'exit' to quit): ")
                if user_input.lower() == 'exit':
                    break
                self.send_message(user_input)
        except KeyboardInterrupt:
            print("\nClient shutting down...")
        finally:
            self.cleanup()
            print("Client shutdown complete.")

if __name__ == "__main__":
    server_ip = "255.255.255.255"  # Broadcast IP address for handshake
    client = Client(server_ip)
    client.run()