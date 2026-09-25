from flask import Flask, request, jsonify, render_template_string
import subprocess, json, urllib.parse

app = Flask(__name__)

API_KEY = "AIzaSyBL4Cv5baQVtp5g0VrYWNd71UkjIylh8-s"

HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ultimate Downloader Pro Max</title>
<style>
body{font-family:sans-serif; background:#070a12; color:white; padding:20px; text-align:center}
input,select{width:100%; padding:12px; margin:5px 0; border-radius:10px; border:1px solid #333; background:#12182a; color:white; box-sizing:border-box}
button{width:100%; padding:12px; margin:5px 0; border-radius:10px; border:none; background:#7c4dff; color:white; font-weight:bold}
</style>
</head>
<body>
<h2>Ultimate Downloader API</h2>
<p>এই সার্ভারটি শুধু ডিরেক্ট লিংক জেনারেট করে। ডাউনলোড আপনার ফোনে হবে।</p>
<input id="url" placeholder="YouTube Link">
<select id="quality">
    <option value="360">360p</option>
    <option value="720" selected>720p</option>
    <option value="1080">1080p</option>
</select>
<button onclick="getUrl()">Get Direct URL</button>
<p id="result" style="word-break:break-all; margin-top:20px; color:#00f5ff;"></p>

<script>
function getUrl() {
    const url = document.getElementById('url').value;
    const quality = document.getElementById('quality').value;
    if (!url) return alert('URL paste koro!');
    document.getElementById('result').innerText = 'Loading...';
    fetch('/geturl', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url: url, quality: quality, type: 'video'})
    })
    .then(r => r.json())
    .then(d => {
        if (d.error) document.getElementById('result').innerText = 'Error: ' + d.error;
        else document.getElementById('result').innerText = 'Direct URL: ' + d.video_url;
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

        # Get direct URL using -g flag
        url_cmd = ["yt-dlp", "-f", fmt, "-g", "--no-playlist", url]
        direct_out = subprocess.check_output(url_cmd, timeout=30).decode().strip()
        urls = [u for u in direct_out.split("\n") if u.strip()]

        # Get metadata for title and thumbnail
        meta_cmd = ["yt-dlp", "-j", "--no-playlist", "-f", fmt, url]
        meta_out = subprocess.check_output(meta_cmd, timeout=30).decode()
        meta = json.loads(meta_out)

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
