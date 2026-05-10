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
              suggested_chunk_size: int, remove_after_sending: bool = False) -> bool:
    try:
        read_file = ReadFileStream(file_path)
    except Exception as e:
        print("Send Error: %s" % e)
        return False

    print("Send Info: Sending file \"%s\"  (%.1f kB) - %s\n" % \
          (rel_file_path, float(read_file.file_size)/1024.0, file_path), end = "")

    # Send header
    status_code = 0
    trial_count = TrialCount()
    while status_code != 100 and trial_count.keep_on_trying():
        file_size = os.path.getsize(file_path)
        header = _form_header(file_size, suggested_chunk_size, rel_file_path)
        try:
            if msg_conn.send(header):
                header_reply = msg_conn.recv()
            else:
                print("Send Warning: Failed to send file header.")
                trial_count.try_once()
                continue
        except Exception as e:
            print("Send Error: Connection Error (%s).\n" % e, end = "")
            return False
        
        if header_reply is None:
            print("Send Warning: Failed to receive header response.")
            trial_count.try_once()
            continue
        
        status_code, chunk_size, file_pos = _parse_data_reply(header_reply)
        if status_code == 403:
            print("Send Error: Server stop file sending.")
            return False

        trial_count.try_once()
    
    if trial_count.failed():
        print("Send Error: Too many trials, file not sent successfully.")
        return False

    # Send file
    prev_time = time.time()
    prev_file_size = file_pos
    prev_file_pos  = file_pos
    trial_count.reset()
    while status_code != 200 and trial_count.keep_on_trying():
        file_data = read_file.read(file_pos, chunk_size)
        try:
            if msg_conn.send(file_data):
                data_reply = msg_conn.recv()
            else:
                print("Send Warning: Failed to receive header response.")
                trial_count.try_once()
                continue
        except Exception as e:
            print("Send Error: Connection Closed (%s).\n" % e, end = "")
            return False
        
        if data_reply is None:
            trial_count.try_once()
            continue

        status_code, chunk_size, file_pos = _parse_data_reply(data_reply)
        if status_code == 403:
            print("Send Error: Server stop file sending.")
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
            print("Send Info: %.2f%% sent at %.1fkB/s.\n" % (file_perc, send_speed), end = "")
            prev_time  = cur_time
            prev_file_size = cur_file_size

    # Completed
    read_file.close()

    if trial_count.failed():
        print("Send Error: Failed to send file \"%s\".\n" % rel_file_path, end = "")
        return False

    print("Send Info: Sent file \"%s\" (%.1f kB).\n" % \
            (rel_file_path, float(read_file.file_size)/1024.0), end = "")
    if remove_after_sending:
        os.remove(file_path)
    return True


def send_files_in_folder(msg_conn: MessageOps,
                         folder_path: str, rel_root_path: str,
                         suggested_chunk_size: int,
                         remove_after_sending: bool = False) -> bool:
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        
        if os.path.isfile(file_path):
            rel_file_path = os.path.join(rel_root_path, filename).replace('/', '\\')
            if not send_file(msg_conn, file_path, rel_file_path,
                             suggested_chunk_size, remove_after_sending):
                return False
        
        elif os.path.isdir(file_path):
            child_rel_root_path = os.path.join(rel_root_path, filename)
            if not send_files_in_folder(msg_conn, file_path, child_rel_root_path,
                                        suggested_chunk_size, remove_after_sending):
                return False
    
    if len(os.listdir(folder_path)) == 0:
        os.rmdir(folder_path)
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
    while True:
        # Receive header
        trial_count.reset()
        while trial_count.keep_on_trying():
            try:
                header_data = msg_conn.recv()
            except Exception as e:
                print("Recv Error: Cannot recv header, connection closed (%s).\n" % e, end = "")
                return False
            
            if header_data is None:
                trial_count.try_once()
                continue

            break

        if trial_count.failed():
            print("Recv Error: Failed to receive file header.\n", end = "")
            return False

        file_size, suggested_chunk_size, rel_file_path = _parse_header(header_data)
        if file_size <= 0:
            break
        print("Recv Info: Receiving file \"%s\" (%.1f kB).\n" % (rel_file_path, float(file_size) / 1024.0), end = "")
        
        # Receive file data
        if chunk_size == 0:
            chunk_size = suggested_chunk_size
        
        file_path  = os.path.join(root_folder_path, rel_file_path).replace('/', "\\")
        write_file = WriteFileStream(file_path, file_size)
        
        prev_time  = time.time()
        prev_file_size = write_file.cur_file_size
        trial_count.reset()
        while not write_file.is_completed() and trial_count.keep_on_trying():
            data_reply = _form_data_reply(100, chunk_size, write_file.cur_file_size)
            
            file_data = None
            try:
                if msg_conn.send(data_reply):
                    file_data = msg_conn.recv()
                else:
                    print("Recv Warning: Failed to send data reply.\n", end = "")
                    trial_count.try_once()
                    continue
            except Exception as e:
                print("Recv Error: Connection Closed (%s).\n" % e, end = "")
                return False

            if file_data is None:
                trial_count.try_once()
                continue

            file_pos = write_file.write(file_data)
            trial_count.reset()

            cur_time = time.time()
            if cur_time - prev_time > 2.0: # update every 2s
                cur_file_size = file_pos
                send_speed = float(cur_file_size - prev_file_size) / (cur_time - prev_time) / 1024.0
                file_perc = float(cur_file_size) / float(file_size) * 100.0
                print("Recv Info: %.2f%% received at %.1fkB/s.\n" % (file_perc, send_speed), end = "")
                prev_time = cur_time
                prev_file_size = cur_file_size
        
        # Completed
        data_reply = _form_data_reply(200, chunk_size, write_file.cur_file_size)
        try:
            msg_conn.send(data_reply)
        except Exception as e:
            pass
        
        if trial_count.failed():
            print("Recv Info: Failed to receive file \"%s\".\n" % rel_file_path, end = "")
        else:
            print("Recv Info: Received file \"%s\" (%.1f kB).\n" % \
                  (rel_file_path, float(write_file.cur_file_size)/1024.0), end = "")

    return True


def send_file_client(server_ip: str, server_port: int,
                     passwd: bytes, file_path: str,
                     suggested_chunk_size: int = 1024*64) -> bool:
    client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_sock.connect((server_ip, server_port))
    print("Info: Connected to server at %s:%d\n" % (server_ip, server_port), end = "")
    msg_conn  = MessageOps(client_sock)

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
            self.server.setblocking(False)
            try:
                server_sock, _ = self.server.accept()
            except:
                continue
            self.server.setblocking(True)

            msg_conn  = MessageOps(server_sock)
            recv_file(msg_conn, self.root_path, self.chunk_size)
            server_sock.close()

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
