from test_file_net_ops import recv_file_server

server_ip     = "192.168.1.100"
server_port   = 10023

recv_server = recv_file_server(server_ip, server_port, b"abcde", ".\\recv")

