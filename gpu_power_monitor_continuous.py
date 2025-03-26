#!/usr/bin/env python3
import subprocess
import re
import csv
import time
import signal
import sys
import os
from datetime import datetime

FIFO_PATH = '/tmp/power_monitor_fifo'

def signal_handler(sig, frame):
    """Handle Ctrl+C to exit gracefully"""
    global process
    if process:
        process.terminate()
    if os.path.exists(FIFO_PATH):
        os.unlink(FIFO_PATH)
    print('\nMonitoring stopped. Data saved to gpu_power_continuous.csv')
    sys.exit(0)

def set_fifo_permissions():
    """Set permissions on FIFO file to allow non-root users to write"""
    try:
        # Get the user ID from the SUDO_UID environment variable
        uid = int(os.environ.get('SUDO_UID', 1000))
        gid = int(os.environ.get('SUDO_GID', 1000))
        
        # Change ownership of the FIFO
        os.chown(FIFO_PATH, uid, gid)
        # Set permissions to allow owner read/write
        os.chmod(FIFO_PATH, 0o600)
    except Exception as e:
        print(f"Warning: Could not set FIFO permissions: {e}")

# Global variable for the subprocess
process = None
monitoring = False

def main():
    global process, monitoring
    
    # Register signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    # Create FIFO if it doesn't exist
    if not os.path.exists(FIFO_PATH):
        os.mkfifo(FIFO_PATH)
        # Set appropriate permissions
        set_fifo_permissions()
    
    print("Power monitor ready. Waiting for commands...")
    print(f"Send commands through: {FIFO_PATH}")
    print("Commands: 'start' to begin monitoring, 'stop' to end monitoring")
    
    # CSV file path
    csv_file = 'gpu_power_continuous.csv'
    
    # Initialize CSV file with header
    with open(csv_file, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Timestamp', 'GPU Power (mW)'])
    
    # Set permissions on CSV file too
    try:
        uid = int(os.environ.get('SUDO_UID', 1000))
        gid = int(os.environ.get('SUDO_GID', 1000))
        os.chown(csv_file, uid, gid)
        os.chmod(csv_file, 0o644)  # Make CSV readable by everyone
    except Exception as e:
        print(f"Warning: Could not set CSV file permissions: {e}")
    
    # Sample interval in milliseconds
    sample_interval = 100  # 0.1 seconds
    
    try:
        while True:
            # Open FIFO for reading
            with open(FIFO_PATH, 'r') as fifo:
                while True:
                    command = fifo.readline().strip()
                    if command == 'start' and not monitoring:
                        monitoring = True
                        print("Starting power monitoring...")
                        
                        # Run powermetrics
                        cmd = ['powermetrics', '--samplers', 'gpu_power', '-i', str(sample_interval), '--show-process-energy']
                        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)
                        
                        # Regular expression to match GPU power
                        power_pattern = re.compile(r'GPU Power: (\d+) mW')
                        
                        # Process output line by line
                        while monitoring:
                            line = process.stdout.readline()
                            if not line:
                                break
                                
                            match = power_pattern.search(line)
                            if match:
                                gpu_power = int(match.group(1))
                                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                                
                                # Save to CSV
                                with open(csv_file, 'a', newline='') as csvfile:
                                    writer = csv.writer(csvfile)
                                    writer.writerow([timestamp, gpu_power])
                                
                                print(f"{timestamp} - GPU Power: {gpu_power} mW")
                                
                    elif command == 'stop' and monitoring:
                        monitoring = False
                        if process:
                            process.terminate()
                            process = None
                        print("Monitoring stopped")
                    
                    elif command == 'exit':
                        raise KeyboardInterrupt
    
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        if process:
            process.terminate()
        if os.path.exists(FIFO_PATH):
            os.unlink(FIFO_PATH)

if __name__ == "__main__":
    main() 