import os, socket, threading

from Utils.MessageOps import MessageOps
from Utils.FileNetOps import send_file, send_files_in_folder, \
    send_file_ending, recv_file

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
    server.listen(60) # Listen for incoming connections
    print("Info: Server is listening on %s:%d\n" % (server_ip, server_port), end = "")

    thread = _RecvFileThread(server, passwd, root_path, chunk_size)
    thread.start()
    return thread


server_ip = socket.gethostbyname(socket.gethostname())
server_port = 10025

recv_server = recv_file_server(server_ip, server_port, b"abcde", ".\\recv")

#send_file_client(server_ip, server_port, b"abcde", r".\send\vps.png")
send_file_client(server_ip, server_port, b"abcde", r".\send")

recv_server.stop_after_last_file()
