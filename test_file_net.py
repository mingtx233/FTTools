import socket

from FileNetOps import recv_file_server, send_file_client

server_ip = socket.gethostbyname(socket.gethostname())
server_port = 10025

recv_server = recv_file_server(server_ip, server_port, b"abcde", ".\\recv")

#send_file_client(server_ip, server_port, b"abcde", r".\send\vps.png")
send_file_client(server_ip, server_port, b"abcde", r".\send")

recv_server.stop_after_last_file()
