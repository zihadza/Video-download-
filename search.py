from flask import Flask, request, jsonify, render_template_string, send_from_directory
import subprocess, os, json, threading, re, time

app = Flask(__name__)

PORT = 1111
SAVE_DIR = "/storage/emulated/0/Zihad/zihaddhorm"
HISTORY_FILE = os.path.join(SAVE_DIR, "history.json")

os.makedirs(SAVE_DIR, exist_ok=True)

if not os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "w") as f:
        json.dump([], f)

progress = {
    "percent": "0%",
    "speed": "",
    "eta": "",
    "size": "",
    "file": "",
    "status": "idle"
}

HTML = """
<!DOCTYPE html>
<html lang="bn">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Zihad Premium Downloader</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@400;500;600;700&display=swap');

:root {
  --primary: #ff2d55;
  --secondary: #00f5d4;
  --bg: #070b14;
  --card: rgba(255, 255, 255, 0.055);
  --text: #f1f5f9;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
  font-family: 'Hind Siliguri', sans-serif;
  -webkit-tap-highlight-color: transparent;
}

body {
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  padding: 18px 16px 40px;
  background-image: 
    radial-gradient(circle at 10% 20%, rgba(255, 45, 85, 0.08), transparent 40%),
    radial-gradient(circle at 90% 80%, rgba(0, 245, 212, 0.06), transparent 40%);
}

.container {
  max-width: 460px;
  margin: 0 auto;
}

.header {
  text-align: center;
  margin-bottom: 22px;
  animation: fadeIn 0.7s ease;
}

.header h1 {
  font-size: 1.8rem;
  font-weight: 700;
  background: linear-gradient(90deg, #ff2d55, #00f5d4);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.header p {
  font-size: 0.82rem;
  color: #94a3b8;
  margin-top: 5px;
}

.card {
  background: var(--card);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-radius: 20px;
  padding: 18px;
  margin-bottom: 16px;
  border: 1px solid rgba(255, 255, 255, 0.07);
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.35);
  animation: slideUp 0.5s ease;
}

.tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
  background: rgba(255,255,255,0.04);
  padding: 5px;
  border-radius: 14px;
}

.tab {
  flex: 1;
  text-align: center;
  padding: 11px;
  border-radius: 11px;
  font-size: 14px;
  font-weight: 500;
  color: #94a3b8;
  transition: 0.3s;
}

.tab.active {
  background: linear-gradient(135deg, #ff2d55, #ff6b6b);
  color: white;
  font-weight: 600;
  box-shadow: 0 4px 15px rgba(255, 45, 85, 0.3);
}

input, select {
  width: 100%;
  padding: 14px 16px;
  border: none;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.07);
  color: white;
  font-size: 15px;
  margin-top: 10px;
  outline: none;
}

input:focus, select:focus {
  background: rgba(255, 255, 255, 0.11);
  box-shadow: 0 0 0 2px rgba(0, 245, 212, 0.25);
}

input::placeholder {
  color: #64748b;
}

button {
  width: 100%;
  padding: 15px;
  border: none;
  border-radius: 14px;
  background: linear-gradient(135deg, #ff2d55, #ff4d6d);
  color: white;
  font-size: 15.5px;
  font-weight: 600;
  margin-top: 12px;
  cursor: pointer;
  transition: 0.25s;
  box-shadow: 0 6px 20px rgba(255, 45, 85, 0.25);
}

button:active {
  transform: scale(0.97);
}

.btn-blue {
  background: linear-gradient(135deg, #3b82f6, #06b6d4);
  box-shadow: 0 6px 20px rgba(59, 130, 246, 0.25);
}

.progress-bg {
  height: 9px;
  background: rgba(255,255,255,0.08);
  border-radius: 20px;
  overflow: hidden;
  margin-top: 6px;
}

.progress-bar {
  height: 100%;
  width: 0%;
  background: linear-gradient(90deg, #00f5d4, #00bbf9);
  border-radius: 20px;
  transition: width 0.4s ease;
}

.status {
  font-size: 12.5px;
  color: #94a3b8;
  margin-top: 10px;
  line-height: 1.55;
}

.result-item {
  display: flex;
  gap: 13px;
  background: rgba(255,255,255,0.04);
  border-radius: 16px;
  padding: 12px;
  margin-top: 12px;
  animation: fadeIn 0.4s ease;
  border: 1px solid rgba(255,255,255,0.04);
}

.result-item img {
  width: 95px;
  height: 64px;
  object-fit: cover;
  border-radius: 11px;
  background: #1e293b;
}

.result-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.result-info h4 {
  font-size: 13.8px;
  font-weight: 600;
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin-bottom: 4px;
}

.result-info p {
  font-size: 11.5px;
  color: #94a3b8;
}

.action-row {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.action-row button {
  padding: 8px 0;
  font-size: 12.5px;
  margin-top: 0;
  flex: 1;
  border-radius: 10px;
}

.bottom-actions {
  display: flex;
  gap: 10px;
}

.bottom-actions button {
  margin-top: 0;
}

.loading {
  text-align: center;
  padding: 30px 10px;
  color: #94a3b8;
  font-size: 14px;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(25px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
</head>
<body>
<div class="container">

  <div class="header">
    <h1>Zihad Downloader</h1>
    <p>YouTube + Bilibili Premium Search</p>
  </div>

  <div class="card">
    <div class="tabs">
      <div class="tab active" onclick="switchTab('search')">সার্চ</div>
      <div class="tab" onclick="switchTab('url')">লিংক পেস্ট</div>
    </div>

    <div id="searchSection">
      <select id="searchPlatform">
        <option value="youtube">YouTube সার্চ</option>
        <option value="bilibili">Bilibili সার্চ</option>
      </select>
      <input type="text" id="searchInput" placeholder="কীওয়ার্ড লিখুন...">
      <button onclick="doSearch()">সার্চ করুন</button>
    </div>

    <div id="urlSection" style="display:none;">
      <input type="text" id="urlInput" placeholder="যেকোনো প্ল্যাটফর্মের লিংক পেস্ট করুন">
      <button onclick="loadInfo()">ইনফো দেখুন</button>
    </div>

    <select id="quality">
      <option value="360">360p</option>
      <option value="480">480p</option>
      <option value="720" selected>720p</option>
      <option value="1080">1080p</option>
      <option value="best">Best Quality</option>
    </select>

    <select id="type">
      <option value="video">ভিডিও</option>
      <option value="audio">শুধু অডিও (MP3)</option>
    </select>
  </div>

  <div class="card">
    <div class="progress-bg">
      <div class="progress-bar" id="progressBar"></div>
    </div>
    <div class="status" id="statusText">রেডি...</div>
  </div>

  <div id="results"></div>

  <div class="card bottom-actions">
    <button class="btn-blue" onclick="showHistory()">হিস্টরি</button>
    <button class="btn-blue" onclick="showFiles()">ফাইলসমূহ</button>
  </div>

</div>

<script>
function switchTab(tab) {
  const tabs = document.querySelectorAll('.tab');
  tabs.forEach(t => t.classList.remove('active'));
  
  if (tab === 'search') {
    tabs[0].classList.add('active');
    document.getElementById('searchSection').style.display = 'block';
    document.getElementById('urlSection').style.display = 'none';
  } else {
    tabs[1].classList.add('active');
    document.getElementById('searchSection').style.display = 'none';
    document.getElementById('urlSection').style.display = 'block';
  }
}

function doSearch() {
  const query = document.getElementById('searchInput').value.trim();
  const platform = document.getElementById('searchPlatform').value;
  if (!query) return alert('কিছু লিখুন');

  document.getElementById('results').innerHTML = '<div class="loading">সার্চ করা হচ্ছে...</div>';

  fetch('/search', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({query, platform})
  })
  .then(res => res.json())
  .then(data => {
    if (data.error) {
      document.getElementById('results').innerHTML = `<div class="card">${data.error}</div>`;
      return;
    }

    let html = '';
    data.results.forEach(item => {
      html += `
        <div class="result-item">
          <img src="${item.thumbnail}" onerror="this.src='https://via.placeholder.com/95x64/1e293b/94a3b8?text=No+Img'">
          <div class="result-info">
            <h4>${item.title}</h4>
            <p>${item.duration || ''} • ${item.uploader || ''}</p>
            <div class="action-row">
              <button onclick="startDownload('${item.url}')">ডাউনলোড</button>
              <button class="btn-blue" onclick="playDirect('${item.url}')">প্লে</button>
            </div>
          </div>
        </div>`;
    });

    document.getElementById('results').innerHTML = html || '<div class="card">কোনো রেজাল্ট পাওয়া যায়নি</div>';
  })
  .catch(() => {
    document.getElementById('results').innerHTML = '<div class="card">সার্চ ব্যর্থ হয়েছে</div>';
  });
}

function loadInfo() {
  const url = document.getElementById('urlInput').value.trim();
  if (!url) return alert('লিংক দিন');

  document.getElementById('results').innerHTML = '<div class="loading">ইনফো আনা হচ্ছে...</div>';

  fetch('/info', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({url})
  })
  .then(res => res.json())
  .then(data => {
    if (data.error) {
      document.getElementById('results').innerHTML = `<div class="card">${data.error}</div>`;
      return;
    }

    document.getElementById('results').innerHTML = `
      <div class="card">
        <img src="${data.thumbnail}" style="width:100%; border-radius:14px; margin-bottom:12px;">
        <h3 style="font-size:16px; margin-bottom:6px;">${data.title}</h3>
        <p style="color:#94a3b8; font-size:13px; margin-bottom:14px;">${data.channel || ''}</p>
        <div class="action-row">
          <button onclick="startDownload('${url}')">ডাউনলোড</button>
          <button class="btn-blue" onclick="playDirect('${url}')">প্লে</button>
        </div>
      </div>`;
  });
}

function startDownload(url) {
  const quality = document.getElementById('quality').value;
  const type = document.getElementById('type').value;

  fetch('/download', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({url, quality, type})
  });

  monitorProgress();
}

function playDirect(url) {
  document.getElementById('results').innerHTML = `
    <div class="card">
      <p style="color:#94a3b8; margin-bottom:12px;">ডাইরেক্ট প্লে সীমিত। ডাউনলোড করে প্লে করুন।</p>
      <button onclick="startDownload('${url}')">ডাউনলোড করুন</button>
    </div>`;
}

function monitorProgress() {
  const interval = setInterval(() => {
    fetch('/progress')
      .then(res => res.json())
      .then(data => {
        document.getElementById('progressBar').style.width = data.percent;
        document.getElementById('statusText').innerHTML = `
          স্ট্যাটাস: <b>${data.status}</b><br>
          প্রগ্রেস: ${data.percent}<br>
          সাইজ: ${data.size || '-'} | স্পিড: ${data.speed || '-'}<br>
          ETA: ${data.eta || '-'}
        `;

        if (data.status === 'finished' && data.file) {
          clearInterval(interval);
          document.getElementById('results').innerHTML = `
            <div class="card">
              <video controls style="width:100%; border-radius:14px;" src="/file/${data.file}"></video>
              <br><br>
              <a href="/file/${data.file}" download style="color:#00f5d4; font-weight:600;">
                ফাইল ডাউনলোড করুন
              </a>
            </div>`;
        }
      });
  }, 900);
}

function showHistory() {
  fetch('/history')
    .then(res => res.json())
    .then(data => {
      let html = '<div class="card"><h3 style="margin-bottom:12px;">ডাউনলোড হিস্টরি</h3>';
      if (data.length === 0) {
        html += '<p style="color:#94a3b8;">এখনো কিছু ডাউনলোড হয়নি</p>';
      } else {
        data.reverse().forEach(item => {
          html += `
            <div style="padding:11px 0; border-bottom:1px solid rgba(255,255,255,0.05); font-size:13.5px;">
              ${item.title}<br>
              <small style="color:#64748b;">${item.time}</small>
            </div>`;
        });
      }
      html += '</div>';
      document.getElementById('results').innerHTML = html;
    });
}

function showFiles() {
  fetch('/files')
    .then(res => res.json())
    .then(data => {
      let html = '<div class="card"><h3 style="margin-bottom:12px;">সেভ করা ফাইল</h3>';
      const files = data.filter(f => f !== 'history.json');
      if (files.length === 0) {
        html += '<p style="color:#94a3b8;">কোনো ফাইল নেই</p>';
      } else {
        files.forEach(f => {
          html += `
            <div style="padding:11px 0; border-bottom:1px solid rgba(255,255,255,0.05);">
              <a href="/file/\( {f}" download style="color:#00f5d4; font-size:14px;"> \){f}</a>
            </div>`;
        });
      }
      html += '</div>';
      document.getElementById('results').innerHTML = html;
    });
}
</script>
</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(HTML)

@app.route("/search", methods=["POST"])
def search():
    query = request.json.get("query", "").strip()
    platform = request.json.get("platform", "youtube")

    if not query:
        return jsonify({"error": "কিছু লিখুন"})

    try:
        if platform == "bilibili":
            search_prefix = f"bilisearch12:{query}"
        else:
            search_prefix = f"ytsearch12:{query}"

        cmd = [
            "yt-dlp",
            search_prefix,
            "--dump-json",
            "--no-download",
            "--flat-playlist"
        ]
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=40).decode(errors="ignore")

        results = []
        for line in output.strip().splitlines():
            try:
                data = json.loads(line)
                results.append({
                    "title": data.get("title", "Unknown"),
                    "url": data.get("url") or data.get("webpage_url") or data.get("original_url", ""),
                    "thumbnail": data.get("thumbnail") or (data.get("thumbnails") or [{}])[-1].get("url", ""),
                    "duration": data.get("duration_string") or "",
                    "uploader": data.get("uploader") or data.get("channel") or data.get("uploader_id", "")
                })
            except:
                continue

        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": f"সার্চ ব্যর্থ হয়েছে। Bilibili সার্চ অনেক সময় অঞ্চলভেদে সমস্যা করে।"})

@app.route("/info", methods=["POST"])
def info():
    url = request.json.get("url", "").strip()
    try:
        data = subprocess.check_output(
            ["yt-dlp", "-j", "--no-download", url],
            stderr=subprocess.STDOUT,
            timeout=25
        ).decode(errors="ignore")
        j = json.loads(data)
        return jsonify({
            "title": j.get("title", "Unknown"),
            "channel": j.get("channel") or j.get("uploader", ""),
            "thumbnail": j.get("thumbnail", "")
        })
    except:
        return jsonify({"error": "ইনফো আনতে ব্যর্থ। লিংক সঠিক কিনা চেক করুন।"})

def run_download(url, quality, typ):
    global progress
    progress.update({
        "percent": "0%",
        "speed": "",
        "eta": "",
        "size": "",
        "file": "",
        "status": "downloading"
    })

    try:
        if typ == "audio":
            cmd = [
                "yt-dlp",
                "-f", "bestaudio",
                "--extract-audio",
                "--audio-format", "mp3",
                "-o", os.path.join(SAVE_DIR, "%(title).85s.%(ext)s"),
                url
            ]
        else:
            fmt = "bestvideo+bestaudio/best" if quality == "best" else f"bestvideo[height<={quality}]+bestaudio/best"
            cmd = [
                "yt-dlp",
                "-f", fmt,
                "--merge-output-format", "mp4",
                "-o", os.path.join(SAVE_DIR, "%(title).85s.%(ext)s"),
                url
            ]

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

        for line in process.stdout:
            if "[download]" in line:
                percent = re.search(r'(\d+\.?\d*%)', line)
                size = re.search(r'of\s+(\S+)', line)
                speed = re.search(r'at\s+(\S+)', line)
                eta = re.search(r'ETA\s+(\S+)', line)

                if percent: progress["percent"] = percent.group(1)
                if size: progress["size"] = size.group(1)
                if speed: progress["speed"] = speed.group(1)
                if eta: progress["eta"] = eta.group(1)

            if "Destination:" in line:
                progress["file"] = os.path.basename(line.split("Destination:")[-1].strip())

        process.wait()
        progress["status"] = "finished"
        progress["percent"] = "100%"

        with open(HISTORY_FILE) as f:
            history = json.load(f)
        history.append({
            "title": url,
            "time": time.strftime("%Y-%m-%d %H:%M")
        })
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f)

    except Exception as e:
        progress["status"] = "error"

@app.route("/download", methods=["POST"])
def download():
    data = request.json
    threading.Thread(target=run_download, args=(data["url"], data["quality"], data["type"]), daemon=True).start()
    return jsonify({"status": "started"})

@app.route("/progress")
def get_progress():
    return jsonify(progress)

@app.route("/history")
def get_history():
    with open(HISTORY_FILE) as f:
        return jsonify(json.load(f))

@app.route("/files")
def get_files():
    return jsonify(os.listdir(SAVE_DIR))

@app.route("/file/<path:name>")
def serve_file(name):
    return send_from_directory(SAVE_DIR, name)

if __name__ == "__main__":
    print(f"Server running → http://0.0.0.0:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
