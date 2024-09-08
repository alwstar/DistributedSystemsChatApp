import socket
import threading
import sys
import time
import xml.etree.ElementTree as ET

BUFFER_SIZE = 1024
DEFAULT_PORT = 7000  # Default client port

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

def sendMessage(clientSocket, clientId):
    while True:
        message = input(f"[{clientId}] > ")
        if message.strip().lower() == "quit":
            break
        chatMessage = createXmlMessage("chatroom", client_id=clientId, content=message)
        clientSocket.send(chatMessage)

    clientSocket.close()

def discoverLeader():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udpSocket:
        udpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        udpSocket.settimeout(5)  # Timeout after 5 seconds if no response
        udpSocket.sendto(b"DiscoverLeader", ('<broadcast>', UDP_PORT))

        try:
            response, serverAddr = udpSocket.recvfrom(BUFFER_SIZE)
            responseStr = response.decode()
            if responseStr.startswith("Leader:"):
                _, leaderIp, leaderPort = responseStr.split(':')
                return leaderIp, int(leaderPort)
        except socket.timeout:
            print("No leader response received.")
            return None, None


def main():
    clientId = input("Enter your client ID: ")

    # Discover the leader
    leader_ip, leader_port = discoverLeader()
    if leader_ip is None:
        print("Failed to discover the leader. Exiting.")
        return

    print(f"Discovered leader at {leader_ip}:{leader_port}")

    # Connect to the leader
    clientSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    clientSocket.connect((leader_ip, leader_port))

    # Send initial client ID to the leader
    clientIdMessage = createXmlMessage("client_id", client_id=clientId)
    clientSocket.send(clientIdMessage)

    # Start a thread to receive messages from the server
    threading.Thread(target=receiveMessages, args=(clientSocket,), daemon=True).start()

    # Start sending messages
    sendMessage(clientSocket, clientId)

