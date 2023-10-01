from subprocess import getoutput as get 

def info():
    inet,nmask,bcast = get("ifconfig -a -v | grep broadcast | cut -d ' ' -f10,13,16").split(' ')
    name = get("iwconfig  | grep wlan0 | cut -d ':' -f2-").split('\n')[-1]
    ap = get("iwconfig | grep Point | cut -d ':' -f4-").split('\n')[-1].strip(' ')
    d = {'connected network': name,
         'inet':inet,
         'net_mask':nmask,
         'broadcast':bcast,
         'access point':ap
            }
    print('\n')
    for k,v in d.items():
        print(k,':',v)


if __name__ == "__main__":
    info()

