import socket
import threading
import time
import sys
import json
import random
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Constants
UDP_PORT = 42000
BUFFER_SIZE = 1024
TCP_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 6000
HEARTBEAT_INTERVAL = 5
HEARTBEAT_TIMEOUT = 10

# Global variables
knownServers = {}  # Dictionary to store all known server information (unique_id: (address, port))
connectedClients = {}  # Dictionary to store client information (socket: (address, name))
leader = None  # Current leader (address, port, unique_id)
isActive = True  # Server active state
uniqueId = f"{int(time.time())}-{random.randint(0, 9999):04d}"
shutdownEvent = threading.Event()
serverLock = threading.Lock()

def createJsonMessage(messageType, **kwargs):
    message = {"type": messageType, **kwargs}
    return json.dumps(message).encode('utf-8') + b'\n'  # Add newline as a message separator

def parseJsonMessages(data):
    messages = []
    for line in data.decode('utf-8').split('\n'):
        if line:
            try:
                message = json.loads(line)
                messages.append((message.get("type"), message))
            except json.JSONDecodeError as e:
                logging.error(f"JSON parsing error: {e}")
                logging.error(f"Problematic JSON: {line}")
    return messages

def broadcastServerPresence():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udpSocket:
        udpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while not shutdownEvent.is_set():
            message = createJsonMessage("server_discovery", server_port=TCP_PORT, unique_id=uniqueId)
            udpSocket.sendto(message, ('<broadcast>', UDP_PORT))
            time.sleep(10)

def listenForServerDiscovery():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udpSocket:
        udpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udpSocket.bind(('', UDP_PORT))
        while not shutdownEvent.is_set():
            try:
                message, addr = udpSocket.recvfrom(BUFFER_SIZE)
                messages = parseJsonMessages(message)
                for messageType, data in messages:
                    if messageType == "server_discovery":
                        handleServerDiscovery(addr, data)
            except Exception as e:
                logging.error(f"Error in server discovery: {e}")

def handleServerDiscovery(addr, data):
    if data is None:
        return
    serverId = data.get('unique_id')
    serverPort = int(data.get('server_port', 0))
    if serverId and serverPort and serverId != uniqueId:
        with serverLock:
            if serverId not in knownServers:
                knownServers[serverId] = (addr[0], serverPort)
                logging.info(f"New server discovered: {addr[0]}:{serverPort}, ID: {serverId}")
                if not any(s[0] == addr[0] and s[1] == serverPort for s in knownServers.values()):
                    connectToServer(addr[0], serverPort, serverId)
        initiateLeaderElection()

def connectToServer(ip, port, serverId):
    try:
        serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        serverSocket.settimeout(5)  # Set a timeout for the connection attempt
        serverSocket.connect((ip, port))
        serverSocket.settimeout(None)  # Remove the timeout after successful connection
        serverSocket.send(createJsonMessage("server_connect", unique_id=uniqueId))
        threading.Thread(target=serverConnectionManager, args=(serverSocket, (ip, port), serverId)).start()
        logging.info(f"Connected to server at {ip}:{port}")
    except Exception as e:
        logging.error(f"Failed to connect to server at {ip}:{port}: {e}")

def initiateLeaderElection():
    global leader
    with serverLock:
        allServers = list(knownServers.items()) + [(uniqueId, (socket.gethostbyname(socket.gethostname()), TCP_PORT))]
        newLeader = max(allServers, key=lambda x: x[0])
        leader = newLeader[1] + (newLeader[0],)
    announceLeader()

def announceLeader():
    leaderAnnouncement = createJsonMessage("leader_announcement", leader_ip=leader[0], leader_port=leader[1], leader_id=leader[2])
    with serverLock:
        for serverId, (ip, port) in knownServers.items():
            if serverId != uniqueId:
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.connect((ip, port))
                        s.send(leaderAnnouncement)
                except Exception as e:
                    logging.error(f"Failed to announce leader to {ip}:{port}: {e}")
        for clientSocket in list(connectedClients.keys()):
            try:
                clientSocket.send(leaderAnnouncement)
            except:
                removeClient(clientSocket)
    logging.info(f"Leader is {leader[0]}:{leader[1]} with ID {leader[2]}")

def serverConnectionManager(serverSocket, addr, serverId):
    buffer = b""
    lastHeartbeat = time.time()
    while not shutdownEvent.is_set():
        try:
            serverSocket.settimeout(1)  # Short timeout to allow for regular checks
            data = serverSocket.recv(BUFFER_SIZE)
            if data:
                buffer += data
                messages = parseJsonMessages(buffer)
                buffer = b""  # Clear the buffer after processing

                for messageType, messageData in messages:
                    if messageType == "heartbeat":
                        lastHeartbeat = time.time()
                        serverSocket.send(createJsonMessage("heartbeat_ack"))
                    elif messageType == "heartbeat_ack":
                        lastHeartbeat = time.time()
                    elif messageType == "leader_announcement":
                        handleLeaderAnnouncement(messageData)
                    else:
                        logging.warning(f"Unknown message type received from server: {messageType}")
            
            # Check if heartbeat has timed out
            if time.time() - lastHeartbeat > HEARTBEAT_TIMEOUT:
                raise Exception("Heartbeat timeout")

        except socket.timeout:
            continue
        except Exception as e:
            logging.error(f"Error handling server {addr}: {e}")
            break

    removeServer(serverId)

def removeServer(serverId):
    with serverLock:
        if serverId in knownServers:
            addr = knownServers[serverId]
            del knownServers[serverId]
            logging.info(f"Connection with server {addr} closed")
            if leader and leader[2] == serverId:
                logging.info("Leader has disconnected. Initiating new leader election.")
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
        logging.info(f"Received leader announcement: {leaderIp}:{leaderPort} with ID {leaderId}")

def clientConnectionManager(clientSocket, addr):
    buffer = b""
    while not shutdownEvent.is_set():
        try:
            data = clientSocket.recv(BUFFER_SIZE)
            if not data:
                break
            buffer += data
            messages = parseJsonMessages(buffer)
            buffer = b""  # Clear the buffer after processing

            for messageType, messageData in messages:
                if messageType == "chat_message":
                    broadcastChatMessage(messageData['name'], messageData['content'])
                elif messageType == "set_name":
                    connectedClients[clientSocket] = (addr, messageData['name'])
                    logging.info(f"Client {addr} set name to {messageData['name']}")
                else:
                    logging.warning(f"Unknown message type received from client: {messageType}")

        except socket.timeout:
            continue
        except Exception as e:
            logging.error(f"Error handling client {addr}: {e}")
            break

    removeClient(clientSocket)

def removeClient(clientSocket):
    if clientSocket in connectedClients:
        addr, name = connectedClients[clientSocket]
        del connectedClients[clientSocket]
        logging.info(f"Connection with client {name} at {addr} closed")
        try:
            clientSocket.close()
        except:
            pass

def broadcastChatMessage(senderName, content):
    message = createJsonMessage("chat_message", sender=senderName, content=content)
    with serverLock:
        for clientSocket in list(connectedClients.keys()):
            try:
                clientSocket.send(message)
            except:
                removeClient(clientSocket)

def heartbeatCheck():
    while not shutdownEvent.is_set():
        with serverLock:
            for serverId, (ip, port) in list(knownServers.items()):
                if serverId != uniqueId:
                    try:
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                            s.settimeout(HEARTBEAT_TIMEOUT)
                            s.connect((ip, port))
                            s.send(createJsonMessage("heartbeat"))
                            ack = s.recv(BUFFER_SIZE)
                            messages = parseJsonMessages(ack)
                            if not any(messageType == "heartbeat_ack" for messageType, _ in messages):
                                raise Exception("Invalid heartbeat acknowledgement")
                    except Exception as e:
                        logging.warning(f"Server {ip}:{port} is not responding: {e}. Removing from known servers.")
                        removeServer(serverId)
        time.sleep(HEARTBEAT_INTERVAL)

def main():
    global isActive

    tcpSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcpSocket.bind(('', TCP_PORT))
    tcpSocket.listen()
    logging.info(f"TCP server listening on port {TCP_PORT}")

    # Add this server to knownServers
    knownServers[uniqueId] = (socket.gethostbyname(socket.gethostname()), TCP_PORT)

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
                messages = parseJsonMessages(message)
                if messages:
                    messageType, data = messages[0]  # Process only the first message
                    if messageType == "server_connect":
                        serverId = data['unique_id']
                        knownServers[serverId] = addr
                        threading.Thread(target=serverConnectionManager, args=(newSocket, addr, serverId)).start()
                        logging.info(f"Server connected from {addr}")
                        initiateLeaderElection()
                    elif messageType == "client_connect":
                        connectedClients[newSocket] = (addr, "Unknown")
                        threading.Thread(target=clientConnectionManager, args=(newSocket, addr)).start()
                        logging.info(f"Client connected from {addr}")
                    else:
                        logging.warning(f"Unknown connection type from {addr}")
                        newSocket.close()
                else:
                    logging.warning(f"No valid message received from {addr}")
                    newSocket.close()
            except Exception as e:
                logging.error(f"Error accepting connection: {e}")

    connectionThread = threading.Thread(target=acceptConnections)
    connectionThread.start()

    while isActive:
        cmd = input("\nSelect an option\n1: Display current leader\n2: Show connected servers and clients\n3: Terminate server\n")
        if cmd == '3':
            shutdownEvent.set()
            break
        elif cmd == '2':
            with serverLock:
                print("Known servers:")
                for server_id, (ip, port) in knownServers.items():
                    print(f"Server at {ip}:{port}, ID: {server_id}")
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