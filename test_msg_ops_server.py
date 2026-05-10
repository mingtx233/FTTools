import socket

from Utils.MessageOps import MessageOps

server_ip     = "192.168.1.100"
server_port   = 10023

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind((server_ip, server_port))
server_socket.listen(60)

server, _ = server_socket.accept()

server_msg_ops = MessageOps(server)

try:
    file_data = server_msg_ops.recv()
    if file_data is not None:
        with open(".\\send\\aaa2.pdf", "wb") as recv_file:
            recv_file.write(file_data)
    
except Exception as e:
    print("Recv Error: %s" % e)

server.close()
