import socket
import threading
import sys
import time
import xml.etree.ElementTree as ET

# Constants
SERVER_UDP_PORT = 42000
BUFFER_SIZE = 1024

# Global variables
shutdownEvent = threading.Event()
serverAddr = None
clientName = None

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

def locate_server():
    global serverAddr
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp_socket.bind(('', SERVER_UDP_PORT))

        while not shutdownEvent.is_set():
            message, addr = udp_socket.recvfrom(BUFFER_SIZE)
            message_type, data = parse_xml_message(message)
            if message_type == "server_presence":
                serverAddr = (addr[0], int(data['port']))
                print(f"Located server at {serverAddr[0]} on port {serverAddr[1]}")
                return

def receive_messages(tcp_socket):
    while not shutdownEvent.is_set():
        try:
            message = tcp_socket.recv(BUFFER_SIZE)
            if not message:
                break

            message_type, data = parse_xml_message(message)

            if message_type == "chat_message":
                print(f"{data['sender']}: {data['content']}")
            elif message_type == "leader_announcement":
                print(f"New leader announced: {data['leader_ip']}:{data['leader_port']}")
            else:
                print(f"Received unknown message type: {message_type}")

        except Exception as e:
            print(f"Error receiving message: {e}")
            break

    if not shutdownEvent.is_set():
        print("Connection to the server lost. Attempting to reconnect...")
        reconnect()

def reconnect():
    global serverAddr
    while not shutdownEvent.is_set():
        try:
            locate_server()
            new_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            new_socket.connect(serverAddr)
            print("Reconnected to the server.")
            new_socket.send(create_xml_message("client_name", name=clientName))
            threading.Thread(target=receive_messages, args=(new_socket,), daemon=True).start()
            return new_socket
        except Exception as e:
            print(f"Failed to reconnect: {e}")
            time.sleep(5)

def main():
    global clientName

    clientName = input("Enter your name: ")

    locate_server()

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket:
            tcp_socket.connect(serverAddr)
            print("Connected to the server.")

            tcp_socket.send(create_xml_message("client_name", name=clientName))

            threading.Thread(target=receive_messages, args=(tcp_socket,), daemon=True).start()

            while not shutdownEvent.is_set():
                message = input()
                if message.lower() == 'quit':
                    break
                tcp_socket.send(create_xml_message("chat_message", content=message))

    except Exception as e:
        print(f"An error occurred: {e}")

    print("Client disconnected.")
    shutdownEvent.set()

if __name__ == "__main__":
    main()