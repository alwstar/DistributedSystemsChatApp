import socket

def udp_receive():
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.bind(("127.0.0.1", 12345))  # Lausche auf Port 12345
    print("Warte auf Nachrichten auf Port 12345...")
    message, addr = udp_socket.recvfrom(1024)
    print(f"Empfangene Nachricht: {message.decode('utf-8')} von {addr}")

if __name__ == "__main__":
    udp_receive()
