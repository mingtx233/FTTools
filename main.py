import os, socket

from MessageOps import MessageOps
from FileNetOps import send_file, send_files_in_folder, send_file_ending, recv_file

class Server:
    _default_server_ip = socket.gethostbyname(socket.gethostname())
    _default_server_port = 10023
    _default_root_path = "./"
    _default_chunk_size = 1024*50

    def __init__(self, server_ip: str, server_port: int, passwd: bytes,
                 root_path: str, chunk_size: int):
        self.server_ip = server_ip if server_ip else self._default_server_ip
        self.server_port = server_port if server_port > 0 else self._default_server_port
        self.passwd = passwd
        self.root_path = root_path if root_path else self._default_root_path
        self.chunk_size = chunk_size if chunk_size > 0 else self._default_chunk_size

    def run(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind((self.server_ip, self.server_port))
        server.listen(5)
        print("Info: Server is listening on %s:%d" % (self.server_ip, self.server_port))

        while True:
            server_sock, _ = server.accept()
            msg_conn  = MessageOps(server_sock)
            recv_file(msg_conn, self.root_path, self.chunk_size)
            msg_conn.close()


class Client:
    _default_server_port = Server._default_chunk_size
    _default_chunk_size = 1024*50

    def __init__(self, server_ip: str, server_port: int, passwd: bytes,
                 suggested_chunk_size: int) -> bool:
        self.server_ip = server_ip
        self.server_port = server_port if server_port > 0 else self._default_server_port
        self.passwd = passwd
        self.suggested_chunk_size = suggested_chunk_size if suggested_chunk_size > 0 else self._default_chunk_size

    def send(self, file_path: str, need_remove_file: bool = False) -> bool:
        client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_sock.connect((self.server_ip, self.server_port))
        msg_conn = MessageOps(client_sock)
        print("Info: Connected to server at %s:%d" % (self.server_ip, self.server_port))

        res = False
        if os.path.isfile(file_path):
            res = send_file(msg_conn, file_path, os.path.basename(file_path),
                            self.suggested_chunk_size, need_remove_file)
        elif os.path.isdir(file_path):
            res = send_files_in_folder(msg_conn, file_path, "./",
                                       self.suggested_chunk_size, need_remove_file)
        
        send_file_ending(msg_conn)
        msg_conn.close()
        return res


if __name__ == "__main__":
    import argparse, json

    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--server", action="store_true", help = "Run in server mode or client mode")
    parser.add_argument("-c", "--config", type = str, default = "config.json",
                        help = "Configuration file name, \"config.json\" by default.")
    parser.add_argument("-f", "--file", type = str, default = "", help = "Name of file or folder to send (required in client mode).")
    parser.add_argument("-r", "--remove_file", action="store_true", help = "Remove file after sending.")

    args = parser.parse_args()

    if not os.path.isfile(args.config):
        print("Error: Configuration file \"%s\" is not found." % args.config)
        exit()
    
    if not args.server:
        if args.file == "":
            print("Error: File/Folder to be sent is not specified.")
            exit()
        elif not os.path.exists(args.file):
            print("Error: File/Folder to be sent is not found:\n" \
                "       %s" % args.file)
            exit()

    with open(args.config, 'r') as config_file:
        config_params: dict[str, str | int] = json.load(config_file)
    
    server_ip   = config_params.get("server_ip", "")
    server_port = config_params.get("server_port", 0)
    passwd      = str(config_params.get("passwd", "")).encode()
    server_root_path = config_params.get("server_root_path", "")
    chunk_size  = config_params.get("chunk_size", 0)

    if args.server:
        server = Server(server_ip, server_port, passwd, server_root_path, chunk_size)
        server.run()
    
    else: # start client
        if not server_ip:
            print("Error: Server IP is not provided in %s." % args.config)
            exit()

        client = Client(server_ip, server_port, passwd, chunk_size)
        client.send(args.file, args.remove_file)
