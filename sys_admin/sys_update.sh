#!/bin/bash
echo 'os.info' && cat /etc/os*;
yes | sudo apt dist-upgrade && sudo apt update && sudo apt full-upgrade -y;
yes | sudo apt-get dist-upgrade && sudo apt-get update && sudo apt-get upgrade;
yes | sudo apt-get clean && sudo apt-get autoremove;
update-grub
