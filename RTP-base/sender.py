import argparse
import socket
import sys

from utils import PacketHeader, compute_checksum


def sender(receiver_ip, receiver_port, window_size, message):
    """TODO: Open socket and send message from sys.stdin."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    pkt_header = PacketHeader(type=2, seq_num=10, length=14)
    pkt_header.checksum = compute_checksum(pkt_header / message)
    pkt = pkt_header / message
    s.sendto(bytes(pkt), (receiver_ip, receiver_port))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "receiver_ip", help="The IP address of the host that receiver is running on"
    )
    parser.add_argument(
        "receiver_port", type=int, help="The port number on which receiver is listening"
    )
    parser.add_argument(
        "window_size", type=int, help="Maximum number of outstanding packets"
    )
    parser.add_argument(
        "message", type=str, help="The message to be sent to the receiver", 
        nargs='?', default=None
    )
    args = parser.parse_args()
    
    # If message is not provided, read from stdin
    message = args.message
    if message is None:
        message = sys.stdin.read()

    sender(args.receiver_ip, args.receiver_port, args.window_size, message)


if __name__ == "__main__":
    main()
