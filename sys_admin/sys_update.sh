#!/bin/bash
echo 'os.info' && cat /etc/os*;
sudo apt dist-upgrade && sudo apt update && sudo apt full-upgrade -y;
sudo apt-get dist-upgrade && sudo apt-get update && sudo apt-get upgrade;
sudo apt-get clean && sudo apt-get autoremove;
update-grub
