from flask import Flask, request, jsonify, render_template_string, send_from_directory
import os
import json
import threading
import re
from datetime import datetime
import yt_dlp

app = Flask(__name__)

# ============================================================
# CONFIG - FIXED
# ============================================================
PORT = 3030
SAVE_DIR = "/app/downloads"
HISTORY_FILE = os.path.join(SAVE_DIR, "history.json")

os.makedirs(SAVE_DIR, exist_ok=True)
if not os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump([], f, ensure_ascii=False, indent=2)

# ============================================================
# GLOBAL DOWNLOAD STATE
# ============================================================
progress = {
    "percent": "0%", "speed": "", "eta": "", "size": "",
    "downloaded": "", "file": "", "title": "", "status": "idle",
    "error": "", "type": "", "quality": "", "started": "", "finished": ""
}
progress_lock = threading.Lock()

def update_progress(**kwargs):
    global progress
    with progress_lock:
        for key, value in kwargs.items():
            if key in progress:
                progress[key] = value

def load_history():
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list): return data
            return []
    except Exception: return []

def save_history(history):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history[-100:], f, ensure_ascii=False, indent=2)
        return True
    except Exception: return False

def my_hook(d):
    if d['status'] == 'downloading':
        p_str = d.get('_percent_str', '0%').replace('%','').strip()
        try:
            p_float = float(p_str)
        except:
            p_float = 0
        update_progress(
            percent=f"{p_float}%",
            speed=d.get('_speed_str',''),
            eta=d.get('_eta_str',''),
            size=d.get('_total_bytes_str','') or d.get('_total_bytes_estimate_str',''),
            downloaded=d.get('_downloaded_bytes_str',''),
            status="downloading"
        )
    elif d['status'] == 'finished':
        update_progress(file=os.path.basename(d.get('filename','')))

# ============================================================
# HTML - YOUR PREMIUM DESIGN (SAME)
# ============================================================
HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<meta name="theme-color" content="#080f1e">
<title>Zihad Downloader • Premium</title>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/npm/remixicon@4.2.0/fonts/remixicon.css" rel="stylesheet">
<style>
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
:root{
  --bg:#060d1a;
  --card:rgba(255,255,255,0.06);
  --card-2:rgba(255,255,255,0.04);
  --border:rgba(255,255,255,0.08);
  --text:#f8fafc; --muted:#8fa3b8;
  --accent:#00d2ff; --accent2:#7c3aed; --success:#22c55e;
}
html,body{margin:0;padding:0;width:100%;min-height:100%}
body{
    background:#060d1a;
    background-image:
      radial-gradient(600px at 0% 0%, rgba(0,210,255,.18), transparent 60%),
      radial-gradient(600px at 100% 0%, rgba(124,58,237,.20), transparent 60%),
      radial-gradient(800px at 50% 100%, rgba(0,210,255,.08), transparent 70%);
    color:var(--text);
    font-family:"Outfit",-apple-system,BlinkMacSystemFont,sans-serif;
    overflow-x:hidden; padding-bottom:110px;
}
.bg-orb{position:fixed;width:300px;height:300px;border-radius:50%;filter:blur(80px);opacity:.35;pointer-events:none;z-index:-1;animation:floatOrb 8s ease-in-out infinite}
.orb-one{background:linear-gradient(135deg,#00d2ff,#3a7bd5);top:-80px;left:-80px}
.orb-two{background:linear-gradient(135deg,#7c3aed,#ff6ec7);bottom:10%;right:-80px;animation-delay:2s}
@keyframes floatOrb{0%,100%{transform:translateY(0) scale(1)}50%{transform:translateY(-25px) scale(1.05)}}
.app-header{
    position:sticky;top:0;z-index:100;
    padding:14px 16px;
    background:rgba(6,13,26,0.7);
    backdrop-filter:blur(24px) saturate(180%); -webkit-backdrop-filter:blur(24px) saturate(180%);
    border-bottom:1px solid var(--border);
}
.header-row{display:flex;align-items:center;justify-content:space-between;max-width:600px;margin:0 auto;width:100%}
.brand{display:flex;align-items:center;gap:12px}
.brand-icon{
    width:44px;height:44px;border-radius:13px;
    display:flex;align-items:center;justify-content:center;
    background:linear-gradient(135deg,#00c6ff,#0072ff 55%,#7c3aed);
    box-shadow:0 8px 20px rgba(0,132,255,.35), inset 0 1px 0 rgba(255,255,255,.3);
    font-size:20px;font-weight:800;color:#fff;
}
.brand-title{font-size:17px;font-weight:800;letter-spacing:-.02em}
.brand-sub{font-size:11px;color:var(--muted);font-weight:500;margin-top:1px}
.icon-btn{
    width:42px;height:42px;border-radius:13px;border:1px solid var(--border);
    background:var(--card);color:#fff;display:flex;align-items:center;justify-content:center;
    font-size:18px;cursor:pointer;transition:.3s cubic-bezier(.16,1,.3,1);
}
.icon-btn:active{transform:scale(.92)}
.container{width:100%;max-width:600px;margin:0 auto;padding:18px 14px 10px}
.hero{
    padding:22px 20px;border-radius:28px;position:relative;overflow:hidden;
    background:linear-gradient(135deg, rgba(255,255,255,.08), rgba(255,255,255,.02));
    border:1px solid var(--border);
    backdrop-filter:blur(20px); -webkit-backdrop-filter:blur(20px);
    box-shadow:0 20px 50px rgba(0,0,0,.3);
}
.hero::before{
    content:"";position:absolute;inset:0;
    background:radial-gradient(400px at 100% 0%, rgba(0,210,255,.15), transparent);
    pointer-events:none;
}
.hero-label{
    display:inline-flex;align-items:center;gap:7px;padding:6px 12px;border-radius:100px;
    background:rgba(34,197,94,.12);border:1px solid rgba(34,197,94,.2);
    color:#86efac;font-size:10px;font-weight:700;letter-spacing:.08em;
}
.status-dot{width:7px;height:7px;border-radius:50%;background:var(--success);box-shadow:0 0 10px var(--success);animation:blink 1.5s infinite}
.hero h1{margin:16px 0 8px;font-size:28px;line-height:1.05;letter-spacing:-.03em;font-weight:800}
.hero h1 span{background:linear-gradient(135deg,#fff,#7dd3fc);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.hero p{margin:0;color:var(--muted);font-size:13px;line-height:1.6;font-weight:400}
.card{
    margin-top:16px;padding:18px;border-radius:24px;
    background:var(--card);border:1px solid var(--border);
    backdrop-filter:blur(20px); -webkit-backdrop-filter:blur(20px);
    box-shadow:0 15px 40px rgba(0,0,0,.2);
    transition:.4s cubic-bezier(.16,1,.3,1);
}
.card:focus-within{border-color:rgba(0,210,255,.3);box-shadow:0 15px 40px rgba(0,0,0,.25), 0 0 0 4px rgba(0,210,255,.08)}
.input-label{font-size:10px;font-weight:700;letter-spacing:.1em;color:var(--muted);margin-bottom:10px;display:block}
.url-row{display:flex;gap:10px}
.url-input{
    flex:1;min-width:0;height:52px;border-radius:16px;
    border:1px solid rgba(255,255,255,.08);outline:none;
    background:rgba(0,0,0,.28);color:#fff;padding:0 16px;font-size:14px;font-weight:500;
    transition:.3s;
}
.url-input:focus{border-color:var(--accent);background:rgba(0,0,0,.35)}
.url-input::placeholder{color:#5d7288}
.paste-btn{
    width:52px;height:52px;flex:none;border:1px solid var(--border);border-radius:16px;
    background:var(--card);color:#fff;font-size:20px;cursor:pointer;transition:.3s;
}
.paste-btn:active{transform:scale(.93)}
.primary-btn{
    width:100%;min-height:54px;margin-top:14px;border:0;border-radius:16px;color:#fff;
    font-weight:700;font-size:14px;cursor:pointer;
    background:linear-gradient(135deg,#00b8ff,#087eff 50%,#7147ff);
    box-shadow:0 12px 28px rgba(0,132,255,.3), inset 0 1px 0 rgba(255,255,255,.3);
    transition:.3s cubic-bezier(.16,1,.3,1);
    display:flex;align-items:center;justify-content:center;gap:8px;letter-spacing:-.01em;
}
.primary-btn:hover{transform:translateY(-1px);box-shadow:0 16px 35px rgba(0,132,255,.4)}
.primary-btn:active{transform:scale(.98)}
.primary-btn:disabled{opacity:.6;transform:none!important}
.options{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px}
.option{
    background:rgba(0,0,0,.22);border:1px solid rgba(255,255,255,.06);
    border-radius:16px;padding:12px 14px;transition:.3s;
}
.option span{font-size:9px;font-weight:700;letter-spacing:.1em;color:var(--muted);display:block;margin-bottom:6px}
.option select{width:100%;border:0;outline:0;background:transparent;color:#fff;font-size:13px;font-weight:600;font-family:"Outfit"}
.info-card{display:none;margin-top:16px;overflow:hidden;border-radius:24px;background:var(--card);border:1px solid var(--border);animation:slideUp.5s cubic-bezier(.16,1,.3,1)}
@keyframes slideUp{from{opacity:0;transform:translateY(20px) scale(.98)}to{opacity:1;transform:translateY(0) scale(1)}}
.info-image{width:100%;height:200px;object-fit:cover;display:block;background:#0f1a2a}
.info-body{padding:16px}
.info-title{font-size:15px;font-weight:700;line-height:1.4;letter-spacing:-.01em}
.info-channel{color:var(--muted);font-size:12px;margin-top:6px;display:flex;align-items:center;gap:6px}
.progress-card{
    display:none;margin-top:16px;padding:18px;border-radius:24px;
    background:linear-gradient(135deg, rgba(0,198,255,.10), rgba(124,58,237,.10));
    border:1px solid rgba(255,255,255,.1);backdrop-filter:blur(20px);
    animation:slideUp.4s ease;
}
.progress-top{display:flex;justify-content:space-between;align-items:center}
.progress-title{font-size:13px;font-weight:700}
.progress-percent{font-size:22px;font-weight:800;color:#7dd3fc;font-variant-numeric:tabular-nums}
.progress-track{width:100%;height:10px;margin-top:14px;border-radius:100px;background:rgba(255,255,255,.08);overflow:hidden;padding:2px}
.progress-bar{
    height:100%;width:0%;border-radius:100px;
    background:linear-gradient(90deg,#00e5ff,#007bff,#8b5cf6);
    box-shadow:0 0 18px rgba(0,198,255,.5);transition:width.6s cubic-bezier(.16,1,.3,1);
    position:relative;overflow:hidden;
}
.progress-bar::after{
    content:"";position:absolute;inset:0;
    background:linear-gradient(90deg, transparent, rgba(255,255,255,.4), transparent);
    animation:shimmer 1.5s infinite;
}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:14px}
.stat{padding:10px 6px;border-radius:14px;background:rgba(0,0,0,.25);text-align:center;border:1px solid rgba(255,255,255,.05)}
.stat-label{font-size:9px;color:var(--muted);font-weight:700;letter-spacing:.08em;margin-bottom:4px;display:block}
.stat-value{font-size:11px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.result{display:none;margin-top:16px;animation:slideUp.5s cubic-bezier(.16,1,.3,1)}
.result-video{width:100%;max-height:340px;border-radius:20px;background:#000;display:block}
.download-file{
    display:flex;align-items:center;justify-content:center;gap:8px;
    min-height:54px;margin-top:12px;border-radius:16px;text-decoration:none;color:#fff;font-weight:700;
    background:linear-gradient(135deg,#16a34a,#0ea5e9);box-shadow:0 10px 25px rgba(22,163,74,.3);
    transition:.3s;
}
.quick-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:16px}
.quick{
    min-height:92px;border-radius:22px;border:1px solid var(--border);
    background:var(--card-2);color:#fff;cursor:pointer;text-align:left;padding:16px;
    transition:.35s cubic-bezier(.16,1,.3,1);backdrop-filter:blur(10px);
}
.quick:hover{transform:translateY(-2px);background:rgba(255,255,255,.07);border-color:rgba(255,255,255,.12)}
.quick:active{transform:scale(.97)}
.quick-icon{width:36px;height:36px;border-radius:11px;display:flex;align-items:center;justify-content:center;font-size:18px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.06)}
.quick-title{margin-top:12px;font-size:12px;font-weight:700;letter-spacing:-.01em}
.quick-sub{color:var(--muted);font-size:10px;margin-top:3px}
.bottom-nav{
    position:fixed;left:12px;right:12px;bottom:12px;z-index:200;height:72px;border-radius:24px;
    background:rgba(8,15,25,.85);border:1px solid rgba(255,255,255,.10);
    backdrop-filter:blur(24px) saturate(180%);-webkit-backdrop-filter:blur(24px) saturate(180%);
    box-shadow:0 20px 50px rgba(0,0,0,.5), inset 0 1px 0 rgba(255,255,255,.1);
    display:flex;align-items:center;justify-content:space-around;
    max-width:500px;margin:0 auto;
}
.nav-btn{
    flex:1;height:56px;border:0;background:transparent;color:#5d7288;cursor:pointer;
    display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;transition:.3s;
}
.nav-btn i{font-size:22px;transition:.3s}
.nav-btn span{font-size:9px;font-weight:700;letter-spacing:.05em}
.nav-btn.active{color:#fff}
.nav-btn.active i{transform:translateY(-1px);color:#7dd3fc;text-shadow:0 0 15px #00d2ff}
.nav-btn.active span{color:#7dd3fc}
.modal{display:none;position:fixed;inset:0;z-index:500;background:rgba(0,0,0,.7);backdrop-filter:blur(12px);padding:14px;align-items:flex-end;justify-content:center}
.modal-box{
    width:100%;max-width:600px;max-height:82vh;overflow:auto;border-radius:28px 28px 20px 20px;
    background:#0b1522;border:1px solid rgba(255,255,255,.1);padding:20px;
    animation:modalUp.4s cubic-bezier(.16,1,.3,1);box-shadow:0 30px 80px rgba(0,0,0,.6);
}
@keyframes modalUp{from{transform:translateY(100%) scale(.96);opacity:0}to{transform:translateY(0) scale(1);opacity:1}}
.modal-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
.modal-title{font-size:18px;font-weight:800;letter-spacing:-.02em}
.close{width:38px;height:38px;border:1px solid var(--border);border-radius:12px;background:var(--card);color:#fff;font-size:18px;cursor:pointer}
.list-item{padding:14px;border-radius:16px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.06);margin-top:10px;transition:.2s}
.list-item:hover{background:rgba(255,255,255,.06)}
.list-title{font-size:12px;font-weight:600;word-break:break-word;line-height:1.4}
.list-time{color:var(--muted);font-size:10px;margin-top:6px;display:flex;align-items:center;gap:6px}
.file-link{color:#7dd3fc;text-decoration:none;font-size:12px;word-break:break-word;font-weight:600;display:flex;align-items:center;gap:8px}
.empty{text-align:center;padding:45px 15px;color:var(--muted);font-size:13px}
.toast{
    position:fixed;left:50%;bottom:100px;transform:translateX(-50%) translateY(20px);
    z-index:999;min-width:260px;max-width:90vw;padding:14px 18px;border-radius:16px;
    background:rgba(13,24,38,.95);border:1px solid rgba(255,255,255,.12);
    box-shadow:0 15px 40px rgba(0,0,0,.4);color:#fff;text-align:center;font-size:13px;font-weight:500;
    opacity:0;pointer-events:none;transition:.4s cubic-bezier(.16,1,.3,1);backdrop-filter:blur(20px);
}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
.spinner{display:inline-block;width:16px;height:16px;border:2px solid rgba(255,255,255,.3);border-top-color:#fff;border-radius:50%;animation:spin.7s linear infinite;vertical-align:middle;margin-right:8px}
@keyframes spin{to{transform:rotate(360deg)}}@keyframes blink{0%,100%{opacity:1}50%{opacity:.4}}@keyframes shimmer{0%{transform:translateX(-100%)}100%{transform:translateX(200%)}}
@media(min-width:700px){.container{padding-top:26px}.hero h1{font-size:36px}}
</style>
</head>
<body>
<div class="bg-orb orb-one"></div><div class="bg-orb orb-two"></div>
<header class="app-header">
    <div class="header-row">
        <div class="brand">
            <div class="brand-icon"><i class="ri-download-2-fill"></i></div>
            <div>
                <div class="brand-title">Zihad Downloader</div>
                <div class="brand-sub">Premium • Fast • Private</div>
            </div>
        </div>
        <div style="display:flex;gap:8px">
            <button class="icon-btn" onclick="refreshApp()"><i class="ri-refresh-line"></i></button>
        </div>
    </div>
</header>
<main class="container">
    <section class="hero">
        <div class="hero-label"><span class="status-dot"></span> SERVER ONLINE • PREMIUM V2</div>
        <h1>Download anything, <span>beautifully.</span></h1>
        <p>Paste any video link, choose quality in 4K / MP3 and get instant premium download with real-time progress.</p>
    </section>
    <section class="card">
        <label class="input-label"><i class="ri-link"></i> VIDEO URL</label>
        <div class="url-row">
            <input id="url" class="url-input" type="url" autocomplete="off" placeholder="https://... paste video URL here">
            <button class="paste-btn" onclick="pasteURL()"><i class="ri-clipboard-line"></i></button>
        </div>
        <button id="infoButton" class="primary-btn" onclick="loadInfo()"><i class="ri-search-eye-line"></i> Load Video Info</button>
        <div class="options">
            <div class="option"><span><i class="ri-hd-line"></i> QUALITY</span>
                <select id="quality"><option value="360">360p • Low</option><option value="480">480p • SD</option><option value="720" selected>720p • HD</option><option value="1080">1080p • Full HD</option><option value="2160">2160p • 4K</option></select>
            </div>
            <div class="option"><span><i class="ri-film-line"></i> FORMAT</span>
                <select id="type"><option value="video">🎬 Video MP4</option><option value="audio">🎵 Audio MP3</option></select>
            </div>
        </div>
        <button id="downloadButton" class="primary-btn" style="background:linear-gradient(135deg,#0ea5e9,#6366f1)" onclick="startDownload()"><i class="ri-download-cloud-2-line"></i> Start Premium Download</button>
    </section>
    <section id="infoCard" class="info-card">
        <img id="infoImage" class="info-image" src="" alt="Thumbnail">
        <div class="info-body">
            <div id="infoTitle" class="info-title">Loading...</div>
            <div id="infoChannel" class="info-channel"><i class="ri-youtube-fill"></i> <span>Loading...</span></div>
        </div>
    </section>
    <section id="progressCard" class="progress-card">
        <div class="progress-top">
            <div id="progressTitle" class="progress-title">Downloading...</div>
            <div id="progressPercent" class="progress-percent">0%</div>
        </div>
        <div class="progress-track"><div id="progressBar" class="progress-bar"></div></div>
        <div class="stats">
            <div class="stat"><span class="stat-label">SIZE</span><span id="statSize" class="stat-value">—</span></div>
            <div class="stat"><span class="stat-label">SPEED</span><span id="statSpeed" class="stat-value">—</span></div>
            <div class="stat"><span class="stat-label">ETA</span><span id="statEta" class="stat-value">—</span></div>
        </div>
    </section>
    <section id="result" class="result"></section>
    <section class="quick-grid">
        <button class="quick" onclick="showHistory()"><div class="quick-icon"><i class="ri-history-line"></i></div><div class="quick-title">History</div><div class="quick-sub">Previous downloads</div></button>
        <button class="quick" onclick="showFiles()"><div class="quick-icon"><i class="ri-folder-3-line"></i></div><div class="quick-title">My Files</div><div class="quick-sub">Browse storage</div></button>
    </section>
</main>
<nav class="bottom-nav">
    <button class="nav-btn active" onclick="goHome()"><i class="ri-home-5-fill"></i><span>Home</span></button>
    <button class="nav-btn" onclick="showHistory()"><i class="ri-time-line"></i><span>History</span></button>
    <button class="nav-btn" onclick="showFiles()"><i class="ri-folder-3-line"></i><span>Files</span></button>
    <button class="nav-btn" onclick="refreshApp()"><i class="ri-settings-3-line"></i><span>Refresh</span></button>
</nav>
<div id="modal" class="modal" onclick="closeModalOutside(event)">
    <div class="modal-box">
        <div class="modal-header"><div id="modalTitle" class="modal-title">Downloads</div><button class="close" onclick="closeModal()"><i class="ri-close-line"></i></button></div>
        <div id="modalContent"></div>
    </div>
</div>
<div id="toast" class="toast"></div>
<script>
let progressTimer=null,downloadActive=false;
function el(id){return document.getElementById(id)}
function toast(message){const box=el("toast");box.innerText=message;box.classList.add("show");setTimeout(()=>box.classList.remove("show"),2500)}
async function pasteURL(){
    try{
        if(navigator.clipboard && navigator.clipboard.readText){
            const text=await navigator.clipboard.readText();
            if(text){el("url").value=text;toast("URL pasted ✨");}
            else toast("Clipboard empty");
        }else toast("Please paste manually");
    }catch(e){toast("Clipboard permission denied");}
}
function loadInfo(){
    const url=el("url").value.trim();
    if(!url){toast("⚠️ Enter a video URL first");el("url").focus();return;}
    const button=el("infoButton");button.disabled=true;button.innerHTML='<span class="spinner"></span> Fetching Info...';
    fetch("/info",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url:url})})
  .then(r=>r.json()).then(data=>{
        if(!data.success) throw new Error(data.error||"Failed");
        el("infoCard").style.display="block";
        el("infoImage").src=data.thumbnail||"";
        el("infoTitle").innerText=data.title||"Unknown title";
        el("infoChannel").innerHTML='<i class="ri-youtube-fill"></i> '+ (data.channel||"Unknown");
        toast("Info loaded successfully 🔥");
    }).catch(err=>{toast(err.message||"Failed to load info")})
  .finally(()=>{button.disabled=false;button.innerHTML='<i class="ri-search-eye-line"></i> Load Video Info';});
}
function startDownload(){
    if(downloadActive){toast("A download is already running ⏳");return;}
    const url=el("url").value.trim(),quality=el("quality").value,type=el("type").value;
    if(!url){toast("Enter URL first");el("url").focus();return;}
    downloadActive=true;
    const button=el("downloadButton");button.disabled=true;button.innerHTML='<span class="spinner"></span> Starting...';
    el("progressCard").style.display="block";el("result").style.display="none";el("result").innerHTML="";
    el("progressBar").style.width="0%";el("progressPercent").innerText="0%";
    el("progressTitle").innerText= type==="audio"? "Preparing MP3..." : "Preparing video...";
    fetch("/download",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url:url,quality:quality,type:type})})
  .then(r=>r.json()).then(data=>{
        if(!data.success) throw new Error(data.error||"Download failed");
        toast("Download started 🚀");startProgressMonitor();
    }).catch(err=>{
        downloadActive=false;button.disabled=false;button.innerHTML='<i class="ri-download-cloud-2-line"></i> Start Premium Download';
        toast(err.message||"Download failed");
    });
}
function startProgressMonitor(){if(progressTimer) clearInterval(progressTimer);checkProgress();progressTimer=setInterval(checkProgress,900);}
function checkProgress(){
    fetch("/progress").then(r=>r.json()).then(data=>{
        let percent=parseFloat(String(data.percent).replace("%",""));if(isNaN(percent)) percent=0;
        if(percent<0) percent=0; if(percent>100) percent=100;
        el("progressBar").style.width=percent+"%";
        el("progressPercent").innerText=percent.toFixed(percent===100?0:1)+"%";
        el("statSize").innerText=data.size||"—";el("statSpeed").innerText=data.speed||"—";el("statEta").innerText=data.eta||"—";
        if(data.title) el("progressTitle").innerText=data.title;
        if(data.status==="error"){
            stopProgressMonitor();downloadActive=false;el("downloadButton").disabled=false;
            el("downloadButton").innerHTML='<i class="ri-download-cloud-2-line"></i> Start Premium Download';
            toast("❌ "+(data.error||"Download failed"));return;
        }
        if(data.status==="finished" && data.file){
            stopProgressMonitor();downloadActive=false;el("downloadButton").disabled=false;
            el("downloadButton").innerHTML='<i class="ri-download-cloud-2-line"></i> Start Premium Download';
            el("progressBar").style.width="100%";el("progressPercent").innerText="100%";
            showResult(data.file,data.type);toast("Download completed 🎉");
        }
    }).catch(()=>{});
}
function stopProgressMonitor(){if(progressTimer){clearInterval(progressTimer);progressTimer=null;}}
function showResult(filename,type){
    const result=el("result");result.style.display="block";const encoded=encodeURIComponent(filename);
    if(type==="audio"){
        result.innerHTML='<div class="card"><div style="font-size:36px;text-align:center;padding:12px">🎵</div><div style="text-align:center;font-weight:700;font-size:13px;word-break:break-word;">'+escapeHTML(filename)+'</div><a class="download-file" href="/file/'+encoded+'" download><i class="ri-download-line"></i> Download MP3</a></div>';
    }else{
        result.innerHTML='<div class="card"><video class="result-video" controls playsinline preload="metadata" src="/file/'+encoded+'"></video><a class="download-file" href="/file/'+encoded+'" download><i class="ri-download-line"></i> Save Video</a></div>';
    }
}
function showHistory(){
    fetch("/history").then(r=>r.json()).then(data=>{
        el("modalTitle").innerText="Download History";
        if(!Array.isArray(data)||data.length===0){el("modalContent").innerHTML='<div class="empty"><i class="ri-history-line" style="font-size:28px;display:block;margin-bottom:10px"></i>No download history yet</div>';}
        else{
            let out="";data.slice().reverse().forEach(item=>{
                out+='<div class="list-item"><div class="list-title">'+escapeHTML(item.title||item.url||"Unknown")+'</div><div class="list-time"><i class="ri-time-line"></i> '+escapeHTML(item.time||"")+' • '+escapeHTML(item.type||"")+'</div></div>';
            });el("modalContent").innerHTML=out;
        }
        openModal();
    }).catch(()=>toast("Could not load history"));
}
function showFiles(){
    fetch("/files").then(r=>r.json()).then(data=>{
        el("modalTitle").innerText="My Files";
        if(!Array.isArray(data)||data.length===0){el("modalContent").innerHTML='<div class="empty"><i class="ri-folder-3-line" style="font-size:28px;display:block;margin-bottom:10px"></i>No downloaded files</div>';}
        else{
            let out="";data.forEach(filename=>{
                const enc=encodeURIComponent(filename);
                out+='<div class="list-item"><a class="file-link" href="/file/'+enc+'" download><i class="ri-file-3-line"></i> '+escapeHTML(filename)+'</a></div>';
            });el("modalContent").innerHTML=out;
        }
        openModal();
    }).catch(()=>toast("Could not load files"));
}
function openModal(){el("modal").style.display="flex";}
function closeModal(){el("modal").style.display="none";}
function closeModalOutside(e){if(e.target===el("modal")) closeModal();}
function goHome(){closeModal();window.scrollTo({top:0,behavior:"smooth"});}
function refreshApp(){toast("Refreshing...");setTimeout(()=>window.location.reload(),400);}
function escapeHTML(v){return String(v||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#039;");}
el("url").addEventListener("keydown",e=>{if(e.key==="Enter") loadInfo();});
</script>
</body>
</html>
"""

@app.route("/")
def home(): return render_template_string(HTML)

@app.route("/info", methods=["POST"])
def info():
    try:
        data = request.get_json(silent=True) or {}
        url = str(data.get("url", "")).strip()
        if not url: return jsonify({"success": False,"error": "URL is required"}), 400

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'skip_download': True,
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            j = ydl.extract_info(url, download=False)
            return jsonify({
                "success": True,
                "title": j.get("title","Unknown title"),
                "channel": j.get("channel", j.get("uploader","Unknown channel")),
                "thumbnail": j.get("thumbnail","")
            })
    except Exception as e:
        return jsonify({"success": False,"error": str(e)[:1000]}), 500

def run_download(url, quality, typ):
    start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    update_progress(percent="0%",speed="",eta="",size="",downloaded="",file="",title="Starting download...",status="downloading",error="",type=typ,quality=str(quality),started=start_time,finished="")
    try:
        # BEST OPTIONS TO BYPASS YOUTUBE BLOCK
        ydl_opts = {
            'outtmpl': os.path.join(SAVE_DIR, '%(title)s.%(ext)s'),
            'noplaylist': True,
            'progress_hooks': [my_hook],
            'nocheckcertificate': True,
            'extractor_args': {'youtube': {'player_client': ['android', 'web', 'ios']}},
            'http_headers': {'User-Agent': 'Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36'},
        }

        if typ == "audio":
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}]
            })
        else:
            # Fixed format - 720 na thakleo jeta ache seta namabe, fail korbe na
            ydl_opts.update({
                'format': f'bv*[height<={quality}]+ba/b[height<={quality}]/b/bv*+ba/b',
                'merge_output_format': 'mp4',
            })

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            update_progress(title=info.get('title', url))
            ydl.download([url])

        # Find latest file
        final_file=""
        try:
            files=[]
            for filename in os.listdir(SAVE_DIR):
                if filename.endswith('.json'): continue
                full_path=os.path.join(SAVE_DIR,filename)
                if os.path.isfile(full_path): files.append((os.path.getmtime(full_path),filename))
            if files:
                files.sort(reverse=True)
                final_file=files[0][1]
        except Exception: pass

        history=load_history()
        title=progress.get("title","")
        if (not title or title in ["Starting download...","Downloading video...","Fetching video..."]): title=url
        history.append({"title": title,"url": url,"file": final_file,"type": typ,"quality": str(quality),"time": datetime.now().strftime("%Y-%m-%d %H:%M")})
        save_history(history)

        finish_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        update_progress(percent="100%",file=final_file,status="finished",finished=finish_time)

    except Exception as e:
        print(f"ERROR: {e}")
        update_progress(status="error",error=str(e)[:800],finished=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

@app.route("/download", methods=["POST"])
def download():
    try:
        data = request.get_json(silent=True) or {}
        url=str(data.get("url","")).strip()
        quality=str(data.get("quality","720")).strip()
        typ=str(data.get("type","video")).strip()
        if not url: return jsonify({"success": False,"error": "URL is required"}), 400
        if quality not in ["360","480","720","1080","2160"]: quality="720"
        if typ not in ["video","audio"]: typ="video"

        with progress_lock: current_status=progress.get("status","idle")
        if current_status=="downloading": return jsonify({"success": False,"error": "Another download is already running"}), 409

        thread=threading.Thread(target=run_download,args=(url,quality,typ),daemon=True)
        thread.start()
        return jsonify({"success": True,"message": "Download started"})
    except Exception as e:
        return jsonify({"success": False,"error": str(e)}), 500

@app.route("/progress")
def prog():
    with progress_lock: return jsonify(dict(progress))

@app.route("/history")
def history(): return jsonify(load_history())

@app.route("/files")
def files():
    try:
        result=[]
        for filename in os.listdir(SAVE_DIR):
            if filename.endswith('.json'): continue
            full_path=os.path.join(SAVE_DIR,filename)
            if os.path.isfile(full_path): result.append(filename)
        result.sort(key=lambda x: os.path.getmtime(os.path.join(SAVE_DIR,x)), reverse=True)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/file/<path:name>")
def file(name): return send_from_directory(SAVE_DIR,name,as_attachment=False)

@app.route("/health")
def health():
    return jsonify({"status": "online","server": "Zihad Downloader V2 Fixed","port": PORT,"directory": SAVE_DIR,"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})

if __name__ == "__main__":
    print("\n====================================\n ZIHAD PREMIUM DOWNLOADER V2 FIXED\n====================================\n")
    print(f"Server: http://127.0.0.1:{PORT}\nSave: {SAVE_DIR}\n")
    app.run(host="0.0.0.0",port=PORT,threaded=True)
