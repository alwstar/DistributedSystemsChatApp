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

# Global variables
connectedServers = {}  # Dictionary to store server information (socket, address, unique_id)
connectedClients = {}  # Dictionary to store client information (socket, address, name)
leader = None  # Current leader (address, unique_id)
isActive = True  # Server active state
uniqueId = f"{int(time.time())}-{random.randint(0, 9999):04d}"
shutdownEvent = threading.Event()

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

def broadcastServerPresence():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udpSocket:
        udpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while not shutdownEvent.is_set():
            message = createXmlMessage("server_discovery", server_port=TCP_PORT, unique_id=uniqueId)
            udpSocket.sendto(message, ('<broadcast>', UDP_PORT))
            time.sleep(10)

def listenForServerDiscovery():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udpSocket:
        udpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udpSocket.bind(('', UDP_PORT))
        while not shutdownEvent.is_set():
            try:
                message, addr = udpSocket.recvfrom(BUFFER_SIZE)
                messageType, data = parseXmlMessage(message)
                if messageType == "server_discovery":
                    handleServerDiscovery(addr, data)
            except Exception as e:
                print(f"Error in server discovery: {e}")

def handleServerDiscovery(addr, data):
    serverId = data['unique_id']
    serverPort = int(data['server_port'])
    if serverId != uniqueId and serverId not in [server[1] for server in connectedServers.values()]:
        print(f"New server discovered: {addr[0]}:{serverPort}, ID: {serverId}")
        connectToServer(addr[0], serverPort, serverId)

def connectToServer(ip, port, serverId):
    try:
        serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        serverSocket.connect((ip, port))
        connectedServers[serverSocket] = ((ip, port), serverId)
        threading.Thread(target=serverConnectionManager, args=(serverSocket, (ip, port))).start()
        print(f"Connected to server at {ip}:{port}")
        initiateLeaderElection()
    except Exception as e:
        print(f"Failed to connect to server at {ip}:{port}: {e}")

def initiateLeaderElection():
    global leader
    allServers = list(connectedServers.values()) + [((socket.gethostbyname(socket.gethostname()), TCP_PORT), uniqueId)]
    newLeader = max(allServers, key=lambda x: x[1])
    if newLeader[1] == uniqueId:
        leader = (socket.gethostbyname(socket.gethostname()), uniqueId)
    else:
        leader = newLeader
    announceLeader()

def announceLeader():
    leaderAnnouncement = createXmlMessage("leader_announcement", leader_ip=leader[0][0], leader_port=str(leader[0][1]), leader_id=leader[1])
    for serverSocket in connectedServers:
        serverSocket.send(leaderAnnouncement)
    for clientSocket in connectedClients:
        clientSocket.send(leaderAnnouncement)
    print(f"Leader is {leader[0]} with ID {leader[1]}")

def serverConnectionManager(serverSocket, addr):
    while not shutdownEvent.is_set():
        try:
            message = serverSocket.recv(BUFFER_SIZE)
            if not message:
                break

            messageType, data = parseXmlMessage(message)

            if messageType == "heartbeat":
                # Reset heartbeat timer for this server
                pass
            elif messageType == "leader_announcement":
                handleLeaderAnnouncement(data)
            else:
                print(f"Unknown message type received from server: {messageType}")

        except Exception as e:
            print(f"Error handling server {addr}: {e}")
            break

    serverSocket.close()
    print(f"Connection with server {addr} closed")
    if serverSocket in connectedServers:
        del connectedServers[serverSocket]
        if addr == leader[0]:
            print("Leader has disconnected. Initiating new leader election.")
            initiateLeaderElection()

def handleLeaderAnnouncement(data):
    global leader
    leaderIp = data['leader_ip']
    leaderPort = int(data['leader_port'])
    leaderId = data['leader_id']
    leader = ((leaderIp, leaderPort), leaderId)
    print(f"Received leader announcement: {leaderIp}:{leaderPort} with ID {leaderId}")

def clientConnectionManager(clientSocket, addr):
    while not shutdownEvent.is_set():
        try:
            message = clientSocket.recv(BUFFER_SIZE)
            if not message:
                break

            messageType, data = parseXmlMessage(message)

            if messageType == "chat_message":
                broadcastChatMessage(data['name'], data['content'])
            elif messageType == "set_name":
                connectedClients[clientSocket] = (addr, data['name'])
                print(f"Client {addr} set name to {data['name']}")
            else:
                print(f"Unknown message type received from client: {messageType}")

        except Exception as e:
            print(f"Error handling client {addr}: {e}")
            break

    clientSocket.close()
    print(f"Connection with client {addr} closed")
    if clientSocket in connectedClients:
        del connectedClients[clientSocket]

def broadcastChatMessage(senderName, content):
    message = createXmlMessage("chat_message", sender=senderName, content=content)
    for clientSocket in connectedClients:
        clientSocket.send(message)

def heartbeatCheck():
    while not shutdownEvent.is_set():
        for serverSocket in list(connectedServers.keys()):
            try:
                serverSocket.send(createXmlMessage("heartbeat"))
            except:
                print(f"Server {connectedServers[serverSocket][0]} is not responding. Removing from connected servers.")
                del connectedServers[serverSocket]
                if connectedServers[serverSocket][0] == leader[0]:
                    print("Leader has failed. Initiating new leader election.")
                    initiateLeaderElection()
        time.sleep(HEARTBEAT_INTERVAL)

def main():
    global isActive

    tcpSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcpSocket.bind(('', TCP_PORT))
    tcpSocket.listen()
    print(f"TCP server listening on port {TCP_PORT}")

    broadcastThread = threading.Thread(target=broadcastServerPresence)
    broadcastThread.start()

    discoveryThread = threading.Thread(target=listenForServerDiscovery)
    discoveryThread.start()

    heartbeatThread = threading.Thread(target=heartbeatCheck)
    heartbeatThread.start()

    # Initial leader election
    initiateLeaderElection()

    def acceptConnections():
        while not shutdownEvent.is_set():
            try:
                clientSocket, addr = tcpSocket.accept()
                threading.Thread(target=clientConnectionManager, args=(clientSocket, addr)).start()
            except Exception as e:
                print(f"Error accepting connection: {e}")

    connectionThread = threading.Thread(target=acceptConnections)
    connectionThread.start()

    while isActive:
        cmd = input("\nSelect an option\n1: Display current leader\n2: Show connected servers and clients\n3: Terminate server\n")
        if cmd == '3':
            shutdownEvent.set()
            break
        elif cmd == '2':
            print("Connected servers:")
            for addr, server_id in connectedServers.values():
                print(f"Server at {addr}, ID: {server_id}")
            print("\nConnected clients:")
            for addr, name in connectedClients.values():
                print(f"Client {name} at {addr}")
        elif cmd == '1':
            if leader:
                print(f"Current leader is: {leader[0]} with ID {leader[1]}")
            else:
                print("No leader has been elected yet.")
        else:
            print("Invalid command.")

    tcpSocket.close()
    connectionThread.join()
    broadcastThread.join()
    discoveryThread.join()
    heartbeatThread.join()

if __name__ == "__main__":
    main()