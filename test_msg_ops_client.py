import threading, socket

from Utils.DataPacketOps import DataPacketOps
from Utils.MessageOps import MessageOps

server_ip     = "192.168.1.100"
server_port   = 10023

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect((server_ip, server_port))

client_msg_ops = MessageOps(client)
with open(".\\send\\aaa.pdf", "rb") as send_file:
    file_data = send_file.read()
    
    client_msg_ops.send(file_data)
    client.close()
