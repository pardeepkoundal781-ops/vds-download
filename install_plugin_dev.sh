#!/bin/bash

# Stop script on first error
set -e

# Usage: ./install_plugin_dev.sh [--add-conf]

ADD_CONF=false
for arg in "$@"; do
    if [ "$arg" = "--add-conf" ]; then
        ADD_CONF=true
    elif [ -n "$arg" ]; then
        echo "ERROR: Unrecognized argument: $arg" >&2
        exit 1
    fi
done

# Pre-flight Check: Ensure we are in the right directory
if [ ! -d "plugin" ] || [ ! -d "server" ]; then
    echo "ERROR: 'plugin' or 'server' directory not found."
    echo "Please run this script from the root of the project."
    exit 1
fi

# Pre-flight Check: Ensure Node/NPM is installed
if ! command -v npm &> /dev/null; then
    echo "ERROR: npm could not be found. Please install Node.js."
    exit 1
fi

# 1. Install Plugin
PLUGIN_DIR=~/yt-dlp-plugins/bgutil-ytdlp-pot-provider/
echo "Creating plugin directory: $PLUGIN_DIR"
mkdir -p "$PLUGIN_DIR"
echo "Copying plugin files..."
cp -r plugin/* "$PLUGIN_DIR"

# 2. Configure yt-dlp.conf
if [ "$ADD_CONF" = true ]; then
    YTDLP_CONF=~/yt-dlp.conf
    if [ -e "$YTDLP_CONF" ]; then
        echo "WARN: yt-dlp.conf already exists at $YTDLP_CONF."
        echo "      Skipping automatic configuration to prevent overwriting."
    else
        echo "Generating yt-dlp configuration at $YTDLP_CONF..."
        # Using absolute path for safety
        SCRIPT_PATH=$(realpath server/build/generate_once.js)
        
        {
            echo "--extractor-args \"youtubepot-bgutilscript:script_path=$SCRIPT_PATH\""
            echo '--extractor-args "youtube:player-client=mweb"'
        } > "$YTDLP_CONF"
        echo "Configuration created."
    fi
else
    echo "INFO: Skipping yt-dlp.conf creation. Run with --add-conf to enable."
fi

# 3. Build Server
echo "Entering server directory..."
cd server/

echo "Installing server dependencies (npm ci)..."
npm ci

echo "Compiling TypeScript files..."
npx tsc

echo "---------------------------------------------------"
echo "DONE! Setup complete."
echo "To start the token server, run:"
echo "node $(pwd)/build/main.js"
echo "---------------------------------------------------"
