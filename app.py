from flask import Flask, request, jsonify, render_template_string, send_from_directory
import subprocess, os, json, threading, re, time

app = Flask(__name__)

PORT = 3030
SAVE_DIR = "/storage/emulated/0/Zihad/Video-download-"
HISTORY_FILE = os.path.join(SAVE_DIR,"history.json")

if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

if not os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE,"w") as f:
        json.dump([],f)

progress = {"percent":"0%","speed":"","eta":"","size":"","file":""}

HTML = """ <!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ultimate Downloader</title>
<style>
body{background:linear-gradient(135deg,#0f2027,#203a43,#2c5364); font-family:Arial;color:white;text-align:center;padding:20px;}
.box{background:rgba(255,255,255,0.1);backdrop-filter:blur(15px);border-radius:15px;padding:20px;max-width:450px;margin:auto;box-shadow:0 0 25px rgba(0,0,0,0.4);}
input,select,button{width:100%;padding:12px;margin-top:10px;border:none;border-radius:10px;}
button{background:#ff0055;color:white;font-weight:bold;}
.progress{background:#333;height:20px;border-radius:10px;overflow:hidden;margin-top:10px;}
.bar{height:20px;width:0%;background:#00ff9d;}
img,video{width:100%;border-radius:10px;margin-top:10px;}
.card{background:#111;padding:10px;border-radius:10px;margin-top:10px;}
a{color:#00ff9d}
</style>
</head>
<body>
<div class="box">
<h2>Ultimate Downloader</h2>
<input id="url" placeholder="Paste video URL">
<button onclick="info()">Load Info</button>
<div id="info"></div>
<select id="quality">
<option value="360">360p</option>
<option value="480">480p</option>
<option value="720">720p</option>
<option value="1080">1080p</option>
</select>
<select id="type">
<option value="video">Video</option>
<option value="audio">MP3</option>
</select>
<button onclick="download()">Download</button>
<div class="progress"><div class="bar" id="bar"></div></div>
<p id="status"></p>
<button onclick="history()">History</button> <button onclick="files()">Files</button>
<div id="result"></div>
</div>
<script>
function info(){
let url=document.getElementById("url").value
fetch("/info",{ method:"POST", headers:{'Content-Type':'application/json'}, body:JSON.stringify({url:url}) })
.then(r=>r.json())
.then(d=>{
document.getElementById("info").innerHTML= "<img src='"+d.thumbnail+"'>"+ "<h3>"+d.title+"</h3>"+ "<p>"+d.channel+"</p>"
})
}
function download(){
let url=document.getElementById("url").value
let quality=document.getElementById("quality").value
let type=document.getElementById("type").value
fetch("/download",{ method:"POST", headers:{'Content-Type':'application/json'}, body:JSON.stringify({url,quality,type}) })
monitor()
}
function monitor(){
setInterval(()=>{
fetch("/progress")
.then(r=>r.json())
.then(d=>{
document.getElementById("bar").style.width=d.percent
document.getElementById("status").innerHTML=
"Progress: "+d.percent+ "<br>Size: "+d.size+ "<br>Speed: "+d.speed+ "<br>ETA: "+d.eta
if(d.file!=""){
document.getElementById("result").innerHTML= "<video controls src='/file/"+d.file+"'></video>"+ "<br><a href='/file/"+d.file+"' download>Download File</a>"
}
})
},1000)
}
function history(){
fetch("/history")
.then(r=>r.json())
.then(d=>{
let html="<h3>Download History</h3>"
d.reverse().forEach(v=>{ html+="<div class='card'>"+v.title+"<br>"+v.time+"</div>" })
document.getElementById("result").innerHTML=html
})
}
function files(){
fetch("/files")
.then(r=>r.json())
.then(d=>{
let html="<h3>Files</h3>"
d.forEach(v=>{ html+="<div class='card'><a href='/file/"+v+"' download>"+v+"</a></div>" })
document.getElementById("result").innerHTML=html
})
}
</script>
  
<!-- ZI_-_HA-_-D Premium Widget -->
<style>
/* Wrapper fixed + isolated */
.ziha-wrapper{
  position:fixed;
  top:50%;
  left:50%;
  transform:translate(-50%,-50%);
  cursor:grab;
  z-index:999999; /* Always on top */
  pointer-events:auto; /* Can interact with widget */
}

/* Card */
.ziha-widget{
  width:300px;
  padding:18px;
  border-radius:16px;
  background:rgba(15,23,42,0.88);
  backdrop-filter:blur(12px);
  border:1px solid rgba(255,255,255,0.08);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto;
  color:#e2e8f0;
  text-align:center;
  box-shadow:0 8px 28px rgba(0,0,0,0.5);
  transition:0.3s ease;
  pointer-events:auto;
}
.ziha-widget:hover{
  transform:translateY(-3px) scale(1.01);
}

/* Image */
.ziha-widget img{
  width:60px;
  height:60px;
  border-radius:50%;
  margin-bottom:10px;
  border:2px solid #22c55e;
}

/* Text */
.ziha-powered{
  font-size:12px;
  color:#94a3b8;
  margin-bottom:4px;
}
.ziha-greet{
  font-size:15px;
  font-weight:500;
  color:#cbd5f5;
  margin-bottom:6px;
}
.ziha-time{
  font-size:26px;
  font-weight:600;
  color:#22c55e;
}
.ziha-date{
  font-size:13px;
  color:#94a3b8;
  margin-bottom:10px;
}

/* Info box */
.info-box{
  display:flex;
  gap:6px;
  margin-top:5px;
}
.info-item{
  flex:1;
  padding:6px;
  border-radius:10px;
  font-size:11px;
  font-weight:500;
  background:linear-gradient(135deg,#1e3a8a,#22c55e);
  color:#f1f5f9;
  text-shadow:0 1px 1px rgba(0,0,0,0.3);
  transition:0.4s;
}

/* Battery bar */
.battery-bar{
  width:100%;
  height:5px;
  background:rgba(255,255,255,0.07);
  border-radius:10px;
  margin-top:6px;
  overflow:hidden;
}
.battery-fill{
  height:100%;
  width:50%;
  background:#22c55e;
  transition:0.5s ease;
}

/* Prevent interfering with page content */
body *:not(.ziha-wrapper):not(.ziha-wrapper *){pointer-events:auto;}
</style>

<div class="ziha-wrapper" id="dragBox">
  <div class="ziha-widget">
    <img src="zihad.png">
    <div class="ziha-powered">Powered by ZI_-_HA-_-D</div>
    <div class="ziha-greet" id="greet">Hello</div>
    <div class="ziha-time" id="time">--:--</div>
    <div class="ziha-date" id="date">Loading...</div>

    <div class="info-box">
      <div class="info-item" id="batteryText">🔋 --%</div>
      <div class="info-item" id="net">🌐 --</div>
      <div class="info-item" id="ip">🌍 --</div>
    </div>

    <div class="battery-bar">
      <div class="battery-fill" id="batteryFill"></div>
    </div>
  </div>
</div>

<script>
// Time
function updateTime(){
  const now=new Date();
  const days=["রবি","সোম","মঙ্গল","বুধ","বৃহস্পতি","শুক্র","শনি"];
  const months=["January","February","March","April","May","June","July","August","September","October","November","December"];

  let h=now.getHours(),m=now.getMinutes(),s=now.getSeconds();
  let greet="Good Night";
  if(h>=5&&h<12)greet="Good Morning";
  else if(h<17)greet="Good Afternoon";
  else if(h<20)greet="Good Evening";

  let ampm=h>=12?"PM":"AM";
  h=h%12||12;
  m=m<10?"0"+m:m;
  s=s<10?"0"+s:s;

  time.innerText=`${h}:${m}:${s} ${ampm}`;
  date.innerText=`${days[now.getDay()]}, ${now.getDate()} ${months[now.getMonth()]}`;
  greetEl.innerText=greet;
}
const time=document.getElementById("time");
const date=document.getElementById("date");
const greetEl=document.getElementById("greet");
setInterval(updateTime,1000);
updateTime();

// Battery
navigator.getBattery().then(b=>{
  function update(){
    let level=Math.round(b.level*100);
    batteryText.innerText="🔋 "+level+"%";
    batteryFill.style.width=level+"%";
    batteryFill.style.background=level>50?"#22c55e":level>20?"#f59e0b":"#ef4444";
  }
  update();
  b.addEventListener("levelchange",update);
});

// Internet
function net(){
  document.getElementById("net").innerText=
    navigator.onLine?"🌐 Online":"Offline";
}
window.addEventListener("online",net);
window.addEventListener("offline",net);
net();

// IP fallback
function loadIP(){
  fetch("https://api.ipify.org?format=json")
  .then(r=>r.json())
  .then(d=>{document.getElementById("ip").innerText="🌍 "+d.ip;})
  .catch(()=>{
    fetch("https://api64.ipify.org?format=json")
    .then(r=>r.json())
    .then(d=>{document.getElementById("ip").innerText="🌍 "+d.ip;})
    .catch(()=>{document.getElementById("ip").innerText="🌍 N/A";});
  });
}
loadIP();

// Drag
const box=document.getElementById("dragBox");
let drag=false,x,y;

box.onmousedown=e=>{
  drag=true;
  x=e.clientX-box.offsetLeft;
  y=e.clientY-box.offsetTop;
};
document.onmousemove=e=>{
  if(!drag)return;
  box.style.left=(e.clientX-x)+"px";
  box.style.top=(e.clientY-y)+"px";
  box.style.transform="none";
};
document.onmouseup=()=>drag=false;

// Touch
box.ontouchstart=e=>{
  let t=e.touches[0];
  drag=true;
  x=t.clientX-box.offsetLeft;
  y=t.clientY-box.offsetTop;
};
document.ontouchmove=e=>{
  if(!drag)return;
  let t=e.touches[0];
  box.style.left=(t.clientX-x)+"px";
  box.style.top=(t.clientY-y)+"px";
  box.style.transform="none";
};
document.ontouchend=()=>drag=false;
</script>



</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(HTML)

@app.route("/info",methods=["POST"])
def info():
    url=request.json["url"]
    data=subprocess.check_output(["yt-dlp","-j",url]).decode()
    j=json.loads(data)
    return jsonify({
        "title":j.get("title",""),
        "channel":j.get("channel",""),
        "thumbnail":j.get("thumbnail","")
    })

def run_download(url,quality,typ):
    global progress
    if typ=="audio":
        cmd=[
            "yt-dlp","-f","bestaudio",
            "--extract-audio","--audio-format","mp3",
            "-o",os.path.join(SAVE_DIR,"%(title)s.%(ext)s"),url
        ]
    else:
        cmd=[
            "yt-dlp",
            "-f",f"bestvideo[height<={quality}]+bestaudio/best",
            "--merge-output-format","webm",
            "-o",os.path.join(SAVE_DIR,"%(title)s.%(ext)s"),url
        ]
    process=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    for line in process.stdout:
        if "[download]" in line:
            p=re.search(r'(\d+\.\d+%)',line)
            s=re.search(r'of\s+(\S+)',line)
            sp=re.search(r'at\s+(\S+)',line)
            e=re.search(r'ETA\s+(\S+)',line)
            if p: progress["percent"]=p.group(1)
            if s: progress["size"]=s.group(1)
            if sp: progress["speed"]=sp.group(1)
            if e: progress["eta"]=e.group(1)
        if "Destination:" in line:
            f=line.split("Destination:")[-1].strip()
            progress["file"]=os.path.basename(f)
    with open(HISTORY_FILE) as f:
        h=json.load(f)
    h.append({"title":url,"time":time.strftime("%Y-%m-%d %H:%M")})
    with open(HISTORY_FILE,"w") as f:
        json.dump(h,f)

@app.route("/download",methods=["POST"])
def download():
    data=request.json
    threading.Thread(target=run_download,args=(data["url"],data["quality"],data["type"])).start()
    return "started"

@app.route("/progress")
def prog():
    return jsonify(progress)

@app.route("/history")
def history():
    with open(HISTORY_FILE) as f:
        return jsonify(json.load(f))

@app.route("/files")
def files():
    return jsonify(os.listdir(SAVE_DIR))

@app.route("/file/<name>")
def file(name):
    return send_from_directory(SAVE_DIR,name)

if __name__=="__main__":
    app.run(host="0.0.0.0", port=3030)
