import argparse
import multiprocessing
import socket
import sys

from utils import PacketHeader, PACKET_TYPE, compute_checksum


class RTPSender:
    def __init__(self, receiver_ip, receiver_port, window_size):
        """
        Initialize the RTP sender.
        :param receiver_ip: The IP address of the receiver.
        :param receiver_port: The port number on which the receiver is listening.
        :param window_size: The maximum number of outstanding packets.
        """
        self.receiver_ip = receiver_ip
        self.receiver_port = receiver_port
        self.window_size = window_size
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.timeout = 0.5
        self.base_seq_num = 0
        self.packet_count = 1
        self.is_initialized = False
        self.buffer = {}
        self.shared_dict = multiprocessing.Manager().dict()
        self._send_start_packet()

    def _send_start_packet(self):
        """
        Send a START packet to the receiver and wait for an ACK.
        The function will return when an ACK packet is received.
        """
        start_packet = PacketHeader(type=PACKET_TYPE.START, seq_num=self.base_seq_num, length=0)
        start_packet.checksum = compute_checksum(start_packet / b'')
        start_packet = start_packet / b''
        while True:
            self.socket.sendto(bytes(start_packet), (self.receiver_ip, self.receiver_port))
            print("Sent START packet")
            print("Waiting for ACK for START packet")
            p = multiprocessing.Process(target=self._wait_for_ack, args=())
            p.start()
            p.join(self.timeout)
            p.terminate()
            if len(self.shared_dict) > 0:
                self.base_seq_num = self.shared_dict["newest_ack"]
                if self.base_seq_num == self.packet_count:
                    print("ACK received for START packet")
                    self.is_initialized = True
                    break
                else:
                    print("ACK not received for START packet, resending")
            else:
                print("ACK not received for START packet, resending")

    def send(self, message: str):
        """
        Send a message to the receiver.
        :param message: The message to be sent.
        """
        if not self.is_initialized:
            raise Exception("Sender is not initialized. Please call start() method first.")
        # Encoding the message to bytes
        message_byte = message.encode('utf-8')
        # Split the message into chunks of size 1456 bytes
        chunks = [message_byte[i:i + 1456] for i in range(0, len(message), 1456)]
        # Send the chunks
        while True:
            if len(chunks) == 0 and len(self.buffer) == 0:
                print("All packets sent and acknowledged")
                break

            # Create a new packet if the buffer is not full
            while len(self.buffer) < self.window_size and len(chunks) > 0:
                chunk = chunks.pop(0)
                self.buffer[self.packet_count] = self._create_packet(chunk)
                self.packet_count += 1

            # Send the packets in the buffer
            for seq_num, packet in self.buffer.items():
                self.socket.sendto(bytes(packet), (self.receiver_ip, self.receiver_port))
                print('Sent packet:', seq_num)

            # Wait for an ACK packet
            p = multiprocessing.Process(target=self._wait_for_ack, args=())
            p.start()
            p.join(self.timeout)
            p.terminate()

            if len(self.shared_dict) > 0:
                self.base_seq_num = self.shared_dict["newest_ack"]
                print('ACK received:', self.base_seq_num)
                # Remove acknowledged packets from the buffer
                self.buffer = {k: v for k, v in self.buffer.items() if k >= self.base_seq_num}

            else:
                print("ACK not received, resending packets")

    def close_connection(self):
        """
        Close the RTP connection.
        """
        # Send a FIN packet to the receiver
        end_packet = PacketHeader(type=PACKET_TYPE.END, seq_num=self.packet_count, length=0)
        end_packet.checksum = compute_checksum(end_packet / b'')
        end_packet = end_packet / b''
        failed_count = 0
        while failed_count < 3:
            self.socket.sendto(bytes(end_packet), (self.receiver_ip, self.receiver_port))
            self.packet_count += 1
            print("Sent END packet")
            print("Waiting for ACK for END packet")
            p = multiprocessing.Process(target=self._wait_for_ack, args=())
            p.start()
            p.join(self.timeout)
            p.terminate()
            failed_count += 1
            if len(self.shared_dict) > 0:
                self.base_seq_num = self.shared_dict["newest_ack"]
                if self.base_seq_num == self.packet_count:
                    print("ACK received for END packet")
                    self.socket.close()
                    self.is_initialized = False
                    break

            else:
                print("ACK not received for END packet, resending")

        else:
            print("Failed to receive ACK for END packet after 3 attempts")
            print("Closing connection")
            self.socket.close()
            self.is_initialized = False

    def _create_packet(self, chunk):
        """
        Send a packet to the receiver.
        :param chunk: The chunk of data to be sent.
        """
        packet = PacketHeader(type=PACKET_TYPE.DATA, seq_num=self.packet_count, length=len(chunk))
        packet.checksum = compute_checksum(packet / chunk)
        packet = packet / chunk
        return packet

    def _wait_for_ack(self):
        """
        Wait for an ACK packet from the receiver.
        The function will return when an ACK packet is received.
        :return: None
        """
        while True:
            pkt, address = self.socket.recvfrom(1472)
            # Extract header and payload
            # The first 16 bytes are the header
            pkt_header = PacketHeader(pkt[:16])
            # The rest is the payload
            msg = pkt[16: 16 + pkt_header.length]
            self.base_seq_num = pkt_header.seq_num
            if pkt_header.type == PACKET_TYPE.ACK and self._compare_checksum(msg, pkt_header) \
                    and pkt_header.seq_num > self.shared_dict.get("newest_ack", -1):
                self.shared_dict["newest_ack"] = pkt_header.seq_num

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
    parser.add_argument(
        "message", type=str, help="The message to be sent to the receiver",
        nargs='?', default=None
    )
    args = parser.parse_args()

    message = args.message
    if message is None:
        message = sys.stdin.read()

    sender = RTPSender(args.receiver_ip, args.receiver_port, args.window_size)
    sender.send(message)
    sender.close_connection()


if __name__ == "__main__":
    main()
