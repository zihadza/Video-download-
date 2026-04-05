from flask import Flask, request, jsonify, render_template_string, send_from_directory
import subprocess, os, json, threading, re, time, urllib.parse

app = Flask(__name__)

API_KEY = "AIzaSyBL4Cv5baQVtp5g0VrYWNd71UkjIylh8-s"

SAVE_DIR = "/storage/emulated/0/Zihad/Video-download-"
HISTORY_FILE = os.path.join(SAVE_DIR,"history.json")

if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

if not os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE,"w") as f:
        json.dump([],f)

progress = {"percent":"0%","speed":"","eta":"","size":"","file":""}

HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ultimate Downloader</title>

<style>
body{background:#0f2027;color:white;font-family:Arial;text-align:center;margin:0}
.box{max-width:420px;margin:auto;padding:15px}

input,button,select{
width:100%;padding:10px;margin-top:8px;border-radius:8px;border:none
}

button{background:#ff0055;color:white}

.card{
background:#111;padding:10px;margin-top:10px;border-radius:10px
}

img{width:100%;border-radius:10px}

.progress{
background:#333;height:15px;border-radius:10px;margin-top:10px
}

.bar{
height:15px;background:#00ff9d;width:0%
}

.video-box{
margin-top:15px;
background:#000;
border-radius:10px;
overflow:hidden;
}

iframe,video{
width:100%;
height:230px;
border:none;
border-radius:10px;
}
</style>

</head>

<body>

<div class="box">

<h2>Ultimate Downloader</h2>

<input id="search" placeholder="Search YouTube..." onkeyup="autoSearch()">
<button onclick="searchYT()">Search</button>

<input id="url" placeholder="Paste or auto set URL">

<button onclick="info()">Load Info</button>

<div id="info"></div>

<select id="quality">
<option value="360">360p</option>
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

<button onclick="history()">History</button>

<!-- ✅ VIDEO PLAYER PERFECT POSITION -->
<div id="player" class="video-box"></div>

<button onclick="files()">Files</button>

<div id="result"></div>

</div>

<script>

let t
let nextPageToken=null
let loading=false

function autoSearch(){
clearTimeout(t)
t=setTimeout(()=>{
nextPageToken=null
document.getElementById("result").innerHTML=""
searchYT()
},500)
}

function searchYT(){
let q=document.getElementById("search").value.trim()
if(!q) return

fetch("/search",{
method:"POST",
headers:{'Content-Type':'application/json'},
body:JSON.stringify({query:q,pageToken:nextPageToken})
})
.then(r=>r.json())
.then(d=>{
let html=""
d.items.forEach(v=>{
html+=`
<div class='card'>
<img src="${v.thumbnail}">
<h4>${v.title}</h4>

<button onclick="play('${v.videoId}')">▶ Play</button>
<button onclick="setURL('${v.videoId}')">Use</button>

</div>`
})

document.getElementById("result").insertAdjacentHTML("beforeend",html)
nextPageToken=d.nextPageToken
loading=false
})
}

window.onscroll=function(){
if((window.innerHeight+window.scrollY)>=document.body.offsetHeight-100 && !loading && nextPageToken){
loading=true
searchYT()
}
}

function play(id){

// ✅ PLAYER ONLY UPDATE হবে
document.getElementById("player").innerHTML=
`<iframe src="https://www.youtube.com/embed/${id}?autoplay=1" allowfullscreen></iframe>`

// ✅ URL auto set
document.getElementById("url").value="https://www.youtube.com/watch?v="+id
}

function setURL(id){
document.getElementById("url").value="https://www.youtube.com/watch?v="+id
}

function info(){
let url=document.getElementById("url").value

fetch("/info",{
method:"POST",
headers:{'Content-Type':'application/json'},
body:JSON.stringify({url})
})
.then(r=>r.json())
.then(d=>{
document.getElementById("info").innerHTML=
"<img src='"+d.thumbnail+"'><h3>"+d.title+"</h3><p>"+d.channel+"</p>"
})
}

function download(){
let url=document.getElementById("url").value
let quality=document.getElementById("quality").value
let type=document.getElementById("type").value

fetch("/download",{
method:"POST",
headers:{'Content-Type':'application/json'},
body:JSON.stringify({url,quality,type})
})

monitor()
}

function monitor(){
setInterval(()=>{
fetch("/progress")
.then(r=>r.json())
.then(d=>{
document.getElementById("bar").style.width=d.percent
document.getElementById("status").innerHTML=
d.percent+" | "+d.size+" | "+d.speed+" | "+d.eta

// ✅ download হলে player এ show
if(d.file!=""){
document.getElementById("player").innerHTML=
"<video controls src='/file/"+d.file+"'></video>"
}
})
},1000)
}

function history(){
fetch("/history").then(r=>r.json()).then(d=>{
let html=""
d.reverse().forEach(v=>{
html+="<div class='card'>"+v.title+"</div>"
})
document.getElementById("result").innerHTML=html
})
}

function files(){
fetch("/files").then(r=>r.json()).then(d=>{
let html=""
d.forEach(v=>{
html+="<div class='card'><a href='/file/"+v+"'>"+v+"</a></div>"
})
document.getElementById("result").innerHTML=html
})
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
    data = request.json
    query = data.get("query","")
    pageToken = data.get("pageToken","")

    encoded_query = urllib.parse.quote(query)

    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={encoded_query}&key={API_KEY}&maxResults=10&type=video"

    if pageToken:
        url += f"&pageToken={pageToken}"

    data = json.loads(subprocess.check_output(["curl", url]).decode())

    videos = []
    for item in data["items"]:
        videos.append({
            "title": item["snippet"]["title"],
            "videoId": item["id"]["videoId"],
            "thumbnail": item["snippet"]["thumbnails"]["high"]["url"]
        })

    return jsonify({"items": videos, "nextPageToken": data.get("nextPageToken","")})

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
        cmd=["yt-dlp","-f","bestaudio","--extract-audio","--audio-format","mp3","-o",SAVE_DIR+"/%(title)s.%(ext)s",url]
    else:
        cmd=["yt-dlp","-f",f"bestvideo[height<={quality}]+bestaudio/best","-o",SAVE_DIR+"/%(title)s.%(ext)s",url]

    process=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)

    for line in process.stdout:
        if "[download]" in line:
            p=re.search(r'(\\d+\\.\\d+%)',line)
            if p: progress["percent"]=p.group(1)

        if "Destination:" in line:
            f=line.split("Destination:")[-1].strip()
            progress["file"]=os.path.basename(f)

@app.route("/download",methods=["POST"])
def download():
    data=request.json
    threading.Thread(target=run_download,args=(data["url"],data["quality"],data["type"])).start()
    return "ok"

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
    app.run(host="0.0.0.0", port=8080)
