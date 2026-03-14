from flask import Flask, request, jsonify, render_template_string, send_from_directory
import subprocess
import os
import re
import json

app = Flask(__name__)

PORT = 3030
SAVE_DIR = "/storage/emulated/0/Zihad"

progress={
"percent":"0%",
"size":"",
"speed":"",
"eta":"",
"file":""
}

HTML="""
<!DOCTYPE html>
<html>
<head>

<meta name="viewport" content="width=device-width, initial-scale=1.0">

<title>Ultra Downloader</title>

<style>

body{
background:linear-gradient(135deg,#0f2027,#203a43,#2c5364);
font-family:Arial;
color:white;
text-align:center;
padding:20px;
}

.box{

backdrop-filter:blur(15px);
background:rgba(255,255,255,0.1);
border-radius:15px;
padding:20px;
max-width:420px;
margin:auto;
box-shadow:0 0 30px rgba(0,0,0,0.4);

}

input,select,button{

width:100%;
padding:12px;
margin-top:10px;
border:none;
border-radius:10px;

}

button{

background:#ff004c;
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

img{
width:100%;
border-radius:10px;
margin-top:10px;
}

video{
width:100%;
margin-top:10px;
border-radius:10px;
}

</style>

</head>

<body>

<div class="box">

<h2>Ultra Video Downloader</h2>

<input id="url" placeholder="Paste YouTube URL">

<button onclick="getInfo()">Load Video</button>

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

<button onclick="startDownload()">Download</button>

<div class="progress">
<div class="bar" id="bar"></div>
</div>

<p id="status"></p>

<div id="player"></div>

</div>

<script>

function getInfo(){

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

function startDownload(){

let url=document.getElementById("url").value
let quality=document.getElementById("quality").value
let type=document.getElementById("type").value

fetch("/download",{
method:"POST",
headers:{'Content-Type':'application/json'},
body:JSON.stringify({
url:url,
quality:quality,
type:type
})
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

document.getElementById("player").innerHTML=

"<video controls src='/video/"+d.file+"'></video>"+
"<br><a href='/video/"+d.file+"' download>Download</a>"

}

})

},1000)

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

    cmd=["yt-dlp","-j",url]

    data=subprocess.check_output(cmd).decode()

    j=json.loads(data)

    return jsonify({
    "title":j["title"],
    "channel":j["channel"],
    "thumbnail":j["thumbnail"]
    })


@app.route("/download",methods=["POST"])
def download():

    global progress

    data=request.json

    url=data["url"]
    quality=data["quality"]
    typ=data["type"]

    if typ=="audio":

        cmd=[
        "yt-dlp",
        "-f","bestaudio",
        "--extract-audio",
        "--audio-format","mp3",
        "-o",SAVE_DIR+"/%(title)s.%(ext)s",
        url
        ]

    else:

        cmd=[
        "yt-dlp",
        "-f",f"bestvideo[height<={quality}]+bestaudio/best",
        "--merge-output-format","webm",
        "-o",SAVE_DIR+"/%(title)s.%(ext)s",
        url
        ]

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

    return "started"


@app.route("/progress")
def prog():
    return jsonify(progress)


@app.route("/video/<name>")
def video(name):
    return send_from_directory(SAVE_DIR,name)


if __name__=="__main__":
    app.run(host="0.0.0.0",port=PORT)
