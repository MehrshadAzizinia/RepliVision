#!/bin/bash
# Quick test to see if the network is visible

echo "=== WiFi Diagnostic Test ==="
echo ""

echo "1. Checking WiFi radio status..."
nmcli radio wifi
echo ""

echo "2. Checking device status..."
nmcli device status
echo ""

echo "3. Turning WiFi off and on..."
nmcli radio wifi off
sleep 2
nmcli radio wifi on
sleep 5
echo ""

echo "4. Scanning for networks..."
nmcli device wifi rescan
sleep 5
echo ""

echo "5. Available networks:"
nmcli device wifi list
echo ""

echo "6. Searching for 'Sony Xperia Z5'..."
nmcli device wifi list | grep -i "sony"
echo ""

echo "7. All SSIDs (raw):"
nmcli -t -f SSID device wifi list
echo ""

echo "=== Test Complete ==="
