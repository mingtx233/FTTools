import socket

from Utils.DataPacketOps import DataPacketOps

server_ip = "192.168.1.100"
server_port = 10023

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind((server_ip, server_port))
server_socket.listen(60)

server, _ = server_socket.accept()

server_conn = DataPacketOps(server, 100)

server.sendall(b"efojeoj")
server_conn.send(b"abcdefghijklmn")

server.sendall(b"xxnxnxnx")
server_conn.send(b"12345678910111213141516")
server.sendall(b"efefejejflejlfe")

data = server_conn.recv()
print(data)

data = server_conn.recv()
print(data)

server_socket.close()
