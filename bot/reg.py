import os
import configparser
from pyrogram import Client

# Define the name of the folder to store session files
SESSION_FOLDER = "sessions"

# Create the session folder if it doesn't exist
if not os.path.exists(SESSION_FOLDER):
    os.makedirs(SESSION_FOLDER)


# Function to read API credentials from a config file
def read_api_credentials(config_file):
    config = configparser.ConfigParser()
    config.read(config_file)

    # Assuming API_ID and API_HASH are stored under the section [DEFAULT]
    api_id = config.get('telegram', 'api_id')
    api_hash = config.get('telegram', 'api_hash')

    return api_id, api_hash

# Read API ID and API Hash from the config file
try:
    api_id, api_hash = read_api_credentials('.conf')
    print("API ID and API Hash loaded successfully.")
except Exception as e:
    print(f"Error reading API credentials: {e}")
    exit(1)

# Loop to create multiple session files
while True:
    # Input for the session name
    session_name = input("Enter the session name: ")

    # Construct the session file path
    session_file_path = os.path.join(SESSION_FOLDER, session_name)

    # Create a new Pyrogram Client instance with the session name
    client = Client(session_file_path, api_id=api_id, api_hash=api_hash)

    # Start the client to create the session file
    try:
        with client:
            print(f"Session file created: {session_file_path}")
    except Exception as e:
        print(f"Failed to create session: {e}")
        continue

    # Ask if the user wants to create another session
    another = input("Do you want to create another session? (y/N): ").strip().lower()
    if another != 'y':
        break

print("Session creation process completed.")