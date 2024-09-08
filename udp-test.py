import socket

def udp_send():
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    message = "Test-Nachricht"
    udp_socket.sendto(message.encode('utf-8'), ('127.0.0.1', 12345))  # Sende an den Port 12345
    print(f"Nachricht gesendet an Port 12345")

if __name__ == "__main__":
    udp_send()
