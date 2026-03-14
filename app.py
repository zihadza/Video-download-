from flask import Flask, request, jsonify, render_template_string, send_from_directory
import subprocess, os, json, threading, re, time

app = Flask(__name__)

PORT = 3030
SAVE_DIR = "/storage/emulated/0/Zihad"
HISTORY_FILE = "history.json"

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
body{
background:linear-gradient(135deg,#0f2027,#203a43,#2c5364);
font-family:Arial;
color:white;
text-align:center;
padding:20px;
}

.box{
background:rgba(255,255,255,0.1);
backdrop-filter:blur(15px);
border-radius:15px;
padding:20px;
max-width:450px;
margin:auto;
box-shadow:0 0 25px rgba(0,0,0,0.4);
}

input,select,button{
width:100%;
padding:12px;
margin-top:10px;
border:none;
border-radius:10px;
}

button{
background:#ff0055;
color:white;
font-weight:bold;
}

.progress{
background:#333;
height:20px;
border-radius:10px;
overflow:hidden;
margin-top:10px;
}

.bar{
height:20px;
width:0%;
background:#00ff9d;
}

img,video{
width:100%;
border-radius:10px;
margin-top:10px;
}

.card{
background:#111;
padding:10px;
border-radius:10px;
margin-top:10px;
}

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

<button onclick="history()">History</button>
<button onclick="files()">Files</button>

<div id="result"></div>

</div>

<script>

function info(){

let url=document.getElementById("url").value

fetch("/info",{
method:"POST",
headers:{'Content-Type':'application/json'},
body:JSON.stringify({url:url})
})
.then(r=>r.json())
.then(d=>{

document.getElementById("info").innerHTML=
"<img src='"+d.thumbnail+"'>"+
"<h3>"+d.title+"</h3>"+
"<p>"+d.channel+"</p>"

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

"Progress: "+d.percent+
"<br>Size: "+d.size+
"<br>Speed: "+d.speed+
"<br>ETA: "+d.eta

if(d.file!=""){

document.getElementById("result").innerHTML=
"<video controls src='/file/"+d.file+"'></video>"+
"<br><a href='/file/"+d.file+"' download>Download File</a>"

}

})

},1000)

}

function history(){

fetch("/history")
.then(r=>r.json())
.then(d=>{

let html="<h3>Download History</h3>"

d.reverse().forEach(v=>{
html+="<div class='card'>"+v.title+"<br>"+v.time+"</div>"
})

document.getElementById("result").innerHTML=html

})

}

function files(){

fetch("/files")
.then(r=>r.json())
.then(d=>{

let html="<h3>Files</h3>"

d.forEach(v=>{
html+="<div class='card'><a href='/file/"+v+"' download>"+v+"</a></div>"
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
        "-o",SAVE_DIR+"/%(title)s.%(ext)s",url]

    else:

        cmd=[
        "yt-dlp",
        "-f",f"bestvideo[height<={quality}]+bestaudio/best",
        "--merge-output-format","webm",
        "-o",SAVE_DIR+"/%(title)s.%(ext)s",url]

    process=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)

    for line in process.stdout:

        if "[download]" in line:

            p=re.search(r'(\\d+\\.\\d+%)',line)
            s=re.search(r'of\\s+(\\S+)',line)
            sp=re.search(r'at\\s+(\\S+)',line)
            e=re.search(r'ETA\\s+(\\S+)',line)

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
    app.run(host="0.0.0.0",port=PORT)
