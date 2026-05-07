#!/usr/bin/env bash
set -euo pipefail

get_os() {
    case "$(uname -s)" in
        Linux*)                      echo "Linux" ;;
        Darwin*)                     echo "macOS" ;;
        CYGWIN*|MINGW*|MSYS*)        echo "Windows" ;;
        *)                           echo "Unknown" ;;
    esac
}

get_linux_distro() {
    if command -v apt-get &>/dev/null; then echo "apt"
    elif command -v dnf &>/dev/null;     then echo "dnf"
    elif command -v yum &>/dev/null;     then echo "yum"
    elif command -v pacman &>/dev/null;  then echo "pacman"
    else                                      echo "unknown"
    fi
}

update_linux() {
    echo "[$(date '+%F %T')] Running Linux system updates..."
    cat /etc/os-release 2>/dev/null || true

    local pm
    pm=$(get_linux_distro)
    echo "Package manager: $pm"

    case $pm in
        apt)
            sudo apt-get update -y
            sudo apt-get full-upgrade -y
            sudo apt-get autoremove -y
            sudo apt-get clean
            ;;
        dnf)
            sudo dnf upgrade -y
            sudo dnf autoremove -y
            sudo dnf clean all
            ;;
        yum)
            sudo yum update -y
            sudo yum autoremove -y
            sudo yum clean all
            ;;
        pacman)
            sudo pacman -Syu --noconfirm
            sudo pacman -Sc --noconfirm
            ;;
        *)
            echo "No supported package manager found." >&2
            return 1
            ;;
    esac

    if command -v grub-update &>/dev/null || command -v update-grub &>/dev/null; then
        sudo update-grub 2>/dev/null || true
    fi

    echo "[$(date '+%F %T')] Linux updates completed."
}

update_macos() {
    echo "[$(date '+%F %T')] Running macOS system updates..."
    sw_vers

    if command -v brew &>/dev/null; then
        brew update
        brew upgrade
        brew autoremove
        brew cleanup
    else
        echo "Homebrew not found. Installing..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        echo "Restart the script after Homebrew installation."
        exit 1
    fi

    if command -v mas &>/dev/null; then
        echo "Updating Mac App Store apps..."
        mas upgrade
    fi

    echo "Checking for macOS system updates..."
    softwareupdate --install --all --agree-to-license

    echo "[$(date '+%F %T')] macOS updates completed."
}

update_windows() {
    echo "[$(date '+%F %T')] Running Windows system updates..."
    systeminfo | findstr /B /C:"OS Name" /C:"OS Version" /C:"System Type"

    if command -v winget &>/dev/null; then
        winget upgrade --all --accept-source-agreements --accept-package-agreements
    else
        echo "winget not found." >&2
        return 1
    fi

    echo "[$(date '+%F %T')] Windows updates completed."
}

OS=$(get_os)
echo "[$(date '+%F %T')] Detected OS: $OS"

case $OS in
    Linux)   update_linux ;;
    macOS)   update_macos ;;
    Windows) update_windows ;;
    *)
        echo "Unsupported operating system." >&2
        exit 1
        ;;
esac

echo "[$(date '+%F %T')] System update process completed."
