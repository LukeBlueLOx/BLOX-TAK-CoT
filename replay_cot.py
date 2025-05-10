import CoT  # https://pypi.org/project/PyCoT
import socket
import ssl
import os
import logging
import datetime
import time
import re
from dateutil.parser import parse as parse_date

# Configure logging for this script
logging.basicConfig(
    filename="cot_replay.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# TAK server settings
TAK_IP = "192.168.1.17"
TAK_PORT = 8089

# SSL certificate paths
CERT_DIR = "/home/luke_blue_lox/PycharmProjects/BLOX-TAK-CoT/certs"
CLIENT_CERT = os.path.join(CERT_DIR, "LukeBlueLOx.pem")
CLIENT_KEY = os.path.join(CERT_DIR, "LukeBlueLOx.key")
CA_CERT = os.path.join(CERT_DIR, "truststore-root.pem")

# Configure SSL context
ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
ssl_context.load_cert_chain(certfile=CLIENT_CERT, keyfile=CLIENT_KEY)
ssl_context.load_verify_locations(cafile=CA_CERT)
ssl_context.verify_mode = ssl.CERT_REQUIRED

# Path to the input log file
LOG_FILE = "/home/luke_blue_lox/PycharmProjects/BLOX-TAK-CoT/cot.log"
SAT_ID = 6073  # NORAD ID for COSMOS 482 DESCENT CRAFT
SAT_NAME = "COSMOS 482 DESCENT CRAFT"
REFRESH_INTERVAL = 10  # Delay between sending CoT messages (in seconds)

def parse_log_for_positions(start_time, end_time):
    """
    Parse the log file for CoT position entries within the given time range.
    Returns a list of tuples: (timestamp, lat, lon, alt).
    """
    positions = []
    cot_regex = re.compile(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - INFO - CoT for .*: lat=(-?\d+\.\d+), lon=(-?\d+\.\d+), alt=(\d+\.\d+)"
    )

    try:
        with open(LOG_FILE, "r") as file:
            for line in file:
                match = cot_regex.search(line)
                if match:
                    timestamp_str, lat, lon, alt = match.groups()
                    timestamp = parse_date(timestamp_str)
                    if start_time <= timestamp <= end_time:
                        positions.append((timestamp, float(lat), float(lon), float(alt)))
    except FileNotFoundError:
        logging.error(f"Log file not found: {LOG_FILE}")
        print(f"Error: Log file not found: {LOG_FILE}")
        return []
    except Exception as e:
        logging.error(f"Error parsing log file: {e}")
        print(f"Error parsing log file: {e}")
        return []

    return positions

def send_cot_to_tak(lat, lon, alt, timestamp):
    """
    Send a CoT message to the TAK server for the given position and timestamp.
    """
    try:
        # Establish SSL connection
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        wrapped_sock = ssl_context.wrap_socket(sock, server_hostname=TAK_IP)
        wrapped_sock.connect((TAK_IP, TAK_PORT))
        wrapped_sock.settimeout(1)

        # Create CoT event
        stale = timestamp + datetime.timedelta(minutes=5)
        cot_event = CoT.Event(
            version="2.0",
            type="a-n-G-U-U-S-R-S",
            access="Undefined",
            uid=f"SAT.{SAT_ID}",
            time=timestamp,
            start=timestamp,
            stale=stale,
            how="m-g",
            qos="2-i-c",
            point=CoT.Point(
                lat=lat,
                lon=lon,
                hae=alt,
                ce=9999999,
                le=9999999
            ),
            detail={"contact": {"callsign": SAT_NAME}}
        )

        # Send CoT message
        wrapped_sock.sendall(bytes(cot_event.xml(), encoding="utf-8"))

        # Log and print position
        position_message = f"CoT for {SAT_NAME}: lat={lat}, lon={lon}, alt={alt}, time={timestamp}"
        print(position_message)
        logging.info(position_message)

        # Try to receive response
        try:
            response = wrapped_sock.recv(1024).decode("utf-8")
            log_message = f"Sent SSL CoT to {TAK_IP}:{TAK_PORT}, Response: {response}"
        except socket.timeout:
            log_message = f"Sent SSL CoT to {TAK_IP}:{TAK_PORT}, No response"
        print(log_message)
        logging.info(log_message)

        wrapped_sock.close()
        return True

    except (ConnectionRefusedError, ssl.SSLError) as e:
        error_message = f"SSL connection error to TAK server: {e}"
        print(error_message)
        logging.error(error_message)
        return False
    except Exception as e:
        error_message = f"Unexpected error sending CoT: {e}"
        print(error_message)
        logging.error(error_message)
        return False

def main():
    # Get time range from user
    print("Enter the time range for replaying CoT messages (format: YYYY-MM-DD HH:MM:SS)")
    try:
        start_time_str = input("Start time: ")
        end_time_str = input("End time: ")
        start_time = parse_date(start_time_str)
        end_time = parse_date(end_time_str)

        if start_time >= end_time:
            print("Error: Start time must be before end time")
            logging.error("Start time is not before end time")
            return

        # Parse log file for positions
        positions = parse_log_for_positions(start_time, end_time)
        if not positions:
            print("No positions found in the log for the specified time range")
            logging.info("No positions found for the specified time range")
            return

        print(f"Found {len(positions)} positions to replay")
        logging.info(f"Found {len(positions)} positions to replay")

        # Send each position as a CoT message
        for timestamp, lat, lon, alt in positions:
            if send_cot_to_tak(lat, lon, alt, timestamp):
                time.sleep(REFRESH_INTERVAL)  # Wait before sending the next message
            else:
                print("Failed to send CoT, continuing to next position")
                logging.error("Failed to send CoT, continuing to next position")

    except ValueError as e:
        print(f"Error: Invalid date format - {e}")
        logging.error(f"Invalid date format: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")
        logging.error(f"Unexpected error: {e}")

if __name__ == "__main__":
    main()