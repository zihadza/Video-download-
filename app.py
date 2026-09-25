
from flask import Flask, request, jsonify, render_template_string, send_from_directory
import subprocess, os, json, threading, re, time, urllib.parse
from datetime import datetime

app = Flask(__name__)

API_KEY = "AIzaSyBL4Cv5baQVtp5g0VrYWNd71UkjIylh8-s"

SAVE_DIR = "/app/downloads"
HISTORY_FILE = os.path.join(SAVE_DIR, "history.json")

if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

if not os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "w") as f:
        json.dump([], f)

progress = {
    "percent": "0%",
    "speed": "0 MB/s",
    "eta": "--",
    "size": "0 / 0",
    "file": "",
    "quality": "",
    "status": "Idle",
    "title": ""
}

HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Ultimate Downloader Pro Max</title>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&family=Space+Grotesk:wght@600;700&display=swap" rel="stylesheet">
<style>
:root{
  --bg1:#070a12; --bg2:#12182a; --card:#161c2eE6; --stroke:#ffffff14;
  --p1:#ff0055; --p2:#7c4dff; --p3:#00f5ff; --ok:#00ff9d; --text:#eaf0ff; --muted:#9aa3bf;
}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{
  margin:0; font-family:'Outfit'; color:var(--text);
  background: radial-gradient(1200px 600px at 20% -10%, #7c4dff33, transparent),
              radial-gradient(900px 500px at 90% 0%, #ff005533, transparent),
              radial-gradient(800px 600px at 50% 120%, #00f5ff22, transparent),
              linear-gradient(180deg, var(--bg1), var(--bg2));
  min-height:100vh;
}
body.amoled{ --bg1:#000000; --bg2:#000000; --card:#0c0c0fcc; }
.app{max-width:440px; margin:0 auto; padding:16px 12px 100px; position:relative}
.topbar{display:flex; align-items:center; justify-content:space-between; margin-bottom:12px}
.logo{display:flex; align-items:center; gap:10px}
.logo-badge{
  width:40px; height:40px; border-radius:12px;
  background: conic-gradient(from 0deg, var(--p1), var(--p2), var(--p3), var(--p1));
  display:grid; place-items:center; box-shadow:0 0 30px #ff005544;
}
.logo-badge span{background:#0c0f1a; width:34px; height:34px; border-radius:10px; display:grid; place-items:center; font-weight:800}
.brand h1{font-family:'Space Grotesk'; font-size:18px; margin:0}
.brand p{margin:0; font-size:10px; color:var(--muted); letter-spacing:1.2px; text-transform:uppercase}
.icon-mini{width:36px; height:36px; border-radius:12px; border:1px solid var(--stroke); background:#ffffff0c; color:white; display:grid; place-items:center}
.glass{
  background: linear-gradient(180deg, #ffffff0f, #ffffff06);
  backdrop-filter: blur(22px); -webkit-backdrop-filter: blur(22px);
  border:1px solid var(--stroke); border-radius:20px;
  box-shadow: 0 10px 40px #00000066, inset 0 1px 0 #ffffff14;
}
.hero{padding:14px; position:relative; overflow:hidden}
.input-wrap{position:relative}
.input-wrap input,.paste-wrap input{
  width:100%; background:#0e1324; border:1px solid #ffffff14; color:white;
  padding:14px 46px 14px 14px; border-radius:14px; outline:none; font-size:14px; transition:.25s;
}
.input-wrap input:focus,.paste-wrap input:focus{border-color:#7c4dff88; box-shadow:0 0 0 4px #7c4dff22; transform:translateY(-1px)}
.icon-btn{
  position:absolute; right:6px; top:6px; width:36px; height:36px; border-radius:10px;
  background: linear-gradient(135deg, var(--p1), var(--p2)); border:none; color:white; font-weight:800;
}
.chips{display:flex; gap:8px; overflow:auto; padding:10px 2px; scrollbar-width:none}
.chips::-webkit-scrollbar{display:none}
.chip{
  white-space:nowrap; padding:8px 12px; border-radius:20px; font-size:12px; font-weight:600;
  background:#ffffff0c; border:1px solid var(--stroke); color:var(--muted);
}
.chip.active{background: linear-gradient(135deg, var(--p1), var(--p2)); color:white; border-color:transparent}
.paste-wrap{position:relative; margin-top:12px}
.paste-wrap .left-icon{position:absolute; left:12px; top:50%; transform:translateY(-50%); opacity:.6}
.paste-wrap input{padding-left:36px; padding-right:92px}
.paste-actions{position:absolute; right:6px; top:6px; display:flex; gap:6px}
.mini-btn{padding:0 10px; height:32px; border-radius:8px; border:1px solid #ffffff15; background:#ffffff10; color:white; font-size:12px; font-weight:700}
.row{display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:10px}
.select{width:100%; background:#0e1324; color:white; border:1px solid #ffffff12; padding:12px; border-radius:14px; outline:none; font-size:13px}
.btn{width:100%; padding:13px; border-radius:14px; border:none; color:white; font-weight:800; letter-spacing:.3px; cursor:pointer; transition:.2s}
.btn:active{transform:scale(.97)}
.btn-primary{background: linear-gradient(135deg, var(--p1), var(--p2)); box-shadow:0 8px 24px #ff005533}
.btn-ghost{background:#ffffff0c; border:1px solid var(--stroke)}
.progress-wrap{margin-top:14px; padding:12px; border-radius:16px}
.badges{display:flex; gap:6px; flex-wrap:wrap; margin-top:8px}
.badge{display:inline-flex; padding:5px 10px; border-radius:20px; font-size:10px; letter-spacing:.6px; background:#ffffff10; border:1px solid #ffffff14; color:var(--muted)}
.badge.ok{color:#00ff9d; border-color:#00ff9d33; background:#00ff9d14}
.badge.quality{color:#00f5ff; border-color:#00f5ff33; background:#00f5ff14}
.progress{background:#0e1324; height:12px; border-radius:20px; overflow:hidden; border:1px solid #ffffff10; position:relative}
.bar{height:100%; width:0%; border-radius:20px; background: linear-gradient(90deg, var(--p1), var(--p2), var(--p3)); background-size:200% 100%; animation: gradMove 1.2s linear infinite; box-shadow:0 0 16px #7c4dff99; transition: width .4s ease}
@keyframes gradMove{0%{background-position:0%}100%{background-position:200%}}
#status{font-size:12px; color:var(--muted); margin-top:8px; line-height:1.4}
.queue{margin-top:10px; display:none}
.queue.show{display:block}
.q-item{padding:8px 10px; border-radius:12px; background:#ffffff08; border:1px dashed #ffffff14; font-size:12px; margin-top:6px; display:flex; justify-content:space-between}
.video-box{
  margin-top:14px; background:#000; border-radius:18px; overflow:hidden;
  border:1px solid var(--stroke); aspect-ratio:16/9; position:relative;
  box-shadow:0 12px 40px #0008;
}
.video-box iframe,.video-box video{width:100%; height:100%; border:none; display:block}
.video-box:empty::before{content:"PREMIUM PLAYER • Tap a video to play"; position:absolute; inset:0; display:grid; place-items:center; color:#5b6588; font-size:11px; letter-spacing:1px; text-transform:uppercase}
.player-controls{display:flex; gap:8px; margin-top:8px; flex-wrap:wrap}
.p-ctrl{flex:1; padding:9px; border-radius:12px; background:#ffffff0c; border:1px solid var(--stroke); color:white; font-size:11px; font-weight:700}
.tabs{display:flex; gap:8px; margin:14px 0 8px}
.tab{flex:1}
.card{
  background: linear-gradient(180deg, #1a2038E6, #12172aE6);
  border:1px solid var(--stroke); padding:10px; margin-top:12px; border-radius:18px;
  text-align:left; overflow:hidden; transition:.3s;
}
.card:hover{transform: translateY(-2px); border-color:#7c4dff44}
.card img{width:100%; border-radius:12px; aspect-ratio:16/9; object-fit:cover}
.card h4{margin:10px 2px 6px; font-size:14px; line-height:1.3; font-weight:600}
.card-actions{display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:8px}
.card-actions button,.card-actions a button{padding:10px; border-radius:12px; border:1px solid #ffffff14; font-weight:700; font-size:12px; width:100%}
.btn-play{background: linear-gradient(135deg, #00f5ff, #7c4dff); color:white; border:none!important}
.link-file{color:#a8f0ff; text-decoration:none; font-size:13px; word-break:break-all}
.shimmer{position:relative; overflow:hidden; min-height:90px; background: linear-gradient(90deg, #1a2038, #1e2540, #1a2038); background-size:200% 100%; animation: gradMove 1.2s linear infinite; border-radius:14px}
.toast-wrap{position:fixed; left:50%; bottom:20px; transform:translateX(-50%); z-index:99; display:flex; flex-direction:column; gap:8px; pointer-events:none}
.toast{pointer-events:auto; padding:12px 16px; border-radius:14px; background:#0f1428f2; border:1px solid #ffffff18; backdrop-filter:blur(16px); color:white; font-size:13px; font-weight:600; box-shadow:0 12px 30px #0008; animation: pop .35s ease}
@keyframes pop{from{transform:translateY(12px) scale(.96); opacity:0}to{transform:translateY(0) scale(1); opacity:1}}
.vis{height:36px; display:flex; align-items:end; gap:2px; margin-top:8px; display:none}
.vis.show{display:flex}
.vis span{width:3px; background: linear-gradient(180deg, var(--p3), var(--p2)); border-radius:10px; animation: wave .6s ease-in-out infinite alternate}
@keyframes wave{from{height:6px}to{height:32px}}
.filter-row{display:flex; gap:8px; margin-top:10px}
.filter-row button{flex:1; padding:8px; border-radius:12px; font-size:12px}
.video-thumb-wrap{position:relative; border-radius:12px; overflow:hidden; aspect-ratio:16/9; background:#000}
.video-thumb-wrap video{width:100%; height:100%; object-fit:cover; display:block}
.video-thumb-wrap .play-overlay{
  position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
  background:rgba(0,0,0,.35); opacity:0; transition:.25s; pointer-events:none;
}
.video-thumb-wrap:hover .play-overlay{opacity:1}
.play-overlay span{font-size:32px; color:white; text-shadow:0 2px 8px #000}
</style>
</head>
<body>
<div class="app">
  <div class="topbar">
    <div class="logo">
      <div class="logo-badge"><span>▶</span></div>
      <div class="brand"><h1>Ultimate Pro Max</h1><p>Animated • Premium • App Feel</p></div>
    </div>
    <div style="display:flex; gap:8px">
      <button class="icon-mini" onclick="toggleAmoled()" title="AMOLED">◐</button>
      <button class="icon-mini" onclick="shareApp()">↗</button>
    </div>
  </div>

  <div class="glass hero">
    <div class="input-wrap">
      <input id="search" placeholder="Search YouTube... anything" onkeyup="autoSearch()">
      <button class="icon-btn" onclick="vibe(); searchYT()">⌕</button>
    </div>
    <div class="chips" id="chips"></div>

    <div class="paste-wrap">
      <span class="left-icon">🔗</span>
      <input id="url" placeholder="Paste YouTube link here... auto magic ✨">
      <div class="paste-actions">
        <button class="mini-btn" onclick="pasteLink()">Paste</button>
        <button class="mini-btn" onclick="clearLink()">✕</button>
      </div>
    </div>

    <button class="btn btn-ghost" onclick="vibe(); info()" style="margin-top:10px">Load Info • Thumbnail + Channel</button>
    <div id="info"></div>

    <div class="row">
      <select id="quality" class="select">
        <option value="360">360p • Fast</option>
        <option value="720" selected>720p • HD Balanced</option>
        <option value="1080">1080p • FHD Pro</option>
      </select>
      <select id="type" class="select">
        <option value="video">Video MP4</option>
        <option value="audio">Audio MP3</option>
      </select>
    </div>
    <button class="btn btn-primary" onclick="vibe(30); download()" style="margin-top:12px">⬇ Download Now • Queue Add</button>

    <div class="glass progress-wrap">
      <div class="progress"><div class="bar" id="bar"></div></div>
      <div class="badges">
        <span class="badge" id="b-percent">0%</span>
        <span class="badge quality" id="b-quality">—</span>
        <span class="badge" id="b-size">0 / 0</span>
        <span class="badge ok" id="b-speed">0 MB/s</span>
        <span class="badge" id="b-eta">ETA --</span>
      </div>
      <p id="status">Idle • Ready to download</p>
      <div class="vis" id="vis"></div>
      <div class="queue" id="queue"><b style="font-size:11px; color:var(--muted)">QUEUE</b><div id="queueList"></div></div>
    </div>
  </div>

  <div class="tabs">
    <button class="btn btn-ghost tab" onclick="vibe(); history()">◷ History</button>
    <button class="btn btn-ghost tab" onclick="vibe(); files()">☰ Files</button>
    <button class="btn btn-ghost tab" onclick="vibe(); showFav()">❤ Fav</button>
  </div>

  <div id="player" class="video-box"></div>
  <div class="player-controls">
    <button class="p-ctrl" onclick="pip()">PiP Mode</button>
    <button class="p-ctrl" onclick="fs()">Fullscreen</button>
    <button class="p-ctrl" onclick="speed(0.5)">0.5x</button>
    <button class="p-ctrl" onclick="speed(1)">1x</button>
    <button class="p-ctrl" onclick="speed(1.5)">1.5x</button>
    <button class="p-ctrl" onclick="speed(2)">2x</button>
  </div>

  <div class="filter-row" id="fileFilters" style="display:none">
    <button class="btn-ghost" onclick="filterFiles('all')">All</button>
    <button class="btn-ghost" onclick="filterFiles('video')">Video</button>
    <button class="btn-ghost" onclick="filterFiles('audio')">Audio</button>
    <input id="fileSearch" placeholder="Search files..." onkeyup="filterFiles(currentFilter)" style="flex:2; background:#0e1324; border:1px solid #ffffff12; color:white; border-radius:12px; padding:8px 10px">
  </div>

  <div id="result"></div>
</div>

<div class="toast-wrap" id="toasts"></div>

<script>
let t, nextPageToken = null, loading = false, currentFilter = 'video', allFiles = [], favList = JSON.parse(localStorage.getItem('fav') || '[]'), queueArr = [];

const categories = ["Music", "Bangla Natok", "Waz", "Gaming", "News", "Cartoon", "4K"];

function renderChips() {
  const container = document.getElementById("chips");
  container.innerHTML = "";
  categories.forEach(function(c) {
    const div = document.createElement("div");
    div.className = "chip";
    div.textContent = c;
    div.onclick = function() { chipSearch(this, c); };
    container.appendChild(div);
  });
}
renderChips();

function chipSearch(el, txt) {
  document.querySelectorAll('.chip').forEach(x => x.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('search').value = txt;
  nextPageToken = null;
  document.getElementById('result').innerHTML = "";
  searchYT();
}

function vibe(ms) {
  if (navigator.vibrate) navigator.vibrate(ms || 20);
}

function toast(msg) {
  const w = document.getElementById("toasts");
  const d = document.createElement('div');
  d.className = 'toast';
  d.innerText = msg;
  w.appendChild(d);
  setTimeout(function() {
    d.style.opacity = '0';
    d.style.transform = 'translateY(10px)';
    setTimeout(function() { d.remove(); }, 300);
  }, 2600);
}

function toggleAmoled() {
  document.body.classList.toggle('amoled');
  toast(document.body.classList.contains('amoled') ? 'AMOLED Black ON' : 'AMOLED Black OFF');
}

function shareApp() {
  if (navigator.share) {
    navigator.share({ title: 'Ultimate Downloader', url: location.href });
  } else {
    toast('Link copied!');
    navigator.clipboard.writeText(location.href);
  }
}

async function pasteLink() {
  try {
    const txt = await navigator.clipboard.readText();
    document.getElementById('url').value = txt;
    toast('Pasted ✨');
    if (txt.includes('youtu')) info();
  } catch (e) {
    toast('Paste permission blocked');
  }
}

function clearLink() {
  document.getElementById('url').value = '';
  toast('Cleared');
}

function autoSearch() {
  clearTimeout(t);
  t = setTimeout(function() {
    nextPageToken = null;
    document.getElementById("result").innerHTML = "";
    searchYT();
  }, 500);
}

function shimmerHTML() {
  let h = "";
  for (let i = 0; i < 4; i++) {
    h += "<div class='card'><div class='shimmer' style='height:180px'></div><div class='shimmer' style='height:18px; margin-top:10px'></div></div>";
  }
  return h;
}

function searchYT() {
  const q = document.getElementById("search").value.trim();
  if (!q) return;
  if (nextPageToken == null) document.getElementById("result").innerHTML = shimmerHTML();
  loading = true;

  fetch("/search", {
    method: "POST",
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: q, pageToken: nextPageToken })
  })
  .then(r => r.json())
  .then(function(d) {
    let html = "";
    (d.items || []).forEach(function(v) {
      html += "<div class='card'>" +
        "<img src='" + v.thumbnail + "' loading='lazy' style='transition:.4s'>" +
        "<h4>" + v.title + "</h4>" +
        "<div class='card-actions'>" +
          "<button class='btn-play' onclick=\"vibe(); play('" + v.videoId + "')\">▶ Play</button>" +
          "<button class='btn-ghost' style='color:white' onclick=\"vibe(); setURL('" + v.videoId + "')\">↗ Use</button>" +
        "</div></div>";
    });
    if (nextPageToken == null) document.getElementById("result").innerHTML = html;
    else document.getElementById("result").insertAdjacentHTML("beforeend", html);
    nextPageToken = d.nextPageToken || null;
    loading = false;
  })
  .catch(function() { loading = false; });
}

window.onscroll = function() {
  if ((window.innerHeight + window.scrollY) >= document.body.offsetHeight - 120 && !loading && nextPageToken) {
    loading = true;
    searchYT();
  }
};

function play(id) {
  document.getElementById("player").innerHTML = '<iframe src="https://www.youtube.com/embed/' + id + '?autoplay=1&modestbranding=1&rel=0" allowfullscreen allow="autoplay; picture-in-picture"></iframe>';
  document.getElementById("url").value = "https://www.youtube.com/watch?v=" + id;
  document.getElementById("player").scrollIntoView({ behavior: 'smooth', block: 'center' });
  toast('Preview Playing ▶');
}

function setURL(id) {
  document.getElementById("url").value = "https://www.youtube.com/watch?v=" + id;
  toast('Link Set ↘');
}

function info() {
  const url = document.getElementById("url").value;
  if (!url) { toast('Paste link first!'); return; }
  toast('Fetching info...');
  fetch("/info", {
    method: "POST",
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url: url })
  })
  .then(r => r.json())
  .then(function(d) {
    const title = d.title || "Unknown Title";
    const channel = d.channel || "Unknown Channel";
    const thumb = d.thumbnail || "";
    document.getElementById("info").innerHTML =
      "<div class='card'>" +
        (thumb ? "<img src='" + thumb + "' style='width:100%;border-radius:12px;aspect-ratio:16/9;object-fit:cover'>" : "") +
        "<h4>" + title + "</h4>" +
        "<p style='color:var(--muted); font-size:12px; margin:4px 0 0'>" + channel + "</p>" +
      "</div>";
  })
  .catch(function() { toast('Info fetch failed'); });
}

function download() {
  const url = document.getElementById("url").value;
  const quality = document.getElementById("quality").value;
  const type = document.getElementById("type").value;
  if (!url) { toast('URL missing!'); return; }

  queueArr.push({ url: url, quality: quality, type: type });
  renderQueue();

  fetch("/download", {
    method: "POST",
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url: url, quality: quality, type: type })
  });

  toast('Download Started 🔥');
  document.getElementById("b-quality").innerText = (type === 'audio') ? 'MP3' : (quality + 'p');
  monitor();

  if (type === 'audio') {
    const vis = document.getElementById('vis');
    vis.classList.add('show');
    vis.innerHTML = '';
    for (let i = 0; i < 22; i++) {
      const s = document.createElement('span');
      s.style.animationDelay = (i * 0.06) + 's';
      s.style.height = (10 + Math.random() * 26) + 'px';
      vis.appendChild(s);
    }
  } else {
    document.getElementById('vis').classList.remove('show');
  }
}

function renderQueue() {
  const q = document.getElementById('queue');
  q.classList.add('show');
  let html = "";
  queueArr.forEach(function(u, i) {
    html += "<div class='q-item'><span>#" + (i + 1) + " " + u.url.slice(0, 32) + "... (" + (u.quality || u.type) + ")</span><span>⏳</span></div>";
  });
  document.getElementById('queueList').innerHTML = html;
}

let monitorInterval = null;
function monitor() {
  if (monitorInterval) clearInterval(monitorInterval);
  monitorInterval = setInterval(function() {
    fetch("/progress")
    .then(r => r.json())
    .then(function(d) {
      document.getElementById("bar").style.width = d.percent || '0%';
      document.getElementById("b-percent").innerText = d.percent || '0%';
      document.getElementById("b-size").innerText = d.size || '0 / 0';
      document.getElementById("b-speed").innerText = d.speed || '0 MB/s';
      document.getElementById("b-eta").innerText = 'ETA ' + (d.eta || '--');
      if (d.quality) document.getElementById("b-quality").innerText = d.quality;

      document.getElementById("status").innerHTML =
        (d.status || '') + " • " + (d.title || '') + "<br>" +
        (d.percent || '') + " | " + (d.size || '') + " | " + (d.speed || '') + " | ETA " + (d.eta || '--');

      if (d.file && d.file !== "") {
        const vp = document.getElementById("player");
        const encoded = encodeURIComponent(d.file);
        if (!vp.innerHTML.includes(encoded) || vp.innerHTML.includes('iframe')) {
          vp.innerHTML = "<video id='mainVideo' controls autoplay playsinline src='/file/" + encoded + "'></video>";
          toast('Ready to Play • ' + d.file);
          if (queueArr.length) queueArr.shift();
          renderQueue();
        }
      }
    });
  }, 800);
}

function pip() {
  const v = document.getElementById('mainVideo');
  if (v && document.pictureInPictureEnabled) v.requestPictureInPicture();
  else toast('PiP not supported');
}

function fs() {
  const v = document.getElementById('player');
  if (v.requestFullscreen) v.requestFullscreen();
}

function speed(s) {
  const v = document.getElementById('mainVideo');
  if (v) { v.playbackRate = s; toast(s + 'x Speed'); }
  else toast('Play a local video first');
}

function history() {
  fetch("/history")
  .then(r => r.json())
  .then(function(d) {
    document.getElementById('fileFilters').style.display = 'none';
    let html = "<div class='badge' style='margin-top:6px'>History • Last Downloads</div>";
    if (!d || d.length === 0) {
      html += "<div class='card'><h4>No history yet</h4></div>";
    } else {
      d.slice().reverse().forEach(function(v) {
        const safeFile = (v.file || "").replace(/'/g, "\\'");
        html += "<div class='card'>" +
          "<h4>" + (v.title || 'Unknown') + "</h4>" +
          "<p style='color:var(--muted);font-size:12px;margin:4px 0'>" + (v.quality || '') + " • " + (v.date || '') + "</p>" +
          "<div class='card-actions'>" +
            "<button class='btn-play' onclick=\"playLocal('" + safeFile + "')\">▶ Play</button>" +
            "<button class='btn-ghost' style='color:white' onclick=\"toast('File: " + safeFile + "')\">↗ Info</button>" +
          "</div></div>";
      });
    }
    document.getElementById("result").innerHTML = html;
  });
}

function files() {
  fetch("/files")
  .then(r => r.json())
  .then(function(d) {
    allFiles = d || [];
    document.getElementById('fileFilters').style.display = 'flex';
    currentFilter = 'video';
    filterFiles('video');
  });
}

function isVideoFile(name) {
  const n = name.toLowerCase();
  return n.endsWith('.mp4') || n.endsWith('.mkv') || n.endsWith('.webm') || n.endsWith('.avi') || n.endsWith('.mov') || n.endsWith('.m4v');
}

function isAudioFile(name) {
  const n = name.toLowerCase();
  return n.endsWith('.mp3') || n.endsWith('.m4a') || n.endsWith('.aac') || n.endsWith('.ogg') || n.endsWith('.wav');
}

function renderFiles(list) {
  let html = "<div class='badge' style='margin-top:6px'>Files • " + list.length + " items</div>";
  list.forEach(function(v) {
    const isAudio = isAudioFile(v);
    const isFav = favList.includes(v);
    const safeName = v.replace(/'/g, "\\'");
    const encoded = encodeURIComponent(v);

    html += "<div class='card'>" +
      "<div class='video-thumb-wrap' onclick=\"playLocal('" + safeName + "')\">" +
        "<video muted preload='metadata' src='/file/" + encoded + "#t=1' onloadeddata='this.currentTime=1'></video>" +
        "<div class='play-overlay'><span>▶</span></div>" +
      "</div>" +
      "<h4 style='margin-top:8px'>" + (isAudio ? '🎵 ' : '🎬 ') + v + "</h4>" +
      "<div class='card-actions' style='margin-top:8px'>" +
        "<button class='btn-play' onclick=\"playLocal('" + safeName + "')\">▶ Play</button>" +
        "<button class='btn-ghost' style='color:white' onclick=\"toggleFav('" + safeName + "')\">" + (isFav ? '❤️ Fav' : '🤍 Fav') + "</button>" +
      "</div>" +
      "<div class='card-actions' style='margin-top:6px'>" +
        "<a href='/file/" + encoded + "' download style='text-decoration:none'><button class='btn-ghost' style='color:white'>⬇ Save</button></a>" +
        "<button class='btn-ghost' style='color:white' onclick=\"shareFile('" + safeName + "')\">↗ Share</button>" +
      "</div></div>";
  });
  if (list.length === 0) html += "<div class='card'><h4>No files found</h4></div>";
  document.getElementById("result").innerHTML = html;
}

function filterFiles(type) {
  currentFilter = type;
  const q = (document.getElementById('fileSearch') && document.getElementById('fileSearch').value || '').toLowerCase();
  const filtered = allFiles.filter(function(f) {
    let okType = true;
    if (type === 'video') okType = isVideoFile(f);
    if (type === 'audio') okType = isAudioFile(f);
    return okType && f.toLowerCase().includes(q);
  });
  renderFiles(filtered);
}

function playLocal(name) {
  const encoded = encodeURIComponent(name);
  document.getElementById("player").innerHTML = "<video id='mainVideo' controls autoplay playsinline src='/file/" + encoded + "'></video>";
  document.getElementById("player").scrollIntoView({ behavior: 'smooth', block: 'center' });
  toast('Playing • ' + name);
}

function toggleFav(name) {
  if (favList.includes(name)) {
    favList = favList.filter(function(x) { return x !== name; });
  } else {
    favList.push(name);
  }
  localStorage.setItem('fav', JSON.stringify(favList));
  toast(favList.includes(name) ? 'Added to Favourite ❤️' : 'Removed from Fav');

  if (document.getElementById('fileFilters').style.display !== 'none') {
    filterFiles(currentFilter);
  } else {
    showFav();
  }
}

function showFav() {
  document.getElementById('fileFilters').style.display = 'none';
  if (favList.length === 0) {
    document.getElementById('result').innerHTML = "<div class='card'><h4>No favourites yet 🤍</h4><p style='color:var(--muted); font-size:12px'>Files e giye ❤️ Fav chapun</p></div>";
    return;
  }
  fetch("/files")
  .then(r => r.json())
  .then(function(all) {
    const existing = favList.filter(function(f) { return all.includes(f); });
    renderFiles(existing);
  });
}

function shareFile(name) {
  if (navigator.share) {
    navigator.share({ title: name, url: location.origin + '/file/' + encodeURIComponent(name) });
  } else {
    navigator.clipboard.writeText(location.origin + '/file/' + encodeURIComponent(name));
    toast('Link copied!');
  }
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
    data = request.json or {}
    query = data.get("query", "")
    pageToken = data.get("pageToken", "")

    encoded_query = urllib.parse.quote(query)
    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={encoded_query}&key={API_KEY}&maxResults=10&type=video"
    if pageToken:
        url += f"&pageToken={pageToken}"

    try:
        raw = subprocess.check_output(["curl", "-s", url], timeout=15).decode()
        data = json.loads(raw)
    except Exception as e:
        return jsonify({"items": [], "nextPageToken": "", "error": str(e)})

    videos = []
    for item in data.get("items", []):
        try:
            videos.append({
                "title": item["snippet"]["title"],
                "videoId": item["id"]["videoId"],
                "thumbnail": item["snippet"]["thumbnails"]["high"]["url"]
            })
        except:
            continue

    return jsonify({"items": videos, "nextPageToken": data.get("nextPageToken", "")})

@app.route("/info", methods=["POST"])
def info():
    url = (request.json or {}).get("url", "")
    if not url:
        return jsonify({"title": "", "channel": "", "thumbnail": ""})
    try:
        data = subprocess.check_output(["yt-dlp", "-j", "--no-playlist", url], timeout=30).decode()
        j = json.loads(data)
        return jsonify({
            "title": j.get("title", ""),
            "channel": j.get("channel") or j.get("uploader", ""),
            "thumbnail": j.get("thumbnail", "")
        })
    except Exception as e:
        return jsonify({"title": "Error", "channel": str(e), "thumbnail": ""})

def parse_progress_line(line):
    info = {}
    # Percent
    m = re.search(r'(\d+\.?\d*)%', line)
    if m:
        info["percent"] = m.group(1) + "%"

    # Size - handles: 12.3MiB of 45.6MiB  |  of \~ 234.5MiB  |  12.3MiB / 45.6MiB
    m = re.search(r'([\d\.]+[KMG]?i?B)\s+(?:of|\/)\s+\~?\s*([\d\.]+[KMG]?i?B)', line, re.I)
    if m:
        info["size"] = f"{m.group(1)} / {m.group(2)}"
    else:
        # only total size with \~
        m = re.search(r'of\s+\~?\s*([\d\.]+[KMG]?i?B)', line, re.I)
        if m:
            info["size"] = f"? / {m.group(1)}"

    # Speed
    m = re.search(r'at\s+([\d\.]+[KMG]?i?B/s)', line, re.I)
    if m:
        speed_str = m.group(1)
        info["speed"] = speed_str
        try:
            num = float(re.search(r'([\d\.]+)', speed_str).group(1))
            unit = speed_str.upper()
            if 'KI' in unit or 'KB' in unit:
                mbps = (num * 8) / 1000
            elif 'MI' in unit or 'MB' in unit:
                mbps = num * 8
            elif 'GI' in unit or 'GB' in unit:
                mbps = num * 8000
            else:
                mbps = (num * 8) / 1000000
            info["speed"] = f"{speed_str} (\~{mbps:.1f} Mbps)"
        except:
            pass

    # ETA
    m = re.search(r'ETA\s+(\d+:\d+(?::\d+)?)', line)
    if m:
        info["eta"] = m.group(1)

    return info

def run_download(url, quality, typ):
    global progress

    progress.update({
        "percent": "0%",
        "speed": "0 MB/s",
        "eta": "--",
        "size": "0 / 0",
        "file": "",
        "quality": "MP3" if typ == "audio" else f"{quality}p",
        "status": "Starting...",
        "title": ""
    })

    try:
        meta = subprocess.check_output(["yt-dlp", "-j", "--no-playlist", url], timeout=20).decode()
        j = json.loads(meta)
        progress["title"] = (j.get("title") or "")[:70]
    except:
        progress["title"] = "Unknown"

    if typ == "audio":
        cmd = [
            "yt-dlp", "-f", "bestaudio",
            "--extract-audio", "--audio-format", "mp3",
            "--newline", "-o", SAVE_DIR + "/%(title)s.%(ext)s",
            "--no-playlist", url
        ]
    else:
        cmd = [
            "yt-dlp",
            "-f", f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best",
            "--merge-output-format", "mp4",
            "--newline", "-o", SAVE_DIR + "/%(title)s.%(ext)s",
            "--no-playlist", url
        ]

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    final_file = ""
    for line in process.stdout:
        line = line.strip()
        if not line:
            continue

        if "Destination:" in line or "Merging formats into" in line:
            parts = line.split('"')
            if len(parts) >= 2:
                final_file = os.path.basename(parts[1])
            else:
                final_file = os.path.basename(line.split()[-1].strip('"'))
            progress["file"] = final_file
            progress["status"] = "Downloading..."

        if "[download]" in line:
            parsed = parse_progress_line(line)
            progress.update(parsed)
            progress["status"] = "Downloading..."

        if "100%" in line or "has already been downloaded" in line:
            progress["percent"] = "100%"
            progress["status"] = "Finishing..."

    process.wait()

    if not final_file:
        try:
            files = sorted(
                [f for f in os.listdir(SAVE_DIR) if not f.endswith(".json")],
                key=lambda x: os.path.getmtime(os.path.join(SAVE_DIR, x)),
                reverse=True
            )
            if files:
                final_file = files[0]
                progress["file"] = final_file
        except:
            pass

    progress["percent"] = "100%"
    progress["status"] = "Completed ✓"
    progress["eta"] = "00:00"
    progress["speed"] = "Done"

    if final_file:
        try:
            with open(HISTORY_FILE, "r") as f:
                hist = json.load(f)
            hist.append({
                "title": progress.get("title") or final_file,
                "file": final_file,
                "quality": progress.get("quality", ""),
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "type": typ
            })
            hist = hist[-50:]
            with open(HISTORY_FILE, "w") as f:
                json.dump(hist, f, indent=2)
        except Exception as e:
            print("History save error:", e)

@app.route("/download", methods=["POST"])
def download():
    data = request.json or {}
    url = data.get("url", "")
    quality = data.get("quality", "720")
    typ = data.get("type", "video")
    if not url:
        return "missing url", 400
    threading.Thread(target=run_download, args=(url, quality, typ), daemon=True).start()
    return "ok"

@app.route("/progress")
def prog():
    return jsonify(progress)

@app.route("/history")
def history():
    try:
        with open(HISTORY_FILE) as f:
            return jsonify(json.load(f))
    except:
        return jsonify([])

@app.route("/files")
def files():
    try:
        items = [f for f in os.listdir(SAVE_DIR) if not f.endswith(".json") and not f.startswith(".")]
        items.sort(key=lambda x: os.path.getmtime(os.path.join(SAVE_DIR, x)), reverse=True)
        return jsonify(items)
    except:
        return jsonify([])

@app.route("/file/<path:name>")
def file(name):
    return send_from_directory(SAVE_DIR, name)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8585, threaded=True)
