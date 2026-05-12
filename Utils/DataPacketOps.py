import socket, struct, hashlib

# Possible network error
# 1. Data cannot be sent/recived
# 2. Remote computer is closed
# 3. Receive incorrect data
# class NetworkError(Exception):
#     def __init__(self, msg: str):
#         super.__init__(msg)


# Lostest level operation for sending and receiving a data packet
# Ensure the data packet sent or received is the right size
# Checksum for data correctness
# Data packet size should be <= _tcp_buf_size
# Sender and receiver should use the same designated data packet size
# Do not ensure the packet has been sent and received successfully
# Do not handle "ConnectionAbortedError" Error
class DataPacketOps:
    _time_out = 1.0 # Increase for bad network condition
    
    _tcp_buf_size = 1024 * 4 # Must be larger than 4+16
    
    # Data packet format:
    # 1. Header: data size (2 bytes), header checksum (2 bytes) - Two's Complement
    # 2. Body: data
    # 3. Checksum (16 bytes): md5 checksum including data header and body
    _header_len = struct.calcsize("HH")
    _md5_checksum_len = hashlib.md5().digest_size

    @staticmethod
    def get_max_data_size() -> int:
        return DataPacketOps._tcp_buf_size - DataPacketOps._header_len - DataPacketOps._md5_checksum_len

    def __init__(self, conn:    socket.socket,
                 max_data_size: int | None = None,
                 time_out:      float | None = _time_out):
        self.conn = conn
        if time_out is not None:
            self.conn.settimeout(time_out)
        self.data_bytes_buf: list[bytes] = []

        self.max_data_size   = max_data_size if type(max_data_size) is int else self.get_max_data_size()
        self.max_packet_size = self._header_len + self.max_data_size + self._md5_checksum_len
        self.two_max_packet_size = self.max_packet_size * 2

        # For parsing packet data
        self.parsed_byte0_num = 0
        self.cur_byte0_off = 0
        self.cur_data_id = 0
        self.cur_byte_off = 0

        self.data_size_buf = bytearray(DataPacketOps._header_len // 2)
        self.header_checksum_buf = bytearray(DataPacketOps._header_len // 2)
        self.data_buf = bytearray(self.max_packet_size)
        self.md5_checksum_buf = bytearray(DataPacketOps._md5_checksum_len)

    def set_timeout(self, time_out: float = _time_out) -> None:
        self.conn.settimeout(time_out)

    def close(self) -> None:
        self.conn.close()

    def send(self, data: bytes) -> None:
        data_len = len(data)
        assert data_len <= self.max_data_size, "Oversize data to sent (size limit %d)" % self.max_data_size
        data_packet = struct.pack("HH", data_len, (~data_len+1) & 0xFFFF) + data
        md5_checksum = hashlib.md5(data_packet).digest()
        self.conn.sendall(data_packet + md5_checksum)

    def _recv_new_data(self):
        data = self.conn.recv(self._tcp_buf_size)
        if not data: # Remote end closed
            raise ConnectionAbortedError()
        self.data_bytes_buf.append(data)

    # Set the position of the first byte to be parsed
    def _init_byte0(self) -> int:
        self.cur_data_id = 0
        self.cur_byte_off = self.cur_byte0_off - 1
        if len(self.data_bytes_buf) == 0:
            self._recv_new_data()

        self.parsed_byte0_num = 0
        return self.parsed_byte0_num

    # Move the first parsed byte
    def _next_byte0(self) -> int:
        self.cur_byte0_off += 1
        if self.cur_byte0_off >= len(self.data_bytes_buf[0]):
            self.cur_byte0_off = 0
            self.data_bytes_buf.pop(0)
            if len(self.data_bytes_buf) == 0:
                self._recv_new_data()
        
        self.cur_data_id = 0
        self.cur_byte_off = self.cur_byte0_off - 1
        
        self.parsed_byte0_num += 1
        return self.parsed_byte0_num

    def _next_byte0_after_cur_byte(self) -> int:
        self.parsed_byte0_num += self.cur_byte_off - self.cur_byte0_off + 1
        
        self.cur_byte0_off = self.cur_byte_off + 1
        if self.cur_byte0_off >= len(self.data_bytes_buf[0]):
            self.cur_byte0_off = 0
            self.data_bytes_buf.pop(0)
        
        self.cur_data_id = 0
        self.cur_byte_off = self.cur_byte0_off - 1
        return self.parsed_byte0_num

    def _next_byte(self) -> bytes:
        self.cur_byte_off += 1
        if self.cur_byte_off >= len(self.data_bytes_buf[self.cur_data_id]):
            self.cur_data_id += 1
            if self.cur_data_id >= len(self.data_bytes_buf):
                self._recv_new_data()
            self.cur_byte_off = 0
        
        return self.data_bytes_buf[self.cur_data_id][self.cur_byte_off]

    def recv(self) -> bytes | None:
        try:
            parsed_byte0_num = self._init_byte0()
            while parsed_byte0_num < self.two_max_packet_size:
                # Check whether this is the header
                self.data_size_buf[0] = self._next_byte()
                self.data_size_buf[1] = self._next_byte()
                self.header_checksum_buf[0] = self._next_byte()
                self.header_checksum_buf[1] = self._next_byte()
                data_size, = struct.unpack("H", self.data_size_buf)
                header_checksum, = struct.unpack("H", self.header_checksum_buf)
                # Not header
                if data_size > self.max_data_size or (data_size + header_checksum) != 65536:
                    parsed_byte0_num = self._next_byte0()
                    continue

                for data_id in range(data_size):
                    self.data_buf[data_id] = self._next_byte()
                
                for data_id in range(DataPacketOps._md5_checksum_len):
                    self.md5_checksum_buf[data_id] = self._next_byte()

                md5_check_sum = hashlib.md5(self.data_size_buf + self.header_checksum_buf + self.data_buf[:data_size]).digest()
                # Find the right packet
                if self.md5_checksum_buf == md5_check_sum:
                    self._next_byte0_after_cur_byte()
                    return bytes(self.data_buf[:data_size])

                parsed_byte0_num = self._next_byte0()
        
        except TimeoutError as e:
            pass # Return None if timeout
        
        # Failed to receive data
        return None
