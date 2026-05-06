import socket

from DataPacketOps import DataPacketOps

server_ip = "127.0.0.1"
server_port = 10023

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind((server_ip, server_port))
server_socket.listen(5)

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect((server_ip, server_port))

server, _ = server_socket.accept()

#
server_conn = DataPacketOps(server, 100)
client_conn = DataPacketOps(client, 100)

#client.close()
#server_socket.close()

server.sendall(b"efojeoj")
server_conn.send(b"abcdefghijklmn")

data = client_conn.recv()
print(data)

server.sendall(b"xxnxnxnx")
server_conn.send(b"12345678910111213141516")
server.sendall(b"efefejejflejlfe")

data = client_conn.recv()
print(data)

client.close()
server_socket.close()
