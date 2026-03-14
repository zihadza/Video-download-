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

## 🛠 Installation & Setup

Copy and paste each block in terminal:

```bash
# 1️⃣ Update Termux / Linux
pkg update && pkg upgrade -y
pkg install python git -y

# 2️⃣ Install Python packages
pip install --upgrade pip
pip install flask
pip install yt-dlp

# 3️⃣ Optional: Install NodeJS
pkg install nodejs -y

# 4️⃣ Prepare folders
mkdir -p /storage/emulated/0/Zihad
cd /storage/emulated/0/Zihad

# 5️⃣ Remove old copy if exists
rm -rf Video-download-

# 6️⃣ Clone the GitHub repo
git clone https://github.com/zihadza/Video-download-.git
cd Video-download-

# 7️⃣ Run the server
python app.py

# 8️⃣ Open in browser
http://localhost:3030
