import socket
import threading
import time
import sys
import xml.etree.ElementTree as ET
import random

# Constants
UDP_PORT = 42000
BUFFER_SIZE = 1024
TCP_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 6000
HEARTBEAT_INTERVAL = 5
HEARTBEAT_TIMEOUT = 15

# Global variables
servers = {}  # Dictionary to store server information (address: unique_id)
clients = {}  # Dictionary to store client information (socket: (address, name))
leader = None  # Current leader (address, unique_id)
isActive = True
unique_id = None
shutdownEvent = threading.Event()

def generate_unique_id():
    return f"{int(time.time())}-{random.randint(0, 9999):04d}"

def create_xml_message(message_type, **kwargs):
    root = ET.Element("message")
    ET.SubElement(root, "type").text = message_type
    for key, value in kwargs.items():
        ET.SubElement(root, key).text = str(value)
    return ET.tostring(root)

def parse_xml_message(xml_string):
    root = ET.fromstring(xml_string)
    message_type = root.find("type").text
    data = {child.tag: child.text for child in root if child.tag != "type"}
    return message_type, data

def broadcast_server_presence():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while not shutdownEvent.is_set():
            message = create_xml_message("server_presence", port=str(TCP_PORT), unique_id=unique_id)
            udp_socket.sendto(message, ('<broadcast>', UDP_PORT))
            print(f"Broadcasted presence: {message}")  # Debug print
            time.sleep(5)

def discover_servers():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp_socket.bind(('', UDP_PORT))
        udp_socket.settimeout(1)
        
        while not shutdownEvent.is_set():
            try:
                message, addr = udp_socket.recvfrom(BUFFER_SIZE)
                print(f"Received message: {message} from {addr}")  # Debug print
                message_type, data = parse_xml_message(message)
                if message_type == "server_presence" and addr[0] != socket.gethostbyname(socket.gethostname()):
                    server_addr = (addr[0], int(data['port']))
                    servers[server_addr] = data['unique_id']
                    print(f"Discovered server: {server_addr}, ID: {data['unique_id']}")
                    if not leader:
                        start_election()
            except socket.timeout:
                print("No messages received in the last second")  # Debug print
                pass


def start_election():
    global leader
    if not servers:
        leader = (socket.gethostbyname(socket.gethostname()), TCP_PORT), unique_id
        print(f"I am the leader: {leader}")
    else:
        candidates = list(servers.items()) + [((socket.gethostbyname(socket.gethostname()), TCP_PORT), unique_id)]
        leader = max(candidates, key=lambda x: x[1])
        print(f"New leader elected: {leader}")
    announce_leader()

def announce_leader():
    leader_message = create_xml_message("leader_announcement", leader_ip=leader[0][0], leader_port=str(leader[0][1]), leader_id=leader[1])
    for server_addr in servers:
        send_tcp_message(server_addr, leader_message)

def send_tcp_message(addr, message):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect(addr)
            s.sendall(message)
    except Exception as e:
        print(f"Error sending message to {addr}: {e}")

def handle_client(client_socket, addr):
    global clients
    try:
        name_message = client_socket.recv(BUFFER_SIZE)
        _, name_data = parse_xml_message(name_message)
        client_name = name_data['name']
        clients[client_socket] = (addr, client_name)
        print(f"New client connected: {client_name} at {addr}")
        
        while not shutdownEvent.is_set():
            message = client_socket.recv(BUFFER_SIZE)
            if not message:
                break
            message_type, data = parse_xml_message(message)
            if message_type == "chat_message":
                broadcast_chat_message(client_name, data['content'])
    except Exception as e:
        print(f"Error handling client {addr}: {e}")
    finally:
        client_socket.close()
        del clients[client_socket]
        print(f"Client disconnected: {client_name} at {addr}")

def broadcast_chat_message(sender_name, content):
    message = create_xml_message("chat_message", sender=sender_name, content=content)
    for client_socket in clients:
        try:
            client_socket.send(message)
        except Exception as e:
            print(f"Error sending message to client: {e}")

def heartbeat():
    while not shutdownEvent.is_set():
        for server_addr in list(servers.keys()):
            try:
                send_tcp_message(server_addr, create_xml_message("heartbeat"))
            except Exception as e:
                print(f"Server {server_addr} is unreachable: {e}")
                del servers[server_addr]
                if leader and leader[0] == server_addr:
                    print("Leader is dead. Starting new election.")
                    start_election()
        time.sleep(HEARTBEAT_INTERVAL)

def main():
    global unique_id, TCP_PORT

    if len(sys.argv) > 1:
        try:
            TCP_PORT = int(sys.argv[1])
        except ValueError:
            print("Invalid port number. Using default port:", TCP_PORT)

    unique_id = generate_unique_id()
    print(f"Server starting with unique ID: {unique_id}")

    broadcast_thread = threading.Thread(target=broadcast_server_presence, daemon=True)
    discover_thread = threading.Thread(target=discover_servers, daemon=True)
    heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)

    broadcast_thread.start()
    discover_thread.start()
    heartbeat_thread.start()

    print("Started broadcast, discover, and heartbeat threads")  # Debug print

    # ... (rest of the main function remains the same)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Server interrupted. Shutting down.")
        shutdownEvent.set()