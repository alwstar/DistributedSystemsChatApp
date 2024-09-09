import socket
import struct
import threading
import concurrent.futures
import time
import json
import logging
from json import JSONDecodeError
import argparse

# logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# constants
BUFFER_SIZE = 1024
MULTICAST_BUFFER_SIZE = 10240
BASE_PORT = 50000

BROADCAST_ADDRESS = '255.255.255.255'
MULTICAST_GROUP_ADDRESS = '239.0.0.1'
MULTICAST_TTL = 2

LEADER_DEATH_TIME = 10

class Server:
    def __init__(self, instance_id):
        self.instance_id = instance_id
        self.ip_address = f"127.0.0.{instance_id}"
        self.shutdown_event = threading.Event()
        self.threads = []
        self.list_of_known_servers = []
        self.chat_rooms = {}
        self.lcr_ongoing = False
        self.is_leader = False
        self.last_message_from_leader_ts = time.time()
        self.direct_neighbour = ''
        self.leader_ip_address = ''
        self.lock = threading.Lock()
        self.participant = False

        # Dynamic port assignment
        self.broadcast_port_client = BASE_PORT + instance_id * 10
        self.broadcast_port_server = BASE_PORT + instance_id * 10 + 1
        self.tcp_client_port = BASE_PORT + instance_id * 10 + 2
        self.multicast_port_client = BASE_PORT + instance_id * 10 + 3
        self.multicast_port_server = BASE_PORT + instance_id * 10 + 4
        self.lcr_port = BASE_PORT + instance_id * 10 + 5
        self.heartbeat_port_server = BASE_PORT + instance_id * 10 + 6

    def start_server(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            methods = [
                self.handle_broadcast_server_requests,
                self.lcr,
                self.handle_leader_update,
                self.handle_leader_heartbeat,
                self.detection_of_missing_or_dead_leader,
                self.handle_broadcast_client_requests,
                self.handle_send_message_request
            ]

            for method in methods:
                self.threads.append(executor.submit(self.run_with_exception_handling, method))

            try:
                while not self.shutdown_event.is_set():
                    self.shutdown_event.wait(1)
            except KeyboardInterrupt:
                logger.info(f"Server {self.instance_id} shutdown initiated.")
                self.shutdown_event.set()
                for thread in self.threads:
                    thread.cancel()
            finally:
                executor.shutdown(wait=True)

    # ... (rest of the methods remain the same, just update the port and IP references)

    def handle_broadcast_server_requests(self):
        logger.debug(f'Server {self.instance_id} starting to listen for broadcast server requests')

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as listener_socket:
                listener_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                listener_socket.bind((self.ip_address, self.broadcast_port_server))
                listener_socket.settimeout(1)

                while not self.shutdown_event.is_set():
                    try:
                        msg, addr = listener_socket.recvfrom(BUFFER_SIZE)
                        logger.debug(f'Server {self.instance_id} received server discovery message via broadcast')

                        if addr[0] not in self.list_of_known_servers:
                            logger.debug(f"Server {self.instance_id} added with address {addr}")
                            self.list_of_known_servers.append(addr[0])

                        response_message = 'hello'.encode()
                        listener_socket.sendto(response_message, addr)
                        logger.debug(f'Server {self.instance_id} sent server hello to {addr}')

                    except socket.timeout:
                        continue
                    except socket.error as e:
                        logger.error(f'Socket error in server {self.instance_id}: {e}')
                    except Exception as e:
                        logger.error(f'Unexpected error in server {self.instance_id}: {e}')

        except socket.error as e:
            logger.error(f'Failed to set up listener socket for server {self.instance_id}: {e}')

    # ... (update other methods similarly)

def main():
    parser = argparse.ArgumentParser(description="Start a server instance")
    parser.add_argument("instance_id", type=int, help="Unique ID for this server instance")
    args = parser.parse_args()

    server = Server(args.instance_id)
    server.start_server()

if __name__ == "__main__":
    main()