import socket as sk
from localconn import info

#DEFAULT_TIMEOUT=20
DEFAULT_MAX_PORT_ENUM=20_000

def grab_local_ip():
    return  str(info(show=False)['broadcast'])

def attempt_connection(ip_addr,port):
    s = sk.socket(sk.AF_INET, sk.SOCK_STREAM)
    #s.settimeout(DEFAULT_TIMEOUT)
    r = s.connect_ex((ip_addr+'/24', port))
    if r==0:
        print(f"Port: {port} is Open on {ip_addr}")
    s.close()
        

if __name__ == "__main__":
    ip_addr = grab_local_ip()
    print(ip_addr)
    for port in range(1,DEFAULT_MAX_PORT_ENUM):
        try: attempt_connection(ip_addr, port)
        except: continue

