# Function to detect the operating system
get_os() {
    case "$(uname -s)" in
        Linux*)     echo "Linux" ;;
        Darwin*)    echo "macOS" ;;
        CYGWIN*|MINGW*|MSYS*|MINGW*) echo "Windows" ;;
        *)          echo "Unknown" ;;
    esac
}

update_linux() {
    echo "Running Linux system updates..."
    echo "OS Information:"
    cat /etc/os*
    echo -e "\nUpdating package lists and upgrading packages..."
    yes | sudo apt update && \
    yes | sudo apt dist-upgrade -y && \
    yes | sudo apt full-upgrade -y && \
    yes | sudo apt-get dist-upgrade && \
    yes | sudo apt-get upgrade -y && \
    yes | sudo apt-get clean && \
    yes | sudo apt-get autoremove -y && \
    yes | sudo update-grub
    echo "Linux updates completed."
}


update_macos() {
    echo "Running macOS system updates..."
    echo "System Information:"
    sw_vers
    echo -e "\nUpdating Homebrew and packages..."
    if command -v brew &> /dev/null; then
        brew update
        brew upgrade
        brew cleanup
    else
        echo "Homebrew not found. Installing Homebrew first..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        echo "Please restart the script after Homebrew installation."
        exit 1
    fi
    
    echo -e "\nChecking for system updates..."
    softwareupdate -ia
    echo "macOS updates completed."
}


update_windows() {
    echo "Running Windows system updates..."
    echo "System Information:"
    systeminfo | findstr /B /C:"OS Name" /C:"OS Version" /C:"System Type"
    
    echo -e "\nChecking for Windows updates..."
    if command -v winget &> /dev/null; then
        echo "Updating packages via Winget..."
        winget upgrade --all
    else
        echo "Winget not found. Using Windows Update..."
        powershell -Command "Start-Process wt -Verb RunAs -ArgumentList 'powershell -Command \"& {Start-Process powershell -ArgumentList \"-NoProfile -ExecutionPolicy Bypass -Command `\"Install-Module -Name PSWindowsUpdate -Force -Confirm:\$false -SkipPublisherCheck; Import-Module PSWindowsUpdate; Install-WindowsUpdate -AcceptAll -AutoReboot`\"\" -Verb RunAs}'"
    fi
    echo "Windows updates completed."
}

OS=$(get_os)
echo "Detected OS: $OS"

case $OS in
    "Linux")
        update_linux
        ;;
    "macOS")
        update_macos
        ;;
    "Windows")
        update_windows
        ;;
    *)
        echo "Unsupported operating system."
        exit 1
        ;;
esac

echo "System update process completed."