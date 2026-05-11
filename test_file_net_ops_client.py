from test_file_net_ops import send_file_client

server_ip     = "192.168.1.100"
server_port   = 10023

#send_file_client(server_ip, server_port, b"abcde", r".\send\vps.png")
send_file_client(server_ip, server_port, b"abcde", r".\send")

