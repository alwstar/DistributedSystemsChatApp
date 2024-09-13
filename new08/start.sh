#!/bin/bash

# Navigate to the directory
cd /path/to/DistributedSystemsChatApp/new06

# Start the first server on port 6001 in a new terminal window
gnome-terminal -- bash -c "python3 s1.py; exec bash"

# Wait for 2 seconds before starting the next server
sleep 2

# Start the second server on port 6002 in a new terminal window
gnome-terminal -- bash -c "python3 c1.py; exec bash"