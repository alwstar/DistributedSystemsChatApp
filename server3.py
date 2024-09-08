import socket
import threading
import time
import sys
import xml.etree.ElementTree as ET

# Constants
UDP_PORT = 42000
BUFFER_SIZE = 1024
TCP_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 6000
HEARTBEAT_INTERVAL = 5  # Send heartbeat every 5 seconds
HEARTBEAT_TIMEOUT = 10  # Timeout if no heartbeat received within 10 seconds

# Global variables
connectedServers = {}  # Dictionary to store information of discovered servers
leader = None  # Current leader
isActive = True  # Server active state
serverId = None  # Will be set based on the TCP port
lastHeartbeat = {}  # Dictionary to store last heartbeat timestamps from other servers

# Shutdown event
shutdownEvent = threading.Event()

def broadcastServerPresence(tcpPort):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udpSocket:
        udpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while isActive:
            message = f"ServerAvailable:{tcpPort}".encode()
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
                    _, discoveredPort = msgStr.split(':')
                    discoveredPort = int(discoveredPort)
                    if discoveredPort != serverId:  # Ignore self
                        connectedServers[discoveredPort] = serverAddr
                        lastHeartbeat[discoveredPort] = time.time()
                        print(f"Discovered server on port {discoveredPort}")
                        initiateLeaderElection()
            except Exception as e:
                print(f"Error listening for servers: {e}")
                break

def initiateLeaderElection():
    global leader
    if connectedServers:
        # Find server with the highest ID (TCP_PORT)
        maxId = max(connectedServers.keys())
        if maxId > serverId:
            leader = (connectedServers[maxId], maxId)
        else:
            leader = (('localhost', serverId), serverId)
        announceLeader(leader)
    else:
        leader = (('localhost', serverId), serverId)
        print(f"No other servers found. I am the leader with port {serverId}")

def announceLeader(leaderAddr):
    print(f"Leader is {leaderAddr}")
    
    # Extract only the IP part from the tuple
    leaderIp = leaderAddr[0]  # This should be '192.168.56.1' or another valid IP address
    leaderPort = leaderAddr[1]  # Port number

    # Create XML leader announcement message with only the IP address as a string
    leaderAnnouncement = createXmlMessage("leader_announcement", leader_ip=leaderIp, leader_port=leaderPort)
    
    # Debug print to verify the message format
    print(f"Broadcasting leader announcement: {leaderAnnouncement.decode()}")

    # Broadcast the leader announcement
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udpSocket:
        udpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        udpSocket.sendto(leaderAnnouncement, ('<broadcast>', UDP_PORT))


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
                    tcpSocket.connect((serverAddr[0], serverPort))
                    heartbeatMessage = createXmlMessage("heartbeat", mid=str(serverId))
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
                del connectedServers[serverPort]
                del lastHeartbeat[serverPort]
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


def main():
    global serverId, isActive

    # Get TCP port from CLI or default to 6000
    if len(sys.argv) > 1:
        try:
            serverId = int(sys.argv[1])
        except ValueError:
            print("Invalid port number. Using default port 6000.")
            serverId = 6000
    else:
        serverId = 6000

    print(f"Starting server on TCP port {serverId}")

    # Start threads for broadcasting, listening, and monitoring heartbeats
    broadcastThread = threading.Thread(target=broadcastServerPresence, args=(serverId,))
    listenThread = threading.Thread(target=listenForServers)
    heartbeatThread = threading.Thread(target=sendHeartbeat)
    monitorHeartbeatThread = threading.Thread(target=monitorHeartbeat)
    heartbeatListenerThread = threading.Thread(target=listenForHeartbeats)

    broadcastThread.start()
    listenThread.start()
    heartbeatThread.start()
    monitorHeartbeatThread.start()
    heartbeatListenerThread.start()

    tcpSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcpSocket.bind(('', serverId))
    tcpSocket.listen()
    print(f"TCP server listening on port {serverId}")

    while isActive:
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

if __name__ == "__main__":
    main()
