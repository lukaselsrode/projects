import socket as sk
from localconn import info


def grab_local_ip():
    return  str(info()['inet'])

if __name__ == "__main__":
    ip_addr = grab_local_ip()
    print(ip_addr)
    for port in range(1, 20000):
        try:
            s = sk.socket(sk.AF_INET, sk.SOCK_STREAM)
            s.setdefaulttimeout(1)
            r = s.connect_ex((ip_addr, port))
            print(f"Port: {port} is Open on {ip_addr}")
            s.close()
        except:
            continue


