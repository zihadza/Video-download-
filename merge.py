from flask import Flask, render_template_string, request, jsonify
import os, subprocess, re

app = Flask(__name__)
PORT = 5050
FOLDER = os.path.dirname(os.path.abspath(__file__))
FFMPEG = "ffmpeg"

HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Video Merge Tool</title>
<style>
body{ font-family:Arial; background:#111; color:white; text-align:center; padding:20px;}
.box{ background:rgba(255,255,255,0.1); padding:20px; border-radius:15px; max-width:900px; margin:auto;}
button{ padding:10px 20px; border:none; border-radius:10px; background:#ff0055; color:white; font-weight:bold; cursor:pointer; margin-top:5px;}
.card{ background:#222; padding:10px; border-radius:10px; margin:10px;}
a{color:#00ff9d; text-decoration:none;}
</style>
</head>
<body>
<div class="box">
<h2>Python Video Merge Tool</h2>
{% if mergeable %}
    <h3>Mergeable Files:</h3>
    {% for v,a in mergeable %}
    <div class="card">
        Video: {{v}}<br>
        Audio: {{a}}<br>
        <button onclick="merge('{{v}}','{{a}}')">Merge Now</button>
    </div>
    {% endfor %}
{% else %}
    <p>No mergeable files found!</p>
{% endif %}
<p id="status"></p>
<script>
function merge(video,audio){
    fetch("/merge",{
        method:"POST",
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({video,audio})
    }).then(r=>r.json())
      .then(d=>document.getElementById("status").innerHTML=d.msg)
}
</script>
</div>
</body>
</html>
"""

def scan_files():
    files = os.listdir(FOLDER)
    videos = {}
    audios = {}
    for f in files:
        if f.endswith(".temp.webm"):  # ignore temp files
            continue
        name, ext = os.path.splitext(f)
        # remove .f12345a or .f12345v pattern from name
        name_clean = re.sub(r'\.f\d+[av]$', '', name)
        if ext.lower() in [".mp4",".webm",".mkv"]:
            videos[name_clean] = f
        if ext.lower() in [".m4a",".webm",".mp3"]:
            audios[name_clean] = f
    mergeable = []
    for n in videos:
        if n in audios:
            mergeable.append((videos[n], audios[n]))
    return mergeable

def merge_files(video,audio):
    output = os.path.splitext(video)[0] + "_merged.mp4"
    cmd = [FFMPEG, "-i", os.path.join(FOLDER,video), "-i", os.path.join(FOLDER,audio),
           "-c","copy","-y", os.path.join(FOLDER,output)]
    process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if process.returncode==0:
        return f"Merged successfully: {output}"
    else:
        return f"Merge failed for {video}"

@app.route("/")
def index():
    mergeable = scan_files()
    return render_template_string(HTML, mergeable=mergeable)

@app.route("/merge",methods=["POST"])
def merge_route():
    data = request.json
    msg = merge_files(data["video"],data["audio"])
    return jsonify({"msg":msg})

if __name__=="__main__":
    print(f"Server running on http://0.0.0.0:{PORT}")
    app.run(host="0.0.0.0",port=PORT)
