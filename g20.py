import subprocess
import time
import sys

def start_process(command):
    if sys.platform.startswith('win'):
        return subprocess.Popen(command, creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:
        return subprocess.Popen(command)

def main():
    server_script = "server.py"
    client_script = "client.py"
    
    # Start 3 server instances
    server_processes = []
    for port in [6000, 6001, 6002]:
        print(f"Starting server on port {port}")
        server_processes.append(start_process(["python", server_script, str(port)]))
        time.sleep(2)  # Wait for 2 seconds between server starts
    
    # Wait a bit longer for servers to initialize
    time.sleep(5)
    
    # Start 2 client instances
    client_processes = []
    for i in range(2):
        print(f"Starting client {i+1}")
        client_processes.append(start_process(["python", client_script]))
        time.sleep(2)  # Wait for 2 seconds between client starts
    
    print("All servers and clients have been started.")
    print("Press Ctrl+C to terminate all processes.")
    
    try:
        # Wait for user interrupt
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Terminating all processes...")
        
        # Terminate all processes
        for process in server_processes + client_processes:
            process.terminate()
        
        # Wait for all processes to finish
        for process in server_processes + client_processes:
            process.wait()
        
        print("All processes have been terminated.")

if __name__ == "__main__":
    main()