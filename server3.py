import socket
import threading
import time
import sys
import xml.etree.ElementTree as ET

# Constants
UDP_PORT = 42000  # Default UDP port for server discovery
BUFFER_SIZE = 1024

# Global variables
connectedServers = {}  # Dictionary to store information of discovered servers
leader = None  # Current leader
isActive = True  # Server active state
serverId = None  # Will be set based on the TCP port

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
    leaderAnnouncement = createXmlMessage("leader_announcement", leader_ip=leaderAddr[0][0], leader_port=leaderAddr[1])
    for serverAddr in connectedServers.values():
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcpSocket:
                tcpSocket.connect((serverAddr[0], leaderAddr[1]))
                tcpSocket.send(leaderAnnouncement)
        except Exception as e:
            print(f"Error sending leader announcement to {serverAddr}: {e}")

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

    broadcastThread = threading.Thread(target=broadcastServerPresence, args=(serverId,))
    broadcastThread.start()

    listenThread = threading.Thread(target=listenForServers)
    listenThread.start()

    tcpSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcpSocket.bind(('', serverId))
    tcpSocket.listen()
    print(f"TCP server listening on port {serverId}")

    # Keep running until the server is terminated
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

    listenThread.join()
    broadcastThread.join()

if __name__ == "__main__":
    main()
