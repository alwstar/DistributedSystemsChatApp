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
leaderAddress = None
currentName = None
tcpSocket = None

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

def discoverLeader():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udpSocket:
        udpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udpSocket.bind(('', SERVER_UDP_PORT))

        while not shutdownEvent.is_set():
            message, serverAddr = udpSocket.recvfrom(BUFFER_SIZE)
            messageType, data = parseXmlMessage(message)
            if messageType == "server_discovery":
                serverIp = serverAddr[0]
                serverTcpPort = int(data['server_port'])
                print(f"Discovered server at {serverIp} on port {serverTcpPort}")
                return serverIp, serverTcpPort

def sendMessageToServer(messageType, **kwargs):
    global tcpSocket
    try:
        message = createXmlMessage(messageType, **kwargs)
        tcpSocket.send(message)
    except ConnectionError:
        print("Connection to the server lost. Attempting to reconnect...")
        reconnectToServer()

def receiveMessages():
    global leaderAddress, tcpSocket
    while not shutdownEvent.is_set():
        try:
            message = tcpSocket.recv(BUFFER_SIZE)
            if not message:
                break

            messageType, data = parseXmlMessage(message)

            if messageType == "leader_announcement":
                leaderAddress = (data['leader_ip'], data['leader_id'])
                print(f"New leader is {leaderAddress[0]} with ID {leaderAddress[1]}")
            elif messageType == "chat_message":
                print(f"{data['sender']}: {data['content']}")
            else:
                print(f"Received unknown message type: {messageType}")

        except Exception as e:
            print(f"Error receiving message: {e}")
            break

    if not shutdownEvent.is_set():
        print("Connection to the server lost. Attempting to reconnect...")
        reconnectToServer()

def reconnectToServer():
    global tcpSocket
    while not shutdownEvent.is_set():
        try:
            serverIp, serverTcpPort = discoverLeader()
            newSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            newSocket.connect((serverIp, serverTcpPort))
            tcpSocket = newSocket
            print("Reconnected to the server.")
            threading.Thread(target=receiveMessages).start()
            if currentName:
                sendMessageToServer("set_name", name=currentName)
            return
        except Exception as e:
            print(f"Failed to reconnect: {e}")
            time.sleep(5)

def main():
    global currentName, tcpSocket

    currentName = input("Enter your name: ")

    try:
        serverIp, serverTcpPort = discoverLeader()
        tcpSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcpSocket.connect((serverIp, serverTcpPort))
        print("Connected to the server.")

        sendMessageToServer("set_name", name=currentName)

        threading.Thread(target=receiveMessages).start()

        while True:
            message = input()
            if message.lower() == 'quit':
                print("Disconnecting client...")
                shutdownEvent.set()
                tcpSocket.close()
                break
            sendMessageToServer("chat_message", name=currentName, content=message)

    except Exception as e:
        print(f"An error occurred: {e}")

    print("Client disconnected.")

if __name__ == "__main__":
    main()
