# Video-download-

YouTube Video Downloader Project

---

## 🎯 Overview

Download YouTube videos in multiple resolutions with a simple web interface.

---

## ⚡ Requirements

- Python 3.13+
- pip
- Flask
- yt-dlp
- Optional: NodeJS (for full YouTube extraction support)

---

# Video-download Setup Guide

---

## 🛠 Step 1️⃣: Update & Install Packages

```bash
# Update Termux / Linux
pkg update && pkg upgrade -y

# Install Python & Git
pkg install python git -y

# Optional: NodeJS for full YouTube extraction support
pkg install nodejs -y

# Upgrade pip
pip install --upgrade pip

# Install required Python packages
pip install flask
pip install yt-dlp
```

🛠 Step 2️⃣: Clone Project
Bash
Copy code
# Prepare Zihad folder
```bash
mkdir -p /storage/emulated/0/Zihad
cd /storage/emulated/0/Zihad

# Remove old copy if exists
rm -rf Video-download-

# Clone GitHub repo
git clone https://github.com/zihadza/Video-download-.git
cd Video-download-
```
🛠 Step 3️⃣: Run Python Server
Bash
Copy code
# Run the Flask app
```bash
python app.py
```
⚠️ Make sure port 3030 is free.
Optional: NodeJS recommended for better YouTube extraction.

🛠 Step 4️⃣: Open in Browser
Plain text
Copy code
```bash
http://localhost:3030
