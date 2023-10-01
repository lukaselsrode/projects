from subprocess import getoutput as get
import socket as sk



def grab_local_ip():
    return get('python3 ip.py').split(' ')[0]


if __name__ == "__main__":
    ip_addr = grab_local_ip()
    for port in range(1, 20000):
        try:
            s = sk.socket(sk.AF_INET, sk.SOCK_STREAM)
            s.settimeout(1000)
            s.connect((ip_addr, port))
            print(f"Port: {port} is Open on {ip_addr}")
            s.close()
        except:
            continue


