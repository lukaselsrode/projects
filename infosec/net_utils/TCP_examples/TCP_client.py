# Simple TCP Client Protocol with big assumptions
import socket
import sys


DEF_BUFFSIZE = 1024
DEF_PORT = 9445
DEF_HOST = socket.gethostbyname(socket.gethostname())


client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

if __name__ == "__main__":

    inputs = sys.argv[1]
    print(inputs)

    if len(inputs) > 1:
        host_ip = str(inputs[0])
        msg = bytes(inputs[1], 'utf-8')

    else:
        host_ip = DEF_HOST
        msg = bytes(inputs, 'utf-8')

    client.send(msg)
    response = client.recv(DEF_BUFFSIZE)
    print(response)
