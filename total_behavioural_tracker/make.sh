#!/bin/bash

set -euo pipefail

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

check_virtual_env() {
    if [[ -z "${VIRTUAL_ENV}" ]]; then
        log "Warning: Not running inside a virtual environment!"
    fi
}

check_arguments() {
    if [ "$#" -ne 2 ]; then
        log "Usage: $0 <android|ios> <project_name>"
        exit 1
    fi
}

clean_directories() {
    local dirs_to_clean=("$@")
    for dir in "${dirs_to_clean[@]}"; do
        rm -rf "$dir"
    done
}

build_android() {
    local project_name=$1
    cd src/ || { log "Failed to change directory to src/"; exit 1; }
    clean_directories "~/.buildozer" ".buildozer/" "./bin/"
    yes | buildozer -v android debug
    log "APK files built at:"
    find . -name '*.apk'
}

build_ios() {
    local project_name=$1
    clean_directories "./build" "./dist" "./${project_name}-ios"
    toolchain build python3 kivy pyyaml
    toolchain pip install matplotlib pandas seaborn
    toolchain create "$project_name" ./src/
    toolchain update "$project_name-ios"
    cp src/config/app_logo.png "$project_name-ios"/icon.png
    open "${project_name}-ios/${project_name}.xcodeproj" || { log "Failed to open Xcode project"; exit 1; }
}

main() {
    check_virtual_env
    check_arguments "$@"

    local build_type=$1
    local project_name=$2
    
    case "$build_type" in
        android)
            build_android "$project_name"
            ;;
        ios)
            build_ios "$project_name"
            ;;
        *)
            log "Invalid argument. Please use 'android' or 'ios'."
            exit 1
            ;;
    esac
}

main "$@"
