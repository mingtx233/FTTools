import threading
import socket

from DataPacketOps import DataPacketOps
from MessageOps import MessageOps

server_ip     = "127.0.0.1"
server_port   = 10023

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind((server_ip, server_port))
server_socket.listen(5)

def server_func(server_socket: socket.socket):
    server, _ = server_socket.accept()
    
    server_conn = DataPacketOps(server)
    server_msg_ops = MessageOps(server_conn)
    try:
        file_data = server_msg_ops.recv()
        if file_data is not None:
            with open(".\\send\\vps2.png", "wb") as recv_file:
                recv_file.write(file_data)
    except Exception as e:
        print("Recv Error: %s" % e)

    server.close()


thread = threading.Thread(target = server_func, args = (server_socket, ))
thread.start()

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect((server_ip, server_port))

client_conn    = DataPacketOps(client, 500)
client_msg_ops = MessageOps(client_conn)
with open(".\\send\\vps.png", "rb") as send_file:
    file_data = send_file.read()
    
    #try:
    client_msg_ops.send(file_data)
    client.close()
    #except Exception as e:
    #    print("Read Error: %s" % e)

thread.join()
