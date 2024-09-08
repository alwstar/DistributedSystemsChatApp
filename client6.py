import socket
import threading
import time
import sys
import xml.etree.ElementTree as ET

BUFFER_SIZE = 1024
DEFAULT_PORT = 7000  # Default client port for listening to server responses
UDP_PORT = 42000  # UDP port for broadcasting

# Function to create XML messages for communication
def createXmlMessage(messageType, **kwargs):
    root = ET.Element("message")
    ET.SubElement(root, "type").text = messageType
    for key, value in kwargs.items():
        ET.SubElement(root, key).text = str(value)
    return ET.tostring(root)

def parseXmlMessage(xmlString):
    root = ET.fromstring(xmlString)
    messageType = root.find("type").text
    data = {child.tag: child.text for child in root if child.tag != "type"}
    return messageType, data

# Discover the leader using UDP broadcast with retries
def discoverLeader(retry_attempts=5, timeout=5):
    for attempt in range(retry_attempts):
        print(f"Attempting to discover leader (Attempt {attempt + 1}/{retry_attempts})")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udpSocket:
            udpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            udpSocket.settimeout(timeout)
            udpSocket.sendto(b"DiscoverLeader", ('<broadcast>', UDP_PORT))

            try:
                response, serverAddr = udpSocket.recvfrom(BUFFER_SIZE)
                responseStr = response.decode()
                if responseStr.startswith("Leader:"):
                    _, leaderIp, leaderPort = responseStr.split(':')
                    print(f"Leader discovered at {leaderIp}:{leaderPort}")
                    return leaderIp, int(leaderPort)
            except socket.timeout:
                print("No leader response received, retrying...")
    
    print("Failed to discover leader after multiple attempts.")
    return None, None

# Attempt to connect to the leader server
def connectToLeader(leader_ip, leader_port, retry_attempts=5, timeout=5):
    for attempt in range(retry_attempts):
        try:
            print(f"Attempting to connect to leader at {leader_ip}:{leader_port} (Attempt {attempt + 1}/{retry_attempts})")
            clientSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            clientSocket.connect((leader_ip, leader_port))
            print(f"Connected to leader at {leader_ip}:{leader_port}")
            return clientSocket
        except Exception as e:
            print(f"Error connecting to leader: {e}. Retrying in {timeout} seconds...")
            time.sleep(timeout)

    print("Failed to connect to leader after multiple attempts.")
    return None

# Thread for receiving messages from the server
def receiveMessages(clientSocket):
    while True:
        try:
            message = clientSocket.recv(BUFFER_SIZE)
            if message:
                messageType, data = parseXmlMessage(message)
                if messageType == "chatroom":
                    sender = data.get('client_id', 'Unknown')
                    content = data.get('content', '')
                    print(f"[{sender}]: {content}")
        except Exception as e:
            print(f"Error receiving message: {e}")
            break

# Send messages to the server and handle disconnection/reconnection
def sendMessage(clientSocket, clientId, leader_ip, leader_port):
    while True:
        try:
            message = input(f"[{clientId}] > ")
            if message.strip().lower() == "quit":
                break
            chatMessage = createXmlMessage("chatroom", client_id=clientId, content=message)
            clientSocket.send(chatMessage)
        except Exception as e:
            print(f"Connection lost: {e}")
            print("Attempting to reconnect to leader...")
            clientSocket = connectToLeader(leader_ip, leader_port)
            if clientSocket is None:
                print("Failed to reconnect to leader. Exiting.")
                break

    clientSocket.close()

def main():
    clientId = input("Enter your client ID: ")

    # Discover the leader
    leader_ip, leader_port = discoverLeader()
    if leader_ip is None:
        print("Failed to discover the leader. Exiting.")
        return

    # Connect to the leader
    clientSocket = connectToLeader(leader_ip, leader_port)
    if clientSocket is None:
        print("Could not connect to the leader. Exiting.")
        return

    # Send initial client ID to the leader
    clientIdMessage = createXmlMessage("client_id", client_id=clientId)
    clientSocket.send(clientIdMessage)

    # Start a thread to receive messages from the server
    threading.Thread(target=receiveMessages, args=(clientSocket,), daemon=True).start()

    # Start sending messages and handle potential disconnections
    sendMessage(clientSocket, clientId, leader_ip, leader_port)

if __name__ == "__main__":
    main()
