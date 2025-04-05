import argparse
import multiprocessing
import socket
import sys

from utils import PacketHeader, PACKET_TYPE, compute_checksum


class UDPSender:
    def __init__(self, receiver_ip, receiver_port, window_size):
        """
        Initialize the UDP sender.
        :param receiver_ip: The IP address of the receiver.
        :param receiver_port: The port number on which the receiver is listening.
        :param window_size: The maximum number of outstanding packets.
        """
        self.receiver_ip = receiver_ip
        self.receiver_port = receiver_port
        self.window_size = window_size
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.is_initialized = False
        self.timeout = 5
        self.base_seq_num = 0
        self.next_seq_num = 0

        self._send_start_packet()

    def _send_start_packet(self):
        """
        Send a START packet to the receiver and wait for an ACK.
        This is a blocking call.
        The function will return when an ACK packet is received.
        :return: None
        """
        start_packet = PacketHeader(type=PACKET_TYPE.START, seq_num=self.next_seq_num, length=0)
        self.next_seq_num += 1
        start_packet.checksum = compute_checksum(start_packet / b'')
        while True:
            self.socket.sendto(bytes(start_packet), (self.receiver_ip, self.receiver_port))
            print("Sent START packet")
            print("Waiting for ACK for START packet")
            p = multiprocessing.Process(target=self._wait_for_ack, args=())
            p.start()
            p.join(self.timeout)
            if p.is_alive():
                print("Timeout waiting for ACK for START packet")
                p.terminate()
            else:
                self.is_initialized = True
                print("Received ACK for START packet")
                break

    def _send_end_packet(self):
        """
        Send an END packet to the receiver.
        """
        end_packet = PacketHeader(type=PACKET_TYPE.END, seq_num=self.next_seq_num, length=0)
        end_packet.checksum = compute_checksum(end_packet / b'')
        self.socket.sendto(bytes(end_packet), (self.receiver_ip, self.receiver_port))
        print("Sent END packet")

    def _wait_for_ack(self):
        """
        Wait for an ACK packet from the receiver.
        This is a blocking call.
        The function will return when an ACK packet is received.
        :return: None
        """
        while True:
            pkt, address = self.socket.recvfrom(1472)
            # Extract header and payload
            # The first 16 bytes are the header
            pkt_header = PacketHeader(pkt[:16])
            self.base_seq_num = pkt_header.seq_num
            if pkt_header.type == PACKET_TYPE.ACK and self.base_seq_num == self.next_seq_num:
                print(f"Received ACK for packet {self.base_seq_num - 1}")
                break

    @staticmethod
    def _compare_checksum(msg, pkt_header):
        pkt_checksum = pkt_header.checksum
        pkt_header.checksum = 0
        computed_checksum = compute_checksum(pkt_header / msg)
        if pkt_checksum != computed_checksum:
            return False
        return True


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

    message = args.message
    if message is None:
        message = sys.stdin.read()

    sender = UDPSender(args.receiver_ip, args.receiver_port, args.window_size)


if __name__ == "__main__":
    main()
