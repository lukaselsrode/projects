import socket
import threading

DEF_BUFFSIZE = 1024
DEF_PORT = 9445
DEF_IP_ADDRESS = 'localhost'


class TCP_Server:

    def __init__(self,ip_address=DEF_IP_ADDRESS,port_num=DEF_PORT,queue_length=1):
        # create server and bind it to the correct port and ip_adress
        self.bind_ip, self.bind_port = ip_address, port_num
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind((self.bind_ip, self.bind_port))
        # Initiate a queue of 5 --> Can hold a backlog queue of 5
        self.server.listen(queue_length)
        print(f"Server Listening on {self.bind_ip}:{self.bind_port}")


    def handle_client(self,client):
        """
        Client Handling Thread which Receives messages from 
        the client and then sends them back

            Inputs:
                ('Socket.socket' Class) : client - The TCP client which to handle 
            Outputs:
                (None)
        """
        data = client.recv(DEF_BUFFSIZE)
        print("Received Data: {}".format(data))
        return data


    def run_server(self):
        """
        """
        while True:
            print("Waiting for connection")
            client, addr = self.server.accept()
            try:
                print("Accepted connection from client IP: {}".format(addr))                
                while True:
                    data = self.handle_client(client)   
                    if not data:
                        break
            finally:
                client.close()


if __name__ == "__main__":
    print("TCP_SERVER.py - CREATES A SERVER TO PASS MESSAGES TO")
    Server = TCP_Server()
    Server.run_server()
