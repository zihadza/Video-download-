from flask import Flask, request, jsonify, render_template_string
import subprocess, json, urllib.parse
import urllib.request

app = Flask(__name__)

API_KEY = "AIzaSyBL4Cv5baQVtp5g0VrYWNd71UkjIylh8-s"

HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ultimate Downloader API</title>
<style>
body{font-family:'Segoe UI',sans-serif; background:#070a12; color:#eaf0ff; padding:20px; text-align:center;}
.container{max-width:500px; margin:0 auto; background:#12182a; padding:20px; border-radius:20px; box-shadow:0 10px 30px #0008;}
h2{color:#7c4dff; margin-bottom:5px;}
p{color:#9aa3bf; font-size:14px;}
input,select{width:100%; padding:14px; margin:8px 0; border-radius:12px; border:1px solid #333; background:#0e1324; color:white; box-sizing:border-box; outline:none;}
input:focus,select:focus{border-color:#7c4dff;}
button{width:100%; padding:14px; margin-top:10px; border-radius:12px; border:none; background:linear-gradient(135deg, #ff0055, #7c4dff); color:white; font-weight:bold; font-size:16px; cursor:pointer;}
button:active{transform:scale(0.98);}
#result{word-break:break-all; margin-top:20px; color:#00f5ff; font-size:13px; text-align:left; background:#0e1324; padding:15px; border-radius:12px; border:1px dashed #333;}
#error{color:#ff4d4d;}
</style>
</head>
<body>
<div class="container">
    <h2>Ultimate Downloader API</h2>
    <p>এই সার্ভারটি শুধু ডিরেক্ট লিংক জেনারেট করে। ডাউনলোড আপনার ফোনে হবে।</p>
    
    <input id="url" placeholder="Paste YouTube Link here...">
    <select id="quality">
        <option value="360">360p</option>
        <option value="720" selected>720p</option>
        <option value="1080">1080p</option>
    </select>
    <button onclick="getUrl()">Get Direct URL</button>
    
    <div id="result">Result will appear here...</div>
</div>

<script>
function getUrl() {
    const url = document.getElementById('url').value;
    const quality = document.getElementById('quality').value;
    const resDiv = document.getElementById('result');
    
    if (!url) {
        resDiv.innerHTML = '<span id="error">URL paste koro!</span>';
        return;
    }
    
    resDiv.innerHTML = 'Loading... (YouTube bot check bypass korar chesta hocche)';
    
    fetch('/geturl', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url: url, quality: quality, type: 'video'})
    })
    .then(r => r.json())
    .then(d => {
        if (d.error) {
            resDiv.innerHTML = '<span id="error">Error: ' + d.error + '</span>';
        } else {
            resDiv.innerHTML = '<b>Title:</b> ' + d.title + '<br><br><b>Direct URL:</b><br>' + d.video_url;
        }
    })
    .catch(e => {
        resDiv.innerHTML = '<span id="error">Fetch Error: ' + e.message + '</span>';
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
    data = request.json or {}
    query = data.get("query", "")
    pageToken = data.get("pageToken", "")
    encoded_query = urllib.parse.quote(query)
    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={encoded_query}&key={API_KEY}&maxResults=10&type=video"
    if pageToken:
        url += f"&pageToken={pageToken}"
    
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode())
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
        cmd = ["yt-dlp", "-j", "--no-playlist", "--extractor-args", "youtube:player_client=web_safari,android", url]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            return jsonify({"title": "Error", "channel": result.stderr[:200], "thumbnail": ""})
            
        j = json.loads(result.stdout)
        return jsonify({
            "title": j.get("title", ""),
            "channel": j.get("channel") or j.get("uploader", ""),
            "thumbnail": j.get("thumbnail", "")
        })
    except Exception as e:
        return jsonify({"title": "Error", "channel": str(e), "thumbnail": ""})

@app.route("/geturl", methods=["POST"])
def geturl():
    data = request.json or {}
    url = data.get("url", "")
    quality = data.get("quality", "720")
    typ = data.get("type", "video")

    if not url:
        return jsonify({"error": "URL missing"}), 400

    try:
        if typ == "audio":
            fmt = "bestaudio[ext=m4a]/bestaudio/best"
        else:
            fmt = f"best[height<={quality}][ext=mp4]/best[height<={quality}]/best"

        # --extractor-args flag ta YouTube er bot block bypass korte help kore
        # --no-check-certificate add kora hoyeche jate SSL error na ashe
        url_cmd = [
            "yt-dlp", 
            "-f", fmt, 
            "-g", 
            "--no-playlist", 
            "--no-check-certificate",
            "--extractor-args", "youtube:player_client=web_safari,android",
            url
        ]
        
        # subprocess.run use kora hoyeche jate asol error message gulo dhorte pari
        result = subprocess.run(url_cmd, capture_output=True, text=True, timeout=30)
        
        # Jodi command fail kore, tokhon asol error ta dekhabo
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown yt-dlp error"
            return jsonify({"error": error_msg.strip()}), 500
            
        direct_out = result.stdout.strip()
        urls = [u for u in direct_out.split("\n") if u.strip()]

        # Metadata ber kora (Title o Thumbnail er jonno)
        meta_cmd = ["yt-dlp", "-j", "--no-playlist", "--extractor-args", "youtube:player_client=web_safari,android", url]
        meta_result = subprocess.run(meta_cmd, capture_output=True, text=True, timeout=30)
        meta = json.loads(meta_result.stdout) if meta_result.returncode == 0 else {}

        return jsonify({
            "title": meta.get("title", ""),
            "thumbnail": meta.get("thumbnail", ""),
            "video_url": urls[0] if len(urls) > 0 else "",
            "audio_url": urls[1] if len(urls) > 1 else "",
            "ext": meta.get("ext", "mp4")
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8585, threaded=True)
