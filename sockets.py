import socket

def close_socket_ports(start_port, end_port):
    for port in range(start_port, end_port + 1):
        try:
            # Create a new socket to bind to the port
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                
                # Attempt to bind the socket to the port
                s.bind(('localhost', port))
                
                # If successful, the port was open and is now bound to our socket
                print(f"Port {port} is open. Closing the socket.")
                # No need to do anything else, the 'with' statement will close the socket
        except socket.error as e:
            # If the port is already in use or any other error occurs, it will print the message
            print(f"Could not close port {port}: {e}")

# Define the range of ports to close
start_port = 6000
end_port = 6008

# Run the function to close the sockets
close_socket_ports(start_port, end_port)
