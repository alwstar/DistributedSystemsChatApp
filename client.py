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
myId = None
currentChatroom = None
leaderIp = None
leaderPort = None
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

def listenForLeader():
    """Listen for leader announcements via UDP."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udpSocket:
        udpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udpSocket.bind(('', SERVER_UDP_PORT))

        while True:
            try:
                message, serverAddr = udpSocket.recvfrom(BUFFER_SIZE)
                rawMessage = message.decode()
                print(f"Raw message received: {rawMessage}")
                
                # Parse the message and look for a leader announcement
                messageType, data = parseXmlMessage(rawMessage)
                if messageType == "leader_announcement":
                    leaderIp = data['leader_ip']  # Extract the IP directly from XML
                    leaderPort = int(data['leader_port'])  # Extract the port as an integer
                    return leaderIp, leaderPort  # Return leader IP and port for connection
            except Exception as e:
                print(f"Error listening for leader: {e}")
                continue

def sendMessageToServer(tcpSocket, messageType, **kwargs):
    try:
        message = createXmlMessage(messageType, **kwargs)
        tcpSocket.send(message)
    except ConnectionError:
        print("Connection to the server lost.")
        tcpSocket.close()

def receiveMessages(tcpSocket):
    global leaderIp, leaderPort
    while not shutdownEvent.is_set():
        try:
            message = tcpSocket.recv(BUFFER_SIZE)
            if not message:
                break

            messageType, data = parseXmlMessage(message)

            if messageType == "leader_announcement":
                leaderIp = data['leader_ip']
                leaderPort = int(data['leader_port'])
                print(f"New leader is {leaderIp}:{leaderPort}")
                reconnectToLeader()
            elif messageType == "chatroom_message":
                print(f"[{data['chatroom']}] {data['sender_ip']}:{data['sender_port']}: {data['content']}")
            else:
                print(f"Received unknown message type: {messageType}")

        except Exception as e:
            print(f"Error receiving message: {e}")
            break

def reconnectToLeader():
    global tcpSocket, leaderIp, leaderPort
    try:
        print(f"Reconnecting to new leader at {leaderIp}:{leaderPort}...")
        tcpSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcpSocket.connect((leaderIp, leaderPort))
        print("Reconnected to the new leader.")
        threading.Thread(target=receiveMessages, args=(tcpSocket,)).start()
    except Exception as e:
        print(f"Failed to reconnect to leader: {e}")
        time.sleep(5)

def main():
    global myId, tcpSocket, currentChatroom, leaderIp, leaderPort

    try:
        # Step 1: Discover the current leader via UDP
        print("Listening for the current leader...")
        leaderIp, leaderPort = listenForLeader()
        print(f"Discovered leader at {leaderIp}:{leaderPort}")

        # Step 2: Connect to the discovered leader
        tcpSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcpSocket.connect((leaderIp, leaderPort))
        print(f"Connected to the server at {leaderIp}:{leaderPort}")

        myId = tcpSocket.getsockname()[1]
        print(f"My ID is {myId}")

        threading.Thread(target=receiveMessages, args=(tcpSocket,)).start()

        while True:
            print("\nChoose an option:")
            print("1. Enter a chatroom")
            print("2. Exit current chatroom")
            print("3. Send a message in current chatroom")
            print("4. Disconnect client")
            choice = input("Enter your choice (1-4): ")

            if choice == '1':
                chatroom = input("Enter chatroom name: ")
                currentChatroom = chatroom
                sendMessageToServer(tcpSocket, "chatroom", action="join", chatroom=chatroom)
            elif choice == '2':
                if currentChatroom:
                    sendMessageToServer(tcpSocket, "chatroom", action="leave", chatroom=currentChatroom)
                    currentChatroom = None
                else:
                    print("You are not in any chatroom.")
            elif choice == '3':
                if currentChatroom:
                    message = input("Type your message: ")
                    sendMessageToServer(tcpSocket, "chatroom", action="message", chatroom=currentChatroom, content=message)
                else:
                    print("You are not in any chatroom.")
            elif choice == '4':
                print("Disconnecting client...")
                shutdownEvent.set()
                tcpSocket.close()
                break
            else:
                print("Invalid choice. Please try again.")

    except Exception as e:
        print(f"An error occurred: {e}")

    print("Client disconnected.")

if __name__ == "__main__":
    main()
