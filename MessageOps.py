import struct, time, itertools
import hashlib, socket

from Utils import TrialCount, Random
from DataPacketOps import DataPacketOps
#from Convertor import Convertor
#from Compressor import Compressor

class Message:
    # Message format:
    # 1. msg id (2 bytes, part of header info)
    # 2. rand id (2 bytes, part of header info)
    # 3. msg_flag (2 bytes, part of header info)
    # 4. sha256_checksum (32 bytes, including header info and data)
    # 5. data
    header_info_fmt = "HHH"
    header_info_len = struct.calcsize(header_info_fmt)
    sha256_len      = hashlib.sha256().digest_size

    header_fmt = "HHH%ds" % sha256_len # header_info + sha256
    header_len = struct.calcsize(header_fmt)

    # msg_flag:
    ERROR      = 0 # Data: no data
    HEADER     = 1 # Data: max_apply_packet_num/max_apply_packet_num (2 bytes), packet_num (8 bytes), total_data_len (8 bytes)
    APPLY_DATA = 2 # Data: apply_packet_num (2 bytes), packet1_id (8 bytes), packet2_id (8 bytes)...
    DATA       = 3 # Data: packet_id (8 bytes), packet_data_len (4 bytes), packet_data
    COMPLETION = 4 # Data: 0-ask for completion, 1-confirm completion (1 byte)

    min_header_msg_len     = struct.calcsize("HQQ")
    min_apply_data_msg_len = struct.calcsize("H")
    min_data_msg_len       = struct.calcsize("QI")

    @staticmethod
    def cal_msg_data_size(data_packet_max_size: int) -> int:
        return data_packet_max_size - Message.header_len - Message.min_data_msg_len

    def __init__(self, msg_id: int = 0, msg_rand_id: int = 0,
                 msg_flag: int = 0, data: bytes = b"",
                 checksum: int | None = None):
        self.msg_id      = msg_id
        self.rand_id     = msg_rand_id
        self.flag        = msg_flag
        self.header_info_data = None
        #
        self.checksum    = checksum
        #
        self.data        = data

    # Helper function
    def _form_header_info_data(self) -> bytes:
        return struct.pack(Message.header_info_fmt,
                           self.msg_id & 0xffff,
                           self.rand_id & 0xffff,
                           self.flag)

    # Read data
    def parse(self, msg_data: bytes) -> bool:
        if len(msg_data) < Message.header_len:
            self.msg_id   = 0
            self.rand_id  = 0
            self.flag     = 0
            self.header_info_data = None
            self.checksum = b""
            self.data     = b""
            return False
        self.msg_id, self.rand_id, self.flag, self.checksum = struct.unpack(Message.header_fmt, msg_data[:Message.header_len])
        self.header_info_data = msg_data[:Message.header_info_len]
        self.data = msg_data[Message.header_len:]
        return True
    
    def data_is_correct(self) -> bool:
        sha256 = hashlib.sha256()
        if self.header_info_data is None:
            self.header_info_data = self._form_header_info_data()
        sha256.update(self.header_info_data)
        sha256.update(self.data)
        return self.checksum == sha256.digest()

    # Write data
    def __bytes__(self) -> bytes:
        self.header_info_data = self._form_header_info_data()
        sha256 = hashlib.sha256()
        sha256.update(self.header_info_data)
        sha256.update(self.data)
        self.checksum = sha256.digest()
        return self.header_info_data + self.checksum + self.data

    def is_new_msg(self, prev_msg_id: int) -> bool:
        return self.msg_id > prev_msg_id
    
    def is_cur_msg(self, cur_msg_id, cur_msg_rand_id: int) -> bool:
        return self.msg_id == cur_msg_id and self.rand_id == cur_msg_rand_id

    def is_error(self) -> bool:
        return self.flag == Message.ERROR
    
    def is_header(self) -> bool:
        return self.flag == Message.HEADER

    def is_apply_data(self) -> bool:
        return self.flag == Message.APPLY_DATA
    
    def is_data(self) -> bool:
        return self.flag == Message.DATA

    def is_completion(self):
        return self.flag == Message.COMPLETION

    def form_error_msg(self) -> bytes:
        self.flag = Message.ERROR
        self.data = b""
        return bytes(self)

    def form_header_msg(self, max_apply_packet_num: int, packet_num: int, total_data_len: int) -> bytes:
        self.flag = Message.HEADER
        self.data = struct.pack("HQQ", max_apply_packet_num, packet_num, total_data_len)
        return bytes(self)

    # Only for HEADER message
    # Return: max_apply_packet_num, packet_num, total_data_len
    def parse_as_header_msg(self) -> tuple[int | None, int | None, int | None]:
        if len(self.data) < Message.min_header_msg_len:
            return None, None, None
        return struct.unpack("HQQ", self.data[:Message.min_header_msg_len])

    def form_apply_data_msg(self, applied_data_ids: tuple[int]) -> bytes:
        self.flag        = Message.APPLY_DATA
        applied_data_num = len(applied_data_ids)
        self.data        = struct.pack("H"+"Q"*applied_data_num, applied_data_num, *applied_data_ids)
        return bytes(self)

    # Only for APPLY_DATA message
    # Return: applied_packet_ids
    def parse_as_apply_data_msg(self) -> tuple[int] | None:
        if len(self.data) < 2:
            return None
        applied_packet_num, = struct.unpack("H", self.data[:2])
        data_fmt = "H" + "Q" * applied_packet_num
        data_len = struct.calcsize(data_fmt)
        if len(self.data) < data_len:
            return None
        return struct.unpack(data_fmt, self.data[:data_len])[1:]

    def form_data_msg(self, packet_id: int, packet_data: bytes) -> bytes:
        packet_data_len = len(packet_data)
        self.flag   = Message.DATA
        data_header = struct.pack("QI", packet_id, packet_data_len)
        self.data   = data_header + packet_data
        return bytes(self)

    # Only for DATA message
    # Return packet_id, packet_data_len, packet_data
    def parse_as_data_msg(self) -> tuple[int | None, int | None, bytes | None]:
        if len(self.data) < Message.min_data_msg_len:
            return None, None, None
        packet_id, packet_data_len = struct.unpack("QI", self.data[:Message.min_data_msg_len])
        return packet_id, packet_data_len, self.data[Message.min_data_msg_len:]

    def form_ask_completion_msg(self) -> bytes:
        self.flag = Message.COMPLETION
        self.data = b"\x00"
        return bytes(self)
    
    def form_confirm_completion_msg(self) -> bytes:
        self.flag = Message.COMPLETION
        self.data = b"\x01"
        return bytes(self)
    
    # Only for COMPLETION message
    # Return 0-ask for completion, 1-confirm completion
    def parse_as_completion_msg(self) -> int | None:
        if len(self.data) < 1:
            return None
        return struct.unpack("B", self.data[:1])[0]

    def __repr__(self):
        if self.flag == Message.ERROR:
            return "Error (%d %d)" % (self.msg_id, self.rand_id)
        elif self.flag == Message.HEADER:
            max_apply_packet_num, packet_num, data_size = self.parse_as_header_msg()
            return "Header (%d %d): Win size %d, Packet num %d, Data size %d" % (self.msg_id, self.rand_id,
                                                                                 max_apply_packet_num, packet_num, data_size)
        elif self.flag == Message.APPLY_DATA:
            apply_packet_ids = self.parse_as_apply_data_msg()
            return ("App Data (%d %d): Packet num %d, Packet ids:" + " %d" * len(apply_packet_ids)) \
                % (self.msg_id, self.rand_id, len(apply_packet_ids), *apply_packet_ids)
        elif self.flag == Message.DATA:
            packet_id, packet_data_size, _ = self.parse_as_data_msg()
            return "Data (%d %d): Packet id %d, Packet data size %d" % (self.msg_id, self.rand_id, packet_id, packet_data_size)
        elif self.flag == Message.COMPLETION:
            state_id = self.parse_as_completion_msg()
            if state_id == 0:
                state = "Ask"
            elif state_id == 1:
                state = "Confirm"
            else:
                state = "Unknown"
            return "Completion (%d %d): %s" % (self.msg_id, self.rand_id, state)


# Ensure the data of any size is received without loss, error or wrong order
# Do not handle "ConnectionAbortedError" Error
class MessageOps:
    _default_max_apply_packet_num = 5

    def _gen_rand_msg_id(self) -> int:
        return self.rand.extract_number() & 0xffff

    def __init__(self, data_packet_conn: DataPacketOps | socket.socket, *,
                 max_apply_packet_num:   int | None = None,
                 trial_count: int | None = None):
        if type(data_packet_conn) is DataPacketOps:
            self.data_packet_conn = data_packet_conn
        else:
            self.data_packet_conn = DataPacketOps(data_packet_conn)
        self.send_max_apply_packet_num = max_apply_packet_num if type(max_apply_packet_num) is int else MessageOps._default_max_apply_packet_num
        self.trial_count      = TrialCount(trial_count)
        
        self.cur_msg_id       = 0
        self.cur_msg_rand_id  = 0
        self.rand             = Random(int(time.time() * 100.0))

    def set_timeout(self, time_out: float) -> None:
        self.data_packet_conn.set_timeout(time_out)
    
    def close(self) -> None:
        self.data_packet_conn.close()
    
    # One layer above the 
    def recv(self) -> bytes | None:
        # Receive header
        self.trial_count.reset()
        packet_num           = 0
        total_data_len       = 0
        max_apply_packet_num = 0
        header_msg           = Message()
        while self.trial_count.keep_on_trying():
            header_msg_bytes = self.data_packet_conn.recv()
            if header_msg_bytes is None:
                self.trial_count.try_once()
                continue
            
            if header_msg.parse(header_msg_bytes) and header_msg.is_new_msg(self.cur_msg_id) and \
                header_msg.data_is_correct():
                # print("recv (header): %s\n" % header_msg, end = "")
                if header_msg.is_error():
                    return None # Connection abort
                elif header_msg.is_header():
                    self.cur_msg_id      = header_msg.msg_id
                    self.cur_msg_rand_id = header_msg.rand_id
                    max_apply_packet_num, packet_num, total_data_len = header_msg.parse_as_header_msg()
                    if packet_num > 0:
                        break # Success
            
            self.trial_count.try_once()
        
        if self.trial_count.failed():
            return None

        # Start receving data
        to_receive_packet_id_set: set[int] = set(range(packet_num))
        data_packets: list[bytes] = []
        app_data_msg = Message(self.cur_msg_id, self.cur_msg_rand_id)
        data_msg     = Message(self.cur_msg_id, self.cur_msg_rand_id)
        self.trial_count.reset()
        while self.trial_count.keep_on_trying():
            # Send apply data message
            if len(to_receive_packet_id_set) == 0:
                break # Completed

            apply_data_ids = list(itertools.islice(to_receive_packet_id_set, max_apply_packet_num))
            app_data_msg_bytes = app_data_msg.form_apply_data_msg(apply_data_ids)
            self.data_packet_conn.send(app_data_msg_bytes)
            # print("recv (app data): %s\n" % app_data_msg, end = "")

            # Receive data
            received_valid_data = False
            for _ in range(len(apply_data_ids) * 3 // 2): # Ideally, loop until no data in unblock mode
                data_msg_bytes = self.data_packet_conn.recv()
                if data_msg_bytes is None:
                    break
                
                if not data_msg.parse(data_msg_bytes) or \
                    not data_msg.is_cur_msg(self.cur_msg_id, self.cur_msg_rand_id) or \
                    not data_msg.data_is_correct():
                    continue
                # print("recv (data): %s\n" % data_msg, end = "")

                if data_msg.is_error() or data_msg.is_completion():
                    return None # Connection aborted
                elif not data_msg.is_data():
                    continue
                
                packet_id, packet_data_len, packet_data = data_msg.parse_as_data_msg()
                if packet_id < 0 or len(packet_data) != packet_data_len:
                    continue
                
                # Receive data successfully
                if packet_id in apply_data_ids:
                    apply_data_ids.remove(packet_id)
                    to_receive_packet_id_set.remove(packet_id)
                    data_packets.append((packet_id, packet_data))
                    received_valid_data = True

                if len(apply_data_ids) == 0:
                    break
            
            if received_valid_data:
                self.trial_count.reset()
            else:
                self.trial_count.try_once()

        # Completed
        completion_msg = Message(self.cur_msg_id, self.cur_msg_rand_id)
        ask_completion_bytes = completion_msg.form_ask_completion_msg()
        confirm_completion_bytes = completion_msg.form_confirm_completion_msg()
        has_asked_for_completion = False
        has_been_asked_for_completion = False
        self.trial_count.reset()
        while self.trial_count.keep_on_trying():
            if not has_asked_for_completion:
                self.data_packet_conn.send(ask_completion_bytes)

            completion_bytes1 = self.data_packet_conn.recv()
            if completion_bytes1 is not None and completion_msg.parse(completion_bytes1) and \
                completion_msg.is_cur_msg(self.cur_msg_id, self.cur_msg_rand_id) and \
                completion_msg.data_is_correct() and \
                completion_msg.is_completion():
                # print("recv (completion): %s\n" % completion_msg, end = "")
                if completion_msg.parse_as_completion_msg() == 1:
                    has_asked_for_completion = True
                elif completion_msg.parse_as_completion_msg() == 0:
                    has_been_asked_for_completion = True
            
            completion_bytes2 = self.data_packet_conn.recv()
            if completion_bytes2 is not None and completion_msg.parse(completion_bytes2) and \
                completion_msg.is_cur_msg(self.cur_msg_id, self.cur_msg_rand_id) and \
                completion_msg.data_is_correct() and \
                completion_msg.is_completion():
                # print("recv (completion): %s\n" % completion_msg, end = "")
                if completion_msg.parse_as_completion_msg() == 1:
                    has_asked_for_completion = True
                elif completion_msg.parse_as_completion_msg() == 0:
                    has_been_asked_for_completion = True

            if has_been_asked_for_completion:
                self.data_packet_conn.send(confirm_completion_bytes)
            
            if has_asked_for_completion and has_been_asked_for_completion:
                break
            
            self.trial_count.try_once()
        
        # Combine data
        final_data = None
        if not self.trial_count.failed() and len(to_receive_packet_id_set) == 0:
            data_packets.sort(key = lambda x: x[0])
            final_data = b''.join([ data_packet[1] for data_packet in data_packets ])
            if len(final_data) != total_data_len:
                final_data = None
            # Decyrt
            # Uncompressed

        return final_data

    def send(self, data: bytes) -> bool:
        self.cur_msg_id += 1
        self.cur_msg_rand_id = self._gen_rand_msg_id()
        error_msg = Message(self.cur_msg_id, self.cur_msg_rand_id)
        error_msg_bytes = error_msg.form_error_msg()

        # Send header
        self.trial_count.reset()
        packet_data_size   = Message.cal_msg_data_size(self.data_packet_conn.max_data_size)
        data_len           = len(data)
        packet_num         = (data_len + packet_data_size - 1) // packet_data_size
        header_msg         = Message(self.cur_msg_id, self.cur_msg_rand_id)
        header_msg_bytes   = header_msg.form_header_msg(self.send_max_apply_packet_num, packet_num, data_len)
        apply_data_msg     = Message(self.cur_msg_id, self.cur_msg_rand_id)
        applied_packet_ids = None
        while self.trial_count.keep_on_trying():
            self.data_packet_conn.send(header_msg_bytes)
            
            apply_data_msg_bytes = self.data_packet_conn.recv()
            if apply_data_msg_bytes is None:
                self.trial_count.try_once()
                continue
            
            if apply_data_msg.parse(apply_data_msg_bytes) and \
                apply_data_msg.is_cur_msg(self.cur_msg_id, self.cur_msg_rand_id) and \
                apply_data_msg.data_is_correct():
                # print("send (app data): %s\n" % apply_data_msg, end = "")

                if apply_data_msg.is_error() or apply_data_msg.is_completion():
                    return False # Connection abort
                elif apply_data_msg.is_apply_data():
                    applied_packet_ids = apply_data_msg.parse_as_apply_data_msg()
                    if applied_packet_ids is not None:
                        break
            
            self.trial_count.try_once()
        
        if self.trial_count.failed():
            self.data_packet_conn.send(error_msg_bytes)
            return False

        self.trial_count.reset()
        data_msg     = Message(self.cur_msg_id, self.cur_msg_rand_id)
        app_data_msg = Message(self.cur_msg_id, self.cur_msg_rand_id)
        while self.trial_count.keep_on_trying():
            if applied_packet_ids is None:
                self.trial_count.try_once()
                continue
            
            applied_packet_num = len(applied_packet_ids)
            # Too many packets applied, send failure message to close connection
            if applied_packet_num > self.send_max_apply_packet_num:
                self.data_packet_conn.send(error_msg_bytes)
                return False

            if applied_packet_num > 0:
                self.trial_count.reset()
            else:
                self.trial_count.try_once()
                continue

            for packet_id in applied_packet_ids:
                packet_data_id0 = packet_id * packet_data_size
                packet_data_idn = min(packet_data_id0 + packet_data_size, data_len)
                packet_data     = data[packet_data_id0:packet_data_idn]
                data_msg_bytes  = data_msg.form_data_msg(packet_id, packet_data)
                self.data_packet_conn.send(data_msg_bytes)
                # print("send (data): %s\n" % data_msg, end = "")

            # Receive data
            applied_packet_ids = None
            app_data_msg_bytes = self.data_packet_conn.recv()
            if app_data_msg_bytes is None:
                continue
            
            if app_data_msg.parse(app_data_msg_bytes) and \
                app_data_msg.is_cur_msg(self.cur_msg_id, self.cur_msg_rand_id) and \
                app_data_msg.data_is_correct():
                # print("send (app data): %s\n" % app_data_msg, end = "")
                if app_data_msg.is_error():
                    return False
                elif app_data_msg.is_completion():
                    break
                elif app_data_msg.is_apply_data():
                    applied_packet_ids = app_data_msg.parse_as_apply_data_msg()

        if self.trial_count.failed():
            self.data_packet_conn.send(error_msg_bytes)
            return False
        
        # Completed
        self.trial_count.reset()
        completion_msg = Message(self.cur_msg_id, self.cur_msg_rand_id)
        while self.trial_count.keep_on_trying():
            confirm_completion_msg_bytes = completion_msg.form_confirm_completion_msg()
            self.data_packet_conn.send(confirm_completion_msg_bytes)
            ask_completion_msg_bytes = completion_msg.form_ask_completion_msg()
            self.data_packet_conn.send(ask_completion_msg_bytes)
            
            confirm_completion_msg_bytes = self.data_packet_conn.recv()
            if completion_msg.parse(confirm_completion_msg_bytes) and \
                completion_msg.is_cur_msg(self.cur_msg_id, self.cur_msg_rand_id) and \
                completion_msg.data_is_correct() and \
                completion_msg.is_completion():
                # print("send (completion): %s\n" % completion_msg, end = "")
                break
            
        return True
