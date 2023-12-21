#!/bin/bash

set -euo pipefail

if [[ -z "${VIRTUAL_ENV}" ]]; then
    echo "Warning: Not running inside a virtual environment!"
fi

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <android|ios>"
    exit 1
fi

case "$1" in
    android)
        cd src/ || { echo "Failed to change directory to src/"; exit 1; }
        rm -rf ~/.buildozer .buildozer/ ./bin/
        yes | buildozer -v android debug
        echo "APK files built at:"
        find . -name '*.apk'
        ;;
    ios)
        PROJECT_NAME=“TBT”
        rm -rf ./build ./dist ./${PROJECT_NAME}-ios
        toolchain build python3 kivy pyyaml
        toolchain pip install matplotlib pandas seaborn
        toolchain create $PROJECT_NAME ./src/
        open "${PROJECT_NAME}-ios/${PROJECT_NAME}.xcodeproj" || { echo "Failed to open Xcode project"; exit 1; }
        ;;
    *)
        echo "Invalid argument. Please use 'android' or 'ios'."
        exit 1
        ;;
esac
