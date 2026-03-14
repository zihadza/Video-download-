from flask import Flask, request, render_template_string
import subprocess

app = Flask(__name__)

PORT = 3030
SAVE_PATH = "/storage/emulated/0/Zihad/%(title)s.webm"

HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>WebM Video Downloader</title>

<style>
body{
font-family:Arial;
background:#0f2027;
color:white;
text-align:center;
padding:20px;
}

.box{
background:#1e2a38;
padding:20px;
border-radius:10px;
max-width:400px;
margin:auto;
}

input,select,button{
width:100%;
padding:12px;
margin-top:10px;
border-radius:8px;
border:none;
font-size:16px;
}

button{
background:#ff0000;
color:white;
cursor:pointer;
}

pre{
text-align:left;
background:black;
padding:10px;
margin-top:15px;
overflow:auto;
max-height:250px;
}
</style>

</head>

<body>

<div class="box">
<h2>WebM Video Downloader</h2>

<form method="POST">

<input name="url" placeholder="Paste Video URL" required>

<select name="quality">
<option value="360">360p</option>
<option value="480">480p</option>
<option value="720">720p</option>
<option value="1080">1080p</option>
</select>

<button type="submit">Download WebM</button>

</form>

{% if log %}
<h3>Download Log</h3>
<pre>{{log}}</pre>
{% endif %}

</div>

</body>
</html>
"""

@app.route("/", methods=["GET","POST"])
def home():

    log=""

    if request.method=="POST":

        url=request.form["url"]
        quality=request.form["quality"]

        try:

            cmd=[
            "yt-dlp",
            "-f",f"best[ext=webm][height<={quality}]",
            "--no-part",
            "-o",SAVE_PATH,
            url
            ]

            result=subprocess.run(cmd,capture_output=True,text=True)

            log=result.stdout + result.stderr

        except Exception as e:

            log=str(e)

    return render_template_string(HTML,log=log)

if __name__ == "__main__":
    app.run(host="0.0.0.0",port=PORT)
