import socket
import threading
import time
import sys
import json
import random

# Constants
UDP_PORT = 42000
BUFFER_SIZE = 1024
BASE_TCP_PORT = 6000

# Global variables
connectedServers = {}  # Dictionary to store server information (socket, address)
connectedUsers = {}    # Dictionary to store user information (socket, address)
leader = None          # Current leader
isActive = True        # Server active state
discussionGroups = {}  # Dictionary to store discussion groups and their members

# Shutdown event
shutdownEvent = threading.Event()

def generateServerId():
    return f"SERVER_{random.randint(1000, 9999)}"

SERVER_ID = generateServerId()
TCP_PORT = None  # Will be set in main()

def createJsonMessage(messageType, **kwargs):
    message = {"type": messageType, **kwargs}
    return json.dumps(message).encode()

def parseJsonMessage(jsonString):
    data = json.loads(jsonString)
    messageType = data.pop("type")
    return messageType, data

def broadcastServerPresence():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udpSocket:
        udpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while isActive:
            message = createJsonMessage("ServerAvailable", id=SERVER_ID, port=TCP_PORT)
            udpSocket.sendto(message, ('<broadcast>', UDP_PORT))
            time.sleep(10)

def initiateLeaderElection():
    global leader
    if connectedServers:
        maxId = max(connectedServers, key=lambda id: connectedServers[id]['port'])
        leader = maxId
        announceLeader(leader)
    else:
        leader = SERVER_ID
        print(f"No other servers connected. This server ({SERVER_ID}) is the leader.")

def serverConnectionManager(serverSocket, serverId, addr):
    global connectedServers, leader
    while not shutdownEvent.is_set():
        try:
            message = serverSocket.recv(BUFFER_SIZE)
            if not message:
                break

            messageType, data = parseJsonMessage(message.decode())

            if messageType == "election":
                processElectionMessage(serverSocket, serverId, data)
            elif messageType == "chatroom":
                processChatroomMessage(serverSocket, serverId, data)
            else:
                print(f"Unknown message type received from server {serverId}: {messageType}")

        except Exception as e:
            print(f"Error handling server {serverId}: {e}")
            break

    serverSocket.close()
    print(f"Connection with server {serverId} closed")
    if serverId in connectedServers:
        del connectedServers[serverId]
        if serverId == leader:
            print("Leader has disconnected. Initiating new leader election.")
            initiateLeaderElection()

def processElectionMessage(serverSocket, serverId, data):
    global leader
    senderId = data['id']
    isLeader = data['isLeader']

    if isLeader:
        leader = senderId
        announceLeader(leader)
    else:
        nextServer = getNextServer(serverId)
        if nextServer:
            connectedServers[nextServer]['socket'].send(createJsonMessage("election", id=senderId, isLeader=False))

def getNextServer(currentServerId):
    serverList = list(connectedServers.keys())
    if currentServerId in serverList:
        currentIndex = serverList.index(currentServerId)
        nextIndex = (currentIndex + 1) % len(serverList)
        return serverList[nextIndex]
    return None

def announceLeader(leaderId):
    leaderAnnouncement = createJsonMessage("leader_announcement", leader_id=leaderId)
    for serverInfo in connectedServers.values():
        serverInfo['socket'].send(leaderAnnouncement)
    print(f"Leader is server {leaderId}")

def processChatroomMessage(serverSocket, serverId, data):
    action = data['action']
    chatroom = data['chatroom']

    if action == "join":
        if chatroom not in discussionGroups:
            discussionGroups[chatroom] = set()
        discussionGroups[chatroom].add(serverId)
        announceServerJoined(chatroom, serverId)
    elif action == "leave":
        if chatroom in discussionGroups and serverId in discussionGroups[chatroom]:
            discussionGroups[chatroom].remove(serverId)
            announceServerLeft(chatroom, serverId)
    elif action == "message":
        if chatroom in discussionGroups and serverId in discussionGroups[chatroom]:
            broadcastChatroomMessage(chatroom, serverId, data['content'])

def announceServerJoined(chatroom, serverId):
    announcement = createJsonMessage("chatroom_update", action="joined", chatroom=chatroom, server_id=serverId)
    for sid in discussionGroups[chatroom]:
        if sid in connectedServers:
            connectedServers[sid]['socket'].send(announcement)

def announceServerLeft(chatroom, serverId):
    announcement = createJsonMessage("chatroom_update", action="left", chatroom=chatroom, server_id=serverId)
    for sid in discussionGroups[chatroom]:
        if sid in connectedServers:
            connectedServers[sid]['socket'].send(announcement)

def broadcastChatroomMessage(chatroom, senderId, content):
    message = createJsonMessage("chatroom_message", chatroom=chatroom, sender_id=senderId, content=content)
    for sid in discussionGroups[chatroom]:
        if sid in connectedServers:
            connectedServers[sid]['socket'].send(message)

def terminateServer(tcpSocket):
    global isActive
    isActive = False
    shutdownEvent.set()

    for serverInfo in connectedServers.values():
        try:
            serverInfo['socket'].close()
        except Exception as e:
            print(f"Error closing server connection: {e}")

    connectedServers.clear()
    discussionGroups.clear()
    tcpSocket.close()
    print("Server has been terminated.")

def displayConnectedServers():
    if connectedServers:
        print("Connected servers:")
        for serverId, info in connectedServers.items():
            print(f"Server {serverId} at {info['address']}:{info['port']}")
    else:
        print("No other servers connected.")

def findAvailablePort(start_port):
    port = start_port
    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', port))
                return port
        except OSError:
            port += 1

def main():
    global isActive, leader, TCP_PORT

    TCP_PORT = findAvailablePort(BASE_TCP_PORT)
    print(f"Server ID: {SERVER_ID}")
    print(f"TCP Port: {TCP_PORT}")

    broadcastThread = threading.Thread(target=broadcastServerPresence)
    broadcastThread.start()

    tcpSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcpSocket.bind(('', TCP_PORT))
    tcpSocket.listen()
    print(f"TCP server listening on port {TCP_PORT}")

    def manageConnections(tcpSocket):
        global connectedServers, isActive

        while isActive:
            try:
                serverSocket, addr = tcpSocket.accept()
                serverId = f"SERVER_{addr[1]}"  # Using port as a unique identifier
                connectedServers[serverId] = {'socket': serverSocket, 'address': addr[0], 'port': addr[1]}
                print(f"Connected to server {serverId} at {addr}")
                threading.Thread(target=serverConnectionManager, args=(serverSocket, serverId, addr)).start()

                if leader is None:
                    initiateLeaderElection()

            except Exception as e:
                print(f"Error in connection management: {e}")

        tcpSocket.close()

    connectionThread = threading.Thread(target=manageConnections, args=(tcpSocket,))
    connectionThread.start()

    while isActive:
        cmd = input("\nSelect an option\n1: Display current leader\n2: Show connected servers\n3: Terminate server\n")
        if cmd == '3':
            terminateServer(tcpSocket)
            break
        elif cmd == '2':
            displayConnectedServers()
        elif cmd == '1':
            if leader:
                print(f"Current leader is: {leader}")
            else:
                print("No leader has been elected yet.")
        else:
            print("Invalid command.")

    connectionThread.join()
    broadcastThread.join()

if __name__ == "__main__":
    main()