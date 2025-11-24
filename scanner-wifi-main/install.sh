#!/bin/bash
# Installation script for Replivision Scanner WiFi Setup Service

set -e  # Exit on error

echo "========================================="
echo "Replivision Scanner WiFi Setup - Installation"
echo "========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "ERROR: Please run as root (sudo bash install.sh)"
    exit 1
fi

# Determine the actual user (not root)
ACTUAL_USER="${SUDO_USER:-$USER}"
if [ "$ACTUAL_USER" = "root" ]; then
    ACTUAL_USER="pi"  # Fallback to pi if can't determine
fi

USER_HOME=$(eval echo ~$ACTUAL_USER)

echo "Installing for user: $ACTUAL_USER"
echo "Home directory: $USER_HOME"
echo ""

echo "Step 1: Updating system packages..."
apt-get update

echo ""
echo "Step 2: Installing dependencies..."
apt-get install -y \
    network-manager \
    python3 \
    python3-pip \
    python3-flask

echo ""
echo "Step 3: Installing Python packages..."
pip3 install flask --break-system-packages 2>/dev/null || pip3 install flask

echo ""
echo "Step 4: Configuring NetworkManager..."

# Stop and disable conflicting services
systemctl stop dhcpcd 2>/dev/null || true
systemctl disable dhcpcd 2>/dev/null || true

# Enable and start NetworkManager
systemctl enable NetworkManager
systemctl start NetworkManager

echo ""
echo "Step 5: Installing WiFi setup service..."

# Create directory
mkdir -p "$USER_HOME/shad-setup"

# Copy service file to systemd directory
cp wifi-setup.service /etc/systemd/system/

# Copy Python script to user's home
cp wifi_setup.py "$USER_HOME/shad-setup/"
chmod +x "$USER_HOME/shad-setup/wifi_setup.py"

# Set proper ownership
chown -R $ACTUAL_USER:$ACTUAL_USER "$USER_HOME/shad-setup"

# Update service file to use correct path
sed -i "s|/home/pi/shad-setup|$USER_HOME/shad-setup|g" /etc/systemd/system/wifi-setup.service
sed -i "s|WorkingDirectory=/home/pi|WorkingDirectory=$USER_HOME/shad-setup|g" /etc/systemd/system/wifi-setup.service

echo ""
echo "Step 6: Enabling service..."
systemctl daemon-reload
systemctl enable wifi-setup.service

echo ""
echo "========================================="
echo "Installation Complete!"
echo "========================================="
echo ""
echo "The WiFi setup service will start automatically on next boot."
echo ""
echo "WiFi Credentials:"
echo "  SSID: Replivision-Scanner"
echo "  Password: repli2025"
echo ""
echo "To start it now, run:"
echo "  sudo systemctl start wifi-setup.service"
echo ""
echo "To view logs:"
echo "  sudo journalctl -u wifi-setup.service -f"
echo ""
echo "To check status:"
echo "  sudo systemctl status wifi-setup.service"
echo ""

read -p "Would you like to reboot now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Rebooting in 3 seconds..."
    sleep 3
    reboot
else
    echo "Please reboot manually to start the service."
fi
