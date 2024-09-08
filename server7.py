import socket
import threading
import time
import sys
import random
import xml.etree.ElementTree as ET

# Constants
UDP_PORT = 42000
BUFFER_SIZE = 1024
HEARTBEAT_INTERVAL = 5  # Send heartbeat every 5 seconds
HEARTBEAT_TIMEOUT = 10  # Timeout if no heartbeat received within 10 seconds

# Global variables
connectedServers = {}  # Dictionary to store information of discovered servers
leader = None  # Current leader
isActive = True  # Server active state
serverId = None  # Will be set based on the TCP port
uniqueId = None  # Unique identifier generated for each server
lastHeartbeat = {}  # Dictionary to store last heartbeat timestamps from other servers

# Shutdown event
shutdownEvent = threading.Event()

# Function to generate a unique identifier based on timestamp and random number
def generate_unique_id():
    timestamp = int(time.time())  # Get the current timestamp
    random_number = random.randint(0, 9999)  # Generate a random number between 0 and 9999
    unique_id = f"{timestamp}{random_number:04d}"  # Combine them to create the unique ID
    return unique_id

def broadcastServerPresence(tcpPort):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udpSocket:
        udpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while isActive:
            message = f"ServerAvailable:{tcpPort}:{uniqueId}".encode()
            udpSocket.sendto(message, ('<broadcast>', UDP_PORT))
            time.sleep(10)

def listenForServers():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udpSocket:
        udpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udpSocket.bind(('', UDP_PORT))

        while isActive:
            try:
                message, serverAddr = udpSocket.recvfrom(BUFFER_SIZE)
                msgStr = message.decode()
                if msgStr.startswith("ServerAvailable:"):
                    _, discoveredPort, discoveredUniqueId = msgStr.split(':')
                    discoveredPort = int(discoveredPort)
                    if discoveredPort != serverId:  # Ignore self
                        connectedServers[discoveredPort] = (serverAddr, discoveredUniqueId)
                        lastHeartbeat[discoveredPort] = time.time()
                        print(f"Discovered server on port {discoveredPort} with ID {discoveredUniqueId}")
                        initiateLeaderElection()
            except Exception as e:
                print(f"Error listening for servers: {e}")
                break

def initiateLeaderElection():
    global leader
    if connectedServers:
        # Find server with the highest unique ID (bully algorithm logic)
        highestIdServer = max(connectedServers.items(), key=lambda x: x[1][1])  # Sort by unique ID
        if highestIdServer[0] > serverId:
            leader = (connectedServers[highestIdServer[0]], highestIdServer[0])
        else:
            leader = (('localhost', serverId), serverId)
        announceLeader(leader)
    else:
        leader = (('localhost', serverId), serverId)
        print(f"No other servers found. I am the leader with port {serverId} and ID {uniqueId}")

def announceLeader(leaderAddr):
    print(f"Leader is {leaderAddr}")
    
    # Correct leader IP and port extraction
    leaderIp = leaderAddr[0] if isinstance(leaderAddr[0], str) else leaderAddr[0][0]
    leaderPort = leaderAddr[1]

    # Create XML leader announcement message with correct IP address
    leaderAnnouncement = createXmlMessage("leader_announcement", leader_ip=leaderIp, leader_port=leaderPort)
    
    # Debug print to verify the message format
    # print(f"Broadcasting leader announcement: {leaderAnnouncement.decode()}")

    # Broadcast the leader announcement
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udpSocket:
        udpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        udpSocket.sendto(leaderAnnouncement, ('<broadcast>', UDP_PORT))



# Handle client discovery requests and respond if this server is the leader
def listenForClientDiscovery():
    global leader
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udpSocket:
        udpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udpSocket.bind(('', UDP_PORT))

        while isActive:
            try:
                message, clientAddr = udpSocket.recvfrom(BUFFER_SIZE)
                msgStr = message.decode()
                if msgStr == "DiscoverLeader":
                    if leader and leader[1] == serverId:
                        print(f"Responding to client leader discovery request from {clientAddr}")
                        # Send leader information back to the client
                        leaderInfo = f"Leader:{leader[0][0]}:{leader[1]}".encode()
                        udpSocket.sendto(leaderInfo, clientAddr)
            except Exception as e:
                print(f"Error listening for client discovery: {e}")
                break

def createXmlMessage(messageType, **kwargs):
    root = ET.Element("message")
    ET.SubElement(root, "type").text = messageType
    for key, value in kwargs.items():
        ET.SubElement(root, key).text = str(value)
    return ET.tostring(root)

def terminateServer(tcpSocket):
    global isActive
    isActive = False
    shutdownEvent.set()

    for userSocket in connectedServers.values():
        try:
            userSocket.close()
        except Exception as e:
            print(f"Error closing server connection: {e}")

    connectedServers.clear()
    tcpSocket.close()
    print("Server has been terminated.")

# Heartbeat mechanism to send heartbeat to all servers
def sendHeartbeat():
    while isActive:
        for serverPort, serverAddr in list(connectedServers.items()):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcpSocket:
                    tcpSocket.connect((serverAddr[0][0], serverPort))
                    heartbeatMessage = createXmlMessage("heartbeat", mid=str(uniqueId))
                    tcpSocket.send(heartbeatMessage)
            except Exception as e:
                print(f"Error sending heartbeat to server {serverAddr}: {e}")
                # Mark the server as failed and remove it
                del connectedServers[serverPort]
                del lastHeartbeat[serverPort]
                print(f"Removed failed server {serverPort}")
        time.sleep(HEARTBEAT_INTERVAL)

# Monitor heartbeats from servers to detect failures
def monitorHeartbeat():
    while isActive:
        currentTime = time.time()
        for serverPort in list(lastHeartbeat.keys()):
            if currentTime - lastHeartbeat[serverPort] > HEARTBEAT_TIMEOUT:
                print(f"Server {serverPort} has failed or is unreachable. Triggering election.")
                if serverPort in connectedServers:
                    del connectedServers[serverPort]  # Safely delete the server if it exists
                if serverPort in lastHeartbeat:
                    del lastHeartbeat[serverPort]  # Safely delete the heartbeat entry if it exists
                initiateLeaderElection()
        time.sleep(HEARTBEAT_INTERVAL)

# Heartbeat response listener
def parseXmlMessage(xmlString):
    root = ET.fromstring(xmlString)
    messageType = root.find("type").text
    data = {child.tag: child.text for child in root if child.tag != "type"}
    return messageType, data

# Heartbeat response listener
def listenForHeartbeats():
    while isActive:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcpSocket:
            tcpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            tcpSocket.bind(('', serverId))
            tcpSocket.listen()
            while isActive:
                conn, addr = tcpSocket.accept()
                message = conn.recv(BUFFER_SIZE)
                messageType, data = parseXmlMessage(message)
                if messageType == "heartbeat":
                    senderId = int(data['mid'])
                    lastHeartbeat[senderId] = time.time()
                    print(f"Received heartbeat from server {senderId}")

def clientConnectionManager(clientSocket, addr):
    global leader
    clientId = None

    print(f"Client connected from {addr}")

    try:
        clientSocket.settimeout(30)  # Set a timeout for client communication

        while True:
            try:
                message = clientSocket.recv(BUFFER_SIZE)
                if not message:
                    print(f"Client {addr} disconnected.")
                    break

                print(f"Received message from client {addr}: {message.decode()}")

                # Parse the incoming message
                messageType, data = parseXmlMessage(message)
                print(f"Parsed message: Type={messageType}, Data={data}")

                if messageType == "client_id":
                    clientId = data['client_id']
                    print(f"Client {clientId} connected.")

                elif messageType == "chatroom":
                    content = data['content']
                    print(f"Message from {clientId}: {content}")

                    # Check if this server is the leader
                    if leader and leader[1] == serverId:
                        print(f"Broadcasting message from {clientId} to all clients.")
                        # Broadcast the message to all connected servers/clients
                        for serverPort, serverAddr in connectedServers.items():
                            try:
                                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcpSocket:
                                    tcpSocket.connect((serverAddr[0][0], serverPort))
                                    chatMessage = createXmlMessage("chatroom", client_id=clientId, content=content)
                                    tcpSocket.send(chatMessage)
                            except Exception as e:
                                print(f"Error broadcasting to server {serverPort}: {e}")
                    else:
                        # Forward the message to the leader if this server is not the leader
                        try:
                            print(f"Forwarding message to leader at {leader[0][0]}:{leader[1]}")
                            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcpSocket:
                                tcpSocket.connect((leader[0][0], leader[1]))
                                forwardMessage = createXmlMessage("chatroom", client_id=clientId, content=content)
                                tcpSocket.send(forwardMessage)
                        except Exception as e:
                            print(f"Error forwarding message to leader: {e}")
            except socket.timeout:
                print(f"Connection timed out for client {addr}.")
                break
            except Exception as e:
                print(f"Error handling client {addr}: {e}")
                break
    finally:
        clientSocket.close()
        print(f"Client {addr} disconnected.")


def main():
    global serverId, isActive, leader, uniqueId

    # Get TCP port from CLI or default to 6000
    if len(sys.argv) > 1:
        try:
            serverId = int(sys.argv[1])
        except ValueError:
            print("Invalid port number. Using default port 6000.")
            serverId = 6000
    else:
        serverId = 6000

    # Generate a unique server ID
    uniqueId = generate_unique_id()
    print(f"Generated unique server ID: {uniqueId}")

    print(f"Starting server on TCP port {serverId}")

    # Start threads for server communication, client discovery, and heartbeats
    broadcastThread = threading.Thread(target=broadcastServerPresence, args=(serverId,))
    listenThread = threading.Thread(target=listenForServers)
    heartbeatThread = threading.Thread(target=sendHeartbeat)
    monitorHeartbeatThread = threading.Thread(target=monitorHeartbeat)
    heartbeatListenerThread = threading.Thread(target=listenForHeartbeats)
    clientDiscoveryThread = threading.Thread(target=listenForClientDiscovery)

    broadcastThread.start()
    listenThread.start()
    heartbeatThread.start()
    monitorHeartbeatThread.start()
    heartbeatListenerThread.start()
    clientDiscoveryThread.start()

    # Accepting client connections (Only the leader handles clients)
    tcpSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcpSocket.bind(('', serverId))
    tcpSocket.listen()
    print(f"TCP server listening on port {serverId}")

    while isActive:
        # Check if the server is the leader before accepting client connections
        if leader and leader[1] == serverId:
            print("I am the leader. Waiting for clients...")
            try:
                clientSocket, addr = tcpSocket.accept()
                threading.Thread(target=clientConnectionManager, args=(clientSocket, addr)).start()
            except Exception as e:
                print(f"Error accepting client connection: {e}")

        cmd = input("\nSelect an option\n1: Display current leader\n2: Show discovered servers\n3: Terminate server\n")
        if cmd == '3':
            terminateServer(tcpSocket)
            break
        elif cmd == '2':
            print("Discovered servers:", connectedServers)
        elif cmd == '1':
            if leader:
                print(f"Current leader is: {leader}")
            else:
                print("No leader has been elected yet.")
        else:
            print("Invalid command.")

    # Wait for all threads to finish before exiting
    broadcastThread.join()
    listenThread.join()
    heartbeatThread.join()
    monitorHeartbeatThread.join()
    heartbeatListenerThread.join()
    clientDiscoveryThread.join()

if __name__ == "__main__":
    main()
