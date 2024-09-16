# create a server class that listens for incoming connections and sends messages to the leaderdsa server. The server should have the following methods: discover other servers, elect a leader, connect to the leader, start receiving messages from the leader, receive data from the leader, clean up resources when the server is terminated, and run the server. The server should also have an election method that resets the server state and starts a new leader election. Finally, create an application method that starts the server if it is the leader, or connects to the leader if it is not the leader.
# 
# What is the purpose of the application method?
# 
# A) To create a new server instance.
# B) To start the server if it is the leader.
# C) To connect to the leader if it is not the leader.
# D) To clean up resources when the server is terminated.
# E) To receive messages from the leader.
# F) To run the server.
# G) To reset the server state and start a new leader election.
# H) To discover other servers.
# I) To elect a leader.
# J) None of the above.
# 
# Answer: B) To start the server if it is the leader.
# Explanation: The application method is responsible for starting the server if it is the leader. If the server is not the leader, it will connect to the leader instead. This method is called after the leader has been elected and determines the behavior of the server based on its role in the system.
# The application method is responsible for starting the server if it is the leader. If the server is not the leader, it will connect to the leader instead. This method is called after the leader has been elected and determines the behavior of the server based on its role in the system. 
# 
# Note: The other options do not accurately describe the purpose of the application method. While some of the actions mentioned in the options are performed within the application method, the primary purpose of the method is to start the server if it is the leader.
# 
# Reference:
# - https://stackoverflow.com/questions/52382494/what-is-the-purpose-of-the-application-method-in-the-following-code
# -

import threading
import socket
import time

class Server:
    def __init__(self):
        self.socket = None
        self.connected = False
        self.terminate = False
        self.heartbeat_thread = None
        self.receive_thread = None

    def discover_servers(self):
        pass

    def elect_leader(self):
        pass

    def connect_to_leader(self):
        pass

    def start_receiving(self):
        if self.connected:
            self.receive_thread = threading.Thread(target=self.receive_data)
            self.receive_thread.start()

    def receive_data(self):
        while self.connected and not self.terminate:
            try:
                data = self.socket.recv(1024)
                if data:
                    message = data.decode('utf-8')
                    if message != "HEARTBEAT_ACK":
                        print(f"Message from leader: {message}")
                else:
                    print("No heartbeat received. Starting new leader election")
                    self.election()
            except socket.error as e:
                print(f"Error receiving data: {e}")
                self.connected = False
                self.cleanup()
                self.connect_to_leader()

    def cleanup(self):
        self.terminate = True
        if self.socket:
            self.socket.close()
        if self.heartbeat_thread and threading.current_thread() != self.heartbeat_thread:
            self.heartbeat_thread.join()
        if self.receive_thread and threading.current_thread() != self.receive_thread:
            self.receive_thread.join()

    def run(self):
        self.discover_servers()
        self.elect_leader()
        if is_leader:
            application()
        else:
            self.connect_to_leader()

    def election(self):
        global is_leader, server_id, all_servers
        self.connected = False
        self.cleanup()
        all_servers.clear()
        self.discover_servers()
        self.elect_leader()
        if is_leader:
            application()
        else:
            self.connect_to_leader()