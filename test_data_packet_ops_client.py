import socket

from Utils.DataPacketOps import DataPacketOps

server_ip = "192.168.1.100"
server_port = 10023

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect((server_ip, server_port))

client_conn = DataPacketOps(client, 100)

data = client_conn.recv()
print(data)

data = client_conn.recv()
print(data)

client.sendall(b"efojeoj")
client_conn.send(b"xxxxxxefef")

client.sendall(b"xxnxnxnx")
client_conn.send(b"56h6h77776j7")
client.sendall(b"efefejejflejlfe")

client.close()
