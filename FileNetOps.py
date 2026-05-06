import os, time, struct, socket, threading

from Utils import TrialCount
from FileStream import ReadFileStream, WriteFileStream
from DataPacketOps import DataPacketOps
from MessageOps import MessageOps

# File header format
# file_size, suggested_chunk_size, rel_file_path
def _form_header(file_size: int, suggested_chunk_size: int,
                 rel_file_path: str) -> bytes:
    rel_file_path_len = len(rel_file_path)
    if rel_file_path_len > 0:
        return struct.pack("QII%ds" % rel_file_path_len, file_size, suggested_chunk_size, rel_file_path_len, rel_file_path.encode("utf-8"))
    else:
        return struct.pack("QII", file_size, suggested_chunk_size, 0)

_header_len = struct.calcsize("QII")
def _parse_header(header_data: bytes | None) -> tuple[int, int, str]:
    if len(header_data) < _header_len:
        return 0, 0, ""
    file_size, suggested_chunk_size, rel_file_path_len = struct.unpack("QII", header_data[:_header_len])
    if rel_file_path_len == 0:
        return file_size, suggested_chunk_size, ""
    elif rel_file_path_len > 0 and len(header_data) >= (_header_len + rel_file_path_len):
        rel_file_path, = struct.unpack_from("%ds" % rel_file_path_len, header_data[_header_len:])
        return file_size, suggested_chunk_size, rel_file_path.decode("utf-8", errors = "ignore")
    return 0, 0, ""

def _form_data_reply(status_code: int, chunk_size: int, file_pos: int) -> bytes:
    return struct.pack("IIQ", status_code, chunk_size, file_pos)

# Return: Status code, Data chunk size, File data pos
_header_reply_len = struct.calcsize("IIQ")
def _parse_data_reply(reply_data: bytes | None) -> tuple[int, int, int]:
    if len(reply_data) < _header_reply_len:
        return 0, 0, 0
    return struct.unpack("IIQ", reply_data)


def send_file(msg_conn: MessageOps, file_path: str, rel_file_path: str,
              suggested_chunk_size: int) -> bool:
    try:
        read_file = ReadFileStream(file_path)
    except Exception as e:
        print("Error: %s" % e)
        return False

    print("Info: Sending file \"%s\": %s\n" % (rel_file_path, file_path), end = "")

    # Send header
    trial_count = TrialCount()
    status_code = 0
    while status_code != 100 and trial_count.keep_on_trying():
        file_size = os.path.getsize(file_path)
        header = _form_header(file_size, suggested_chunk_size, rel_file_path)
        try:
            if not msg_conn.send(header):
                print("Warning: Failed to send file header.")
                trial_count.try_once()
                continue

            header_reply = msg_conn.recv()
        except ConnectionAbortedError as e:
            print("Error: %s." % e)
            return False
        
        if header_reply is None:
            print("Warning: Failed to receive header response.")
            trial_count.try_once()
            continue
        
        status_code, chunk_size, file_pos = _parse_data_reply(header_reply)
        if status_code == 403:
            print("Error: Server stop file sending.")
            return False

        trial_count.try_once()
    
    if trial_count.failed():
        print("Error: Too many trials, file not sent successfully.")
        return False

    # Send file
    prev_time = time.time()
    prev_file_size = file_pos
    prev_file_pos  = file_pos
    trial_count.reset()
    while status_code != 200 and trial_count.keep_on_trying():
        file_data = read_file.read(file_pos, chunk_size)
        try:
            if not msg_conn.send(file_data):
                print("Warning: Failed to receive header response.")
                trial_count.try_once()
                continue

            data_reply = msg_conn.recv()
        except ConnectionAbortedError as e:
            print("Error: %s." % e)
            return False
        
        if data_reply is None:
            trial_count.try_once()
            continue

        status_code, chunk_size, file_pos = _parse_data_reply(data_reply)
        if status_code == 403:
            print("Error: Server stop file sending.")
            return False

        if prev_file_pos < file_pos:
            trial_count.reset()
            prev_file_pos = file_pos
        else:
            trial_count.try_once()
        
        # Cal sending speed
        cur_time = time.time()
        if cur_time - prev_time > 2.0: # update every 2s
            cur_file_size = file_pos
            send_speed = float(cur_file_size - prev_file_size) / (cur_time - prev_time) / 1024.0
            file_perc  = float(cur_file_size) / float(file_size) * 100.0
            print("Info: %.2f%% sent at %.1fkB/s.\n" % (file_perc, send_speed), end = "")
            prev_time  = cur_time
            prev_file_size = cur_file_size

    # Completed
    if trial_count.failed():
        print("Error: Failed to send file \"%s\".\n" % rel_file_path, end = "")
        return False
    
    read_file.close()
    print("Info: Sent file \"%s\".\n" % rel_file_path, end = "")
    return True


def send_files_in_folder(msg_conn: MessageOps,
                         folder_path: str, rel_root_path: str,
                         suggested_chunk_size: int) -> bool:
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        
        if os.path.isfile(file_path):
            rel_file_path = os.path.join(rel_root_path, filename).replace('/', '\\')
            if not send_file(msg_conn, file_path, rel_file_path, suggested_chunk_size):
                return False
        
        elif os.path.isdir(file_path):
            child_rel_root_path = os.path.join(rel_root_path, filename)
            if not send_files_in_folder(msg_conn, file_path, child_rel_root_path, suggested_chunk_size):
                return False
    
    return True


# Send an empty header to indicate that no more file to be send
def send_file_ending(msg_conn: MessageOps) -> None:
    ending_header = _form_header(0, 0, "")
    
    try:
        msg_conn.send(ending_header)
    except:
        pass


def recv_file(msg_conn: MessageOps, root_folder_path: str, chunk_size: int = 0) -> bool:
    file_size = -1
    trial_count = TrialCount()
    while file_size != 0:
        # Receive header
        trial_count.reset()
        while trial_count.keep_on_trying():
            try:
                header_data = msg_conn.recv()
            except ConnectionAbortedError as e:
                print("Error: %s." % e)
                return False
            
            if header_data is None:
                trial_count.try_once()
                continue

            break

        if trial_count.failed():
            print("Error: Failed to receive file header.")
            return False

        file_size, suggested_chunk_size, rel_file_path = _parse_header(header_data)
        print("Info: Receiving file \"%s\".\n" % rel_file_path, end = "")

        if chunk_size == 0:
            chunk_size = suggested_chunk_size
        
        file_path  = os.path.join(root_folder_path, rel_file_path).replace('/', "\\")
        write_file = WriteFileStream(file_path, file_size)

        prev_time  = time.time()
        prev_file_size = write_file.cur_file_size

        
        header_reply = _form_data_reply(100, chunk_size, write_file.cur_file_size)
        
        try:
            if not msg_conn.send(header_reply):
                print("Warning: Failed to send header reply.")
                
                file_data = msg_conn.recv()
        except ConnectionAbortedError as e:
            print("Error: %s." % e)
            return False

        if file_data is not None:
            file_pos = write_file.write(file_data)

        # Receive file
        while not write_file.is_completed():
            data_reply = _form_data_reply(100, chunk_size, file_pos)
            msg_conn.send(data_reply)

            if file_data is not None:
                file_data = msg_conn.recv()
                file_pos  = write_file.write(file_data)

            cur_time = time.time()
            if cur_time - prev_time > 2.0: # update every 2s
                cur_file_size = file_pos
                send_speed = float(cur_file_size - prev_file_size) / (cur_time - prev_time) / 1024.0
                file_perc = float(cur_file_size) / float(file_size) * 100.0
                print("Info: %.2f%% received at %.1fkB/s.\n" % (file_perc, send_speed), end = "")
                prev_time = cur_time
                prev_file_size = cur_file_size

        # Completed
        data_reply = _form_data_reply(200, chunk_size, file_pos)
        msg_conn.send(data_reply)
        print("Info: Received file \"%s\".\n" % rel_file_path, end = "")

        # Get next file header
        header = msg_conn.recv()
        file_size, suggested_chunk_size, rel_file_path = _parse_header(header)

    return True


def send_file_client(server_ip: str, server_port: int,
                     passwd: bytes, file_path: str,
                     suggested_chunk_size: int = 1024*64) -> bool:
    client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_sock.connect((server_ip, server_port))
    print("Info: Connected to server at %s:%d\n" % (server_ip, server_port), end = "")
    data_conn = DataPacketOps(client_sock)
    msg_conn  = MessageOps(data_conn)

    res = False
    if os.path.isfile(file_path):
        res = send_file(msg_conn, file_path, os.path.basename(file_path), suggested_chunk_size)
    elif os.path.isdir(file_path):
        res = send_files_in_folder(msg_conn, file_path, "./", suggested_chunk_size)

    send_file_ending(msg_conn)
    msg_conn.close()
    return res


class _RecvFileThread(threading.Thread):
    def __init__(self, server: socket.socket, passwd: bytes,
                 root_path: str, chunk_size: int | None = None):
        super().__init__()
        self.server     = server
        self.passwd     = passwd
        self.root_path  = root_path
        self.chunk_size = chunk_size
        self.running    = True
    
    def run(self):
        while self.running:
            server_sock, _ = self.server.accept()
            data_conn = DataPacketOps(server_sock)
            msg_conn  = MessageOps(data_conn)
            recv_file(msg_conn, self.root_path, self.chunk_size)

    def stop_after_last_file(self):
        self.running = False


def recv_file_server(server_ip: str, server_port: int,
                     passwd: bytes, root_path: str,
                     chunk_size: int = 0) -> _RecvFileThread:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((server_ip, server_port))
    server.listen(5) # Listen for incoming connections
    print("Info: Server is listening on %s:%d\n" % (server_ip, server_port), end = "")

    thread = _RecvFileThread(server, passwd, root_path, chunk_size)
    thread.start()
    return thread
