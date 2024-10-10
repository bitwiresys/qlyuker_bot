#!/bin/bash

# Activate the virtual environment
source venv/bin/activate

while true; do
    clear
    echo "Choose an action:"
    echo "1. Registration"
    echo "2. Launch"
    echo "3. Exit"
    read -p "Enter the number (1-3): " choice

    case $choice in
        1)
			cls
            python reg.py
            read -n 1 -s -r -p "Press any key to continue..."
            ;;
        2)
			cls
            python main.py
            read -n 1 -s -r -p "Press any key to continue..."
            ;;
        3)
            exit
            ;;
        *)
            echo "Invalid input. Please try again."
            read -n 1 -s -r -p "Press any key to continue..."
            ;;
    esac
done