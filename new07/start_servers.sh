#!/bin/bash

# Navigate to the directory
cd /path/to/DistributedSystemsChatApp/new06

# Start the first server on port 6001 in a new terminal window
gnome-terminal -- bash -c "python3 s1.py 6001; exec bash"

# Wait for 2 seconds before starting the next server
sleep 2

# Start the second server on port 6002 in a new terminal window
gnome-terminal -- bash -c "python3 s1.py 6002; exec bash"

# Wait for 2 seconds before starting the next server
sleep 2

# Start the third server on port 6003 in a new terminal window
gnome-terminal -- bash -c "python3 s1.py 6003; exec bash"

# Wait for 2 seconds before starting the next server
sleep 2

# Start the fourth server on port 6004 in a new terminal window
gnome-terminal -- bash -c "python3 s1.py 6004; exec bash"
