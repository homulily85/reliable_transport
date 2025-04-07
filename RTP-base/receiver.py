import argparse
import socket

from utils import PacketHeader, compute_checksum, PACKET_TYPE


class RTPReceiver:
    def __init__(self, receiver_ip, receiver_port, window_size):
        """
        Initialize the RTP receiver.
        :param receiver_ip: The IP address of the host that receiver is running on.
        :param receiver_port: The port number on which receiver is listening.
        :param window_size: The maximum number of outstanding packets.
        """
        self.receiver_ip = receiver_ip
        self.receiver_port = receiver_port
        self.window_size = window_size
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((self.receiver_ip, self.receiver_port))
        self.is_initialized = False
        self.current_sender_ip = None
        self.current_sender_port = None
        self.buffer = {}
        self.expect_next = 1
        self.current_mes = ''

    def start(self):
        """
        Start the receiver and listen for incoming packets.
        """
        while True:
            pkt, address = self.socket.recvfrom(1472)
            # Extract header and payload
            # The first 16 bytes are the header
            pkt_header = PacketHeader(pkt[:16])
            # The rest is the payload
            msg = pkt[16: 16 + pkt_header.length]
            # Check packet type
            match pkt_header.type:
                case PACKET_TYPE.START:
                    if not self.is_initialized:
                        print(f"Received START packet from {address[0]}:{address[1]}")
                        if self._compare_checksum(msg, pkt_header):
                            print("Checksum verified")
                            self.is_initialized = True
                            self.current_sender_ip = address[0]
                            self.current_sender_port = address[1]
                            print(
                                f"Connected to sender {self.current_sender_ip}:{self.current_sender_port}")
                        else:
                            print("Checksum verification failed")
                            continue

                        # Send ACK for START packet
                        self._send_ack(self.expect_next)
                        print("Sent ACK for START packet")

                    elif (address[0] == self.current_sender_ip and
                          address[1] == self.current_sender_port):
                        print("Received duplicate START packet from the same sender")
                        # Send ACK for duplicate START packet
                        self._send_ack(self.expect_next)
                    else:
                        print(f"Received START packet from {address[0]}:{address[1]}")
                        print("Ignored this START packet as receiver is already initialized")

                case PACKET_TYPE.DATA:
                    if self.is_initialized:
                        print(
                            f"Received DATA packet {pkt_header.seq_num} from {address[0]}:{address[1]}")
                        print(f"Packet length: {pkt_header.length}")
                        print(f'message: {msg}')
                        if self._compare_checksum(msg, pkt_header):
                            print("Checksum verified")
                            if pkt_header.seq_num == self.expect_next:
                                print(f"Packet {self.expect_next} received in order")
                                self.current_mes += msg.decode('utf-8')
                                print('Current message:', self.current_mes)
                                self.expect_next += 1
                                # Check if there are buffered packets
                                while self.expect_next in self.buffer:
                                    print(f"Buffered packet {self.expect_next} received")
                                    buff_mess = self.buffer.pop(self.expect_next)
                                    self.current_mes += buff_mess
                                    print('Current message:', self.current_mes)
                                    self.expect_next += 1
                                # Send ACK for the received packet
                                self._send_ack(self.expect_next)
                                print(f"Sent ACK for packet {self.expect_next - 1}")
                            elif pkt_header.seq_num > self.expect_next:
                                print(
                                    f"Packet {pkt_header.seq_num} received out of order, expected {self.expect_next}"
                                    f". Buffering it")
                                if len(self.buffer) < self.window_size and pkt_header.seq_num not in self.buffer:
                                    self.buffer[pkt_header.seq_num] = msg.decode('utf-8')
                                    self.buffer = dict(sorted(self.buffer.items()))
                                    print(f"Buffered packet {pkt_header.seq_num}")
                                else:
                                    print(
                                        f"Buffer full or packet is buffered, dropping packet {pkt_header.seq_num}")
                                # Send ACK for the last in-order packet
                                self._send_ack(self.expect_next)
                                print(f"Sent ACK for packet {self.expect_next - 1}")
                            else:
                                print(
                                    f"Packet {pkt_header.seq_num} already received. Ignored")
                                # Send ACK for the last in-order packet
                                self._send_ack(self.expect_next)
                                print(f"Sent ACK for packet {self.expect_next - 1}")
                        else:
                            print("Checksum verification failed")
                    else:
                        print("Receiver not initialized, ignoring DATA packet")

                case PACKET_TYPE.END:
                    if self.is_initialized:
                        print(f"Received END packet from {address[0]}:{address[1]}")
                        if self._compare_checksum(msg, pkt_header):
                            print("Checksum verified")
                            print("Sending ACK for END packet")
                            self.expect_next += 1
                            self._send_ack(self.expect_next)
                            print("End of transmission")
                            self.is_initialized = False
                            self.current_sender_ip = None
                            self.current_sender_port = None
                            self.socket.close()
                            print("Message received:", self.current_mes)
                            return
                        else:
                            print("Checksum verification failed")
                    else:
                        print("Receiver not initialized, ignoring END packet")

    def _send_ack(self, seq_num):
        """
        Send an ACK packet to the sender.
        :param seq_num: The sequence number of the packet being acknowledged.
        """
        ack_packet = PacketHeader(type=PACKET_TYPE.ACK, seq_num=seq_num, length=0)
        ack_packet.checksum = compute_checksum(ack_packet / b'')
        self.socket.sendto(bytes(ack_packet), (self.current_sender_ip, self.current_sender_port))

    @staticmethod
    def _compare_checksum(msg, pkt_header):
        """
        Compare the checksum of the packet with the computed checksum.
        :param msg: The message to be sent.
        :param pkt_header: The packet header.
        """
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
    args = parser.parse_args()

    RTPReceiver(args.receiver_ip, args.receiver_port, args.window_size).start()


if __name__ == "__main__":
    main()
