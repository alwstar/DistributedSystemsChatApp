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
connectedServers = {}  # Dictionary to store server information (socket: (address, unique_id))
connectedClients = {}  # Dictionary to store client information (socket: (address, name))
leader = None  # Current leader (address, port, unique_id)
isActive = True  # Server active state
uniqueId = f"{int(time.time())}-{random.randint(0, 9999):04d}"
shutdownEvent = threading.Event()

def createXmlMessage(messageType, **kwargs):
    root = ET.Element("message")
    ET.SubElement(root, "type").text = messageType
    for key, value in kwargs.items():
        ET.SubElement(root, key).text = str(value)
    return ET.tostring(root, encoding='utf-8', method='xml')

def parseXmlMessage(xmlString):
    try:
        root = ET.fromstring(xmlString)
        messageType = root.find("type").text
        data = {child.tag: child.text for child in root if child.tag != "type"}
        return messageType, data
    except ET.ParseError as e:
        print(f"XML parsing error: {e}")
        print(f"Problematic XML: {xmlString}")
        return None, None

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
    if data is None:
        return
    serverId = data.get('unique_id')
    serverPort = int(data.get('server_port', 0))
    if serverId and serverPort and serverId != uniqueId and not any(server_id == serverId for _, server_id in connectedServers.values()):
        print(f"New server discovered: {addr[0]}:{serverPort}, ID: {serverId}")
        connectToServer(addr[0], serverPort, serverId)

def connectToServer(ip, port, serverId):
    try:
        serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        serverSocket.connect((ip, port))
        serverSocket.send(createXmlMessage("server_connect", unique_id=uniqueId))
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
        leader = (socket.gethostbyname(socket.gethostname()), TCP_PORT, uniqueId)
    else:
        leader = newLeader[0] + (newLeader[1],)
    announceLeader()

def announceLeader():
    leaderAnnouncement = createXmlMessage("leader_announcement", leader_ip=leader[0], leader_port=str(leader[1]), leader_id=leader[2])
    for serverSocket in list(connectedServers.keys()):
        try:
            serverSocket.send(leaderAnnouncement)
        except:
            removeServer(serverSocket)
    for clientSocket in list(connectedClients.keys()):
        try:
            clientSocket.send(leaderAnnouncement)
        except:
            removeClient(clientSocket)
    print(f"Leader is {leader[0]}:{leader[1]} with ID {leader[2]}")

def serverConnectionManager(serverSocket, addr):
    while not shutdownEvent.is_set():
        try:
            message = serverSocket.recv(BUFFER_SIZE)
            if not message:
                break

            messageType, data = parseXmlMessage(message)
            if messageType is None:
                continue

            if messageType == "heartbeat":
                serverSocket.send(createXmlMessage("heartbeat_ack"))
            elif messageType == "heartbeat_ack":
                pass  # Heartbeat acknowledged, do nothing
            elif messageType == "leader_announcement":
                handleLeaderAnnouncement(data)
            else:
                print(f"Unknown message type received from server: {messageType}")

        except socket.timeout:
            continue
        except Exception as e:
            print(f"Error handling server {addr}: {e}")
            break

    removeServer(serverSocket)

def removeServer(serverSocket):
    if serverSocket in connectedServers:
        addr, serverId = connectedServers[serverSocket]
        del connectedServers[serverSocket]
        print(f"Connection with server {addr} closed")
        try:
            serverSocket.close()
        except:
            pass
        if (addr[0], addr[1], serverId) == leader:
            print("Leader has disconnected. Initiating new leader election.")
            initiateLeaderElection()

def handleLeaderAnnouncement(data):
    global leader
    if data is None:
        return
    leaderIp = data.get('leader_ip')
    leaderPort = int(data.get('leader_port', 0))
    leaderId = data.get('leader_id')
    if leaderIp and leaderPort and leaderId:
        leader = (leaderIp, leaderPort, leaderId)
        print(f"Received leader announcement: {leaderIp}:{leaderPort} with ID {leaderId}")

def clientConnectionManager(clientSocket, addr):
    while not shutdownEvent.is_set():
        try:
            message = clientSocket.recv(BUFFER_SIZE)
            if not message:
                break

            messageType, data = parseXmlMessage(message)
            if messageType is None:
                continue

            if messageType == "chat_message":
                broadcastChatMessage(data['name'], data['content'])
            elif messageType == "set_name":
                connectedClients[clientSocket] = (addr, data['name'])
                print(f"Client {addr} set name to {data['name']}")
            else:
                print(f"Unknown message type received from client: {messageType}")

        except socket.timeout:
            continue
        except Exception as e:
            print(f"Error handling client {addr}: {e}")
            break

    removeClient(clientSocket)

def removeClient(clientSocket):
    if clientSocket in connectedClients:
        addr, name = connectedClients[clientSocket]
        del connectedClients[clientSocket]
        print(f"Connection with client {name} at {addr} closed")
        try:
            clientSocket.close()
        except:
            pass

def broadcastChatMessage(senderName, content):
    message = createXmlMessage("chat_message", sender=senderName, content=content)
    for clientSocket in list(connectedClients.keys()):
        try:
            clientSocket.send(message)
        except:
            removeClient(clientSocket)

def heartbeatCheck():
    while not shutdownEvent.is_set():
        for serverSocket in list(connectedServers.keys()):
            try:
                serverSocket.send(createXmlMessage("heartbeat"))
                serverSocket.settimeout(2)
                ack = serverSocket.recv(BUFFER_SIZE)
                serverSocket.settimeout(None)
                messageType, _ = parseXmlMessage(ack)
                if messageType != "heartbeat_ack":
                    raise Exception("Invalid heartbeat acknowledgement")
            except Exception as e:
                print(f"Server {connectedServers[serverSocket][0]} is not responding: {e}. Removing from connected servers.")
                removeServer(serverSocket)
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
                newSocket, addr = tcpSocket.accept()
                newSocket.settimeout(5)  # Set a timeout for receiving the initial message
                message = newSocket.recv(BUFFER_SIZE)
                newSocket.settimeout(None)  # Remove the timeout
                messageType, data = parseXmlMessage(message)
                if messageType == "server_connect":
                    serverId = data['unique_id']
                    connectedServers[newSocket] = (addr, serverId)
                    threading.Thread(target=serverConnectionManager, args=(newSocket, addr)).start()
                    print(f"Server connected from {addr}")
                    initiateLeaderElection()
                elif messageType == "client_connect":
                    connectedClients[newSocket] = (addr, "Unknown")
                    threading.Thread(target=clientConnectionManager, args=(newSocket, addr)).start()
                    print(f"Client connected from {addr}")
                else:
                    print(f"Unknown connection type from {addr}")
                    newSocket.close()
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
                print(f"Current leader is: {leader[0]}:{leader[1]} with ID {leader[2]}")
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