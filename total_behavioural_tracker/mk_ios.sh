#!/bin/bash
set -euo pipefail
PROJECT_NAME="tbt"
if [[ -z "${VIRTUAL_ENV}" ]]; then
    echo "Warning: Not running inside a virtual environment!"
fi

echo "Cleaning up old build directories for $PROJECT_NAME..."
sleep 3
rm -rf ./build ./dist ./${PROJECT_NAME}-ios

echo "Building toolchains inbuilt recipes..."
sleep 3
toolchain build python3 kivy pyyaml

echo "Installing Python packages..."
sleep 3
toolchain pip install matplotlib pandas seaborn

echo "Creating the $PROJECT_NAME project..."
sleep 3
toolchain create $PROJECT_NAME ./src/

echo "Script execution completed successfully."
sleep 3