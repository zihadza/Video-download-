cat > server.py <<'PYEOF'
from flask import Flask, jsonify, request, send_file
from pathlib import Path
import json, re, subprocess, shutil, os, threading, time, uuid

app = Flask(__name__)

BASE_DIR = Path.home() / "Projects" / "ZihadIDE"
PROJECTS_DIR = BASE_DIR / "projects"
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

PORT = 3040
TERMUX_PREFIX = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
BUILDS = {}

LANGUAGES = {
    ".py":{"name":"Python","run":"python \"{file}\"","check":"python -m py_compile \"{file}\""},
    ".c":{"name":"C","run":"gcc \"{file}\" -o /tmp/zh_out && /tmp/zh_out","check":"gcc -fsyntax-only -Wall \"{file}\""},
    ".cpp":{"name":"C++","run":"g++ \"{file}\" -o /tmp/zh_out && /tmp/zh_out","check":"g++ -fsyntax-only -Wall \"{file}\""},
    ".cc":{"name":"C++","run":"g++ \"{file}\" -o /tmp/zh_out && /tmp/zh_out","check":"g++ -fsyntax-only -Wall \"{file}\""},
    ".php":{"name":"PHP","run":"php \"{file}\"","check":"php -l \"{file}\""},
    ".js":{"name":"JavaScript","run":"node \"{file}\"","check":"node --check \"{file}\""},
    ".go":{"name":"Go","run":"go run \"{file}\"","check":"gofmt -e \"{file}\""},
    ".rs":{"name":"Rust","run":"rustc \"{file}\" -o /tmp/zh_out && /tmp/zh_out","check":None},
    ".rb":{"name":"Ruby","run":"ruby \"{file}\"","check":"ruby -c \"{file}\""},
    ".pl":{"name":"Perl","run":"perl \"{file}\"","check":"perl -c \"{file}\""},
    ".sh":{"name":"Bash","run":"bash \"{file}\"","check":"bash -n \"{file}\""},
    ".java":{"name":"Java","run":"java \"{file}\"","check":None},
    ".kt":{"name":"Kotlin","run":None,"check":None},
    ".html":{"name":"HTML","run":None,"check":None},
    ".css":{"name":"CSS","run":None,"check":None},
    ".json":{"name":"JSON","run":None,"check":"python -c \"import json,sys; json.load(open(sys.argv[1]))\" \"{file}\""},
    ".xml":{"name":"XML","run":None,"check":"python -c \"import xml.etree.ElementTree as ET,sys; ET.parse(sys.argv[1])\" \"{file}\""},
    ".md":{"name":"Markdown","run":None,"check":None},
    ".txt":{"name":"Text","run":None,"check":None},
    ".gradle":{"name":"Gradle","run":None,"check":None},
    ".properties":{"name":"Properties","run":None,"check":None},
}

def valid_package(p):
    return re.match(r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$", p) is not None

def safe_project(name):
    if not name: return None
    p = (PROJECTS_DIR / name).resolve()
    try: p.relative_to(PROJECTS_DIR.resolve())
    except ValueError: return None
    return p

def safe_subpath(project, sub):
    if not sub: return project
    p = (project / sub).resolve()
    try: p.relative_to(project.resolve())
    except ValueError: return None
    return p

def write_file(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

def create_android_project(name, package, language):
    project = PROJECTS_DIR / name
    if project.exists(): raise ValueError("Project already exists")
    pkg_path = package.replace(".", "/")
    main_dir = project / "app" / "src" / "main"
    java_dir = main_dir / "java" / pkg_path
    kotlin_dir = main_dir / "kotlin" / pkg_path
    res_dir = main_dir / "res"
    values_dir = res_dir / "values"
    layout_dir = res_dir / "layout"
    mipmap_dir = res_dir / "mipmap-hdpi"
    for d in [java_dir, kotlin_dir, values_dir, layout_dir, mipmap_dir,
              res_dir / "drawable", main_dir / "assets", main_dir / "jniLibs"]:
        d.mkdir(parents=True, exist_ok=True)

    main_java = "package " + package + ";\n\nimport android.app.Activity;\nimport android.os.Bundle;\nimport android.widget.TextView;\n\npublic class MainActivity extends Activity {\n    @Override\n    protected void onCreate(Bundle savedInstanceState) {\n        super.onCreate(savedInstanceState);\n        TextView text = new TextView(this);\n        text.setText(\"Hello from " + name + "\");\n        text.setTextSize(24);\n        setContentView(text);\n    }\n}\n"

    main_kotlin = "package " + package + "\n\nimport android.app.Activity\nimport android.os.Bundle\nimport android.widget.TextView\n\nclass MainActivity : Activity() {\n    override fun onCreate(savedInstanceState: Bundle?) {\n        super.onCreate(savedInstanceState)\n        val text = TextView(this)\n        text.text = \"Hello from " + name + "\"\n        text.textSize = 24f\n        setContentView(text)\n    }\n}\n"

    manifest = '<?xml version="1.0" encoding="utf-8"?>\n<manifest xmlns:android="http://schemas.android.com/apk/res/android">\n    <uses-permission android:name="android.permission.INTERNET"/>\n    <application android:theme="@style/AppTheme" android:label="@string/app_name" android:allowBackup="true" android:supportsRtl="true">\n        <activity android:name="' + package + '.MainActivity" android:exported="true">\n            <intent-filter>\n                <action android:name="android.intent.action.MAIN"/>\n                <category android:name="android.intent.category.LAUNCHER"/>\n            </intent-filter>\n        </activity>\n    </application>\n</manifest>\n'

    layout = '<?xml version="1.0" encoding="utf-8"?>\n<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"\n    android:layout_width="match_parent" android:layout_height="match_parent"\n    android:gravity="center" android:orientation="vertical">\n    <TextView android:id="@+id/titleText"\n        android:layout_width="wrap_content" android:layout_height="wrap_content"\n        android:text="@string/app_name" android:textSize="24sp"/>\n</LinearLayout>\n'

    strings_xml = '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <string name="app_name">' + name + '</string>\n</resources>\n'
    colors_xml = '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="black">#000000</color>\n    <color name="white">#FFFFFF</color>\n    <color name="primary">#2563EB</color>\n    <color name="primary_dark">#1E40AF</color>\n</resources>\n'
    themes_xml = '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <style name="AppTheme" parent="android:style/Theme.Material.Light.NoActionBar">\n        <item name="android:fontFamily">sans</item>\n        <item name="android:colorAccent">#2563EB</item>\n        <item name="android:statusBarColor">@color/black</item>\n        <item name="android:navigationBarColor">@color/black</item>\n    </style>\n</resources>\n'
    ic_launcher = '<?xml version="1.0" encoding="utf-8"?>\n<layer-list xmlns:android="http://schemas.android.com/apk/res/android">\n    <item>\n        <shape android:shape="rectangle">\n            <solid android:color="#2563EB"/>\n        </shape>\n    </item>\n</layer-list>\n'

    settings_gradle = 'pluginManagement {\n    repositories {\n        google()\n        mavenCentral()\n        gradlePluginPortal()\n    }\n}\ndependencyResolutionManagement {\n    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)\n    repositories {\n        google()\n        mavenCentral()\n    }\n}\nrootProject.name = "' + name + '"\ninclude(":app")\n'
    root_gradle = "plugins {\n    id 'com.android.application' version '8.7.3' apply false\n}\n"
    app_gradle = 'plugins {\n    id "com.android.application"\n}\nandroid {\n    namespace "' + package + '"\n    compileSdk 34\n    defaultConfig {\n        applicationId "' + package + '"\n        minSdk 23\n        targetSdk 34\n        versionCode 1\n        versionName "1.0"\n    }\n    buildTypes {\n        release {\n            minifyEnabled false\n        }\n    }\n    compileOptions {\n        sourceCompatibility JavaVersion.VERSION_17\n        targetCompatibility JavaVersion.VERSION_17\n    }\n}\n'
    gradle_props = "org.gradle.jvmargs=-Xmx1536m -XX:MaxMetaspaceSize=512m\nandroid.useAndroidX=true\nandroid.nonTransitiveRClass=true\norg.gradle.caching=true\norg.gradle.parallel=true\n"

    aapt2_path = TERMUX_PREFIX + "/bin/aapt2"
    local_props = "sdk.dir=" + str(Path.home() / "android-sdk") + "\nandroid.aapt2FromMavenOverride=" + aapt2_path + "\n"

    project_info = {"name": name, "package": package, "language": language, "versionCode": 1, "versionName": "1.0"}

    write_file(java_dir / "MainActivity.java", main_java)
    write_file(kotlin_dir / "MainActivity.kt", main_kotlin)
    write_file(main_dir / "AndroidManifest.xml", manifest)
    write_file(layout_dir / "activity_main.xml", layout)
    write_file(values_dir / "strings.xml", strings_xml)
    write_file(values_dir / "colors.xml", colors_xml)
    write_file(values_dir / "themes.xml", themes_xml)
    write_file(mipmap_dir / "ic_launcher.xml", ic_launcher)
    write_file(project / "settings.gradle", settings_gradle)
    write_file(project / "build.gradle", root_gradle)
    write_file(project / "gradle.properties", gradle_props)
    write_file(project / "local.properties", local_props)
    write_file(project / "app" / "build.gradle", app_gradle)
    write_file(project / "project.json", json.dumps(project_info, indent=4))
    write_file(project / "hello.py", 'print("Hello from ' + name + '")\n')
    return project


HOME_HTML = """<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Zihad Mobile IDE</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#070b12;color:#fff;font-family:Arial,sans-serif}
header{padding:16px;background:#111827;border-bottom:1px solid #263244;display:flex;justify-content:space-between;align-items:center;gap:10px}
h1{font-size:20px;margin:0}
.container{padding:15px}
.card{background:#111827;border:1px solid #263244;border-radius:15px;padding:17px;margin-bottom:15px}
button{border:0;border-radius:9px;padding:10px 14px;margin:3px;background:#2563eb;color:white;font-weight:bold;cursor:pointer;font-size:13px}
.green{background:#16a34a}.red{background:#dc2626}.orange{background:#ea580c}.gray{background:#4b5563}
input,select{width:100%;padding:13px;margin:6px 0;border-radius:8px;border:1px solid #374151;background:#080f1c;color:white}
.project{background:#080f1c;border:1px solid #263244;border-radius:11px;padding:14px;margin:8px 0;display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap}
.project-info{flex:1;min-width:150px}
.project small{color:#94a3b8}
.status{color:#4ade80}.hidden{display:none}
#message{padding:10px;border-radius:8px;margin-top:8px;display:none}
</style>
</head>
<body>
<header>
<h1>⚡ Zihad Mobile IDE v8</h1>
<button class="green" onclick="showCreate()">+ New Project</button>
</header>
<div class="container">
<div class="card">
<h2>🖥️ System</h2>
<p class="status">● Termux Server Online</p>
<p id="status">Checking...</p>
</div>
<div class="card hidden" id="createBox">
<h2>📱 New Android Project</h2>
<input id="appName" placeholder="App Name (e.g. MyApp)">
<input id="packageName" placeholder="com.zihad.myapp">
<select id="language"><option value="java">Java</option><option value="kotlin">Kotlin</option></select>
<button class="green" onclick="createProject()">🚀 Create Project</button>
<button class="red" onclick="hideCreate()">Cancel</button>
<div id="message"></div>
</div>
<div class="card">
<h2>📂 Projects</h2>
<div id="projects">Loading...</div>
</div>
</div>
<script>
function showCreate(){document.getElementById("createBox").classList.remove("hidden");}
function hideCreate(){document.getElementById("createBox").classList.add("hidden");}
async function status(){try{var r=await fetch("/api/status");var d=await r.json();
document.getElementById("status").innerText="Port: "+d.port+" | Projects: "+d.projects+" | Languages: "+d.language_count;
}catch(e){document.getElementById("status").innerText="Server error";}}
async function loadProjects(){try{var r=await fetch("/api/projects");var d=await r.json();
var box=document.getElementById("projects");
if(d.projects.length===0){box.innerHTML="<p>No projects yet. Click + New Project.</p>";return;}
box.innerHTML="";
d.projects.forEach(function(p){var div=document.createElement("div");div.className="project";
var info=document.createElement("div");info.className="project-info";
info.innerHTML="<b>📱 "+esc(p.name)+"</b><br><small>"+esc(p.package)+"</small> &nbsp; <small>"+esc(p.language)+"</small>";
div.appendChild(info);
var g=document.createElement("div");
var o=document.createElement("button");o.className="green";o.innerText="Open";
o.onclick=function(){window.location="/project/"+encodeURIComponent(p.name);};g.appendChild(o);
var dl=document.createElement("button");dl.className="red";dl.innerText="🗑 Delete";
dl.onclick=function(){deleteProject(p.name);};g.appendChild(dl);
div.appendChild(g);box.appendChild(div);});
}catch(e){document.getElementById("projects").innerText="Load error: "+e;}}
async function createProject(){var n=document.getElementById("appName").value.trim();
var p=document.getElementById("packageName").value.trim();
var l=document.getElementById("language").value;
if(!n||!p){msg("Name and Package required.",1);return;}
try{var r=await fetch("/api/projects",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:n,package:p,language:l})});
var d=await r.json();
if(!r.ok){msg(d.error||"Failed",1);return;}
msg("✓ Project created!",0);
document.getElementById("appName").value="";document.getElementById("packageName").value="";
loadProjects();status();
}catch(e){msg("Error: "+e,1);}}
async function deleteProject(name){if(!confirm("Delete project '"+name+"'?")) return;
if(!confirm("Are you ABSOLUTELY sure?")) return;
try{var r=await fetch("/api/projects/"+encodeURIComponent(name),{method:"DELETE"});
var d=await r.json();
if(!r.ok){alert("Delete failed: "+(d.error||"?"));return;}
alert("✓ Deleted: "+name);loadProjects();status();
}catch(e){alert("Error: "+e);}}
function msg(t,e){var m=document.getElementById("message");m.style.display="block";m.innerText=t;m.style.background=e?"#7f1d1d":"#14532d";}
function esc(t){var d=document.createElement("div");d.innerText=t;return d.innerHTML;}
status();loadProjects();
</script>
</body>
</html>
"""


IDE_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__NAME__ - Zihad IDE</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/theme/dracula.min.css">
<style>
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:#070b12;color:#e2e8f0;font-family:-apple-system,Arial,sans-serif;font-size:14px}
header{padding:8px;background:#111827;border-bottom:1px solid #263244;display:flex;justify-content:space-between;align-items:center;gap:6px;flex-wrap:wrap}
header h2{margin:0;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;min-width:80px}
.btn{border:0;border-radius:6px;padding:7px 10px;margin:2px;background:#2563eb;color:white;font-weight:bold;font-size:12px;cursor:pointer}
.green{background:#16a34a}.red{background:#dc2626}.orange{background:#ea580c}.gray{background:#4b5563}.purple{background:#7c3aed}.yellow{background:#ca8a04}
.badge{display:inline-block;padding:3px 8px;border-radius:20px;font-size:11px;font-weight:bold;margin-left:4px}
.badge.err{background:#dc2626;color:#fff}.badge.ok{background:#16a34a;color:#fff}
.tab-bar{display:flex;background:#111827;border-bottom:1px solid #263244;overflow-x:auto}
.tab{padding:10px 14px;cursor:pointer;border-bottom:2px solid transparent;font-weight:bold;font-size:13px;white-space:nowrap}
.tab.active{border-bottom-color:#2563eb;color:#60a5fa}
.panel{padding:10px;display:none;height:calc(100vh - 90px);overflow-y:auto}
.panel.active{display:block}
.breadcrumb{background:#080f1c;padding:8px;border-radius:6px;margin-bottom:8px;font-size:12px;word-break:break-all;line-height:1.6}
.breadcrumb span{color:#60a5fa;cursor:pointer;text-decoration:underline}
.file-item{background:#111827;padding:10px;margin:4px 0;border-radius:6px;border:1px solid #263244;cursor:pointer;display:flex;align-items:center;gap:8px}
.file-item:hover{background:#1f2937}
.file-item .name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.file-item.folder .name{color:#fbbf24;font-weight:bold}
.file-item.file .name{color:#93c5fd}
.file-item .menu-btn{background:#374151;padding:4px 8px;font-size:14px;border-radius:4px;border:0;color:#fff;cursor:pointer}
.empty{color:#6b7280;text-align:center;padding:20px;font-style:italic}
.toolbar{display:flex;gap:6px;margin-bottom:10px;flex-wrap:wrap}
#editor-box{position:fixed;top:0;left:0;right:0;bottom:0;background:#070b12;z-index:100;display:none;flex-direction:column}
#editor-header{padding:6px;background:#111827;border-bottom:1px solid #263244;display:flex;justify-content:space-between;align-items:center;gap:5px;flex-wrap:wrap}
#editor-header .file-name{font-size:12px;color:#93c5fd;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:100px;font-family:monospace}
#editor-toolbar{padding:5px;background:#0b1220;border-bottom:1px solid #263244;display:flex;gap:4px;flex-wrap:wrap;align-items:center;font-size:11px}
#editor-toolbar button{background:#374151;color:#fff;border:0;border-radius:4px;padding:6px 10px;font-size:11px;cursor:pointer;font-weight:bold}
#editor-toolbar button:hover{background:#4b5563}
#editor-toolbar .info{color:#94a3b8;font-size:10px;margin-left:8px}
#editor-container{flex:1;overflow:hidden}
.CodeMirror{height:100%!important;font-size:13px;font-family:'Courier New',monospace}
.cm-error-line{background:rgba(220,38,38,0.18)!important}
#terminal-output{background:#000;color:#4ade80;padding:10px;border-radius:6px;min-height:200px;max-height:calc(100vh - 200px);overflow-y:auto;font-size:12px;white-space:pre-wrap;margin-bottom:8px;border:1px solid #1f2937;font-family:monospace;line-height:1.4}
#cmd-input{display:flex;gap:5px;position:sticky;bottom:0;background:#070b12;padding-top:5px}
#cmd-input input{flex:1;padding:10px;background:#080f1c;color:#e2e8f0;border:1px solid #374151;border-radius:6px;font-family:monospace;font-size:13px}
#cmd-input button{padding:10px 15px;background:#16a34a;color:white;border:0;border-radius:6px;font-weight:bold}
.info-bar{background:#080f1c;padding:8px;border-radius:6px;margin-bottom:8px;font-size:12px;border:1px solid #263244}
.output-box{background:#000;color:#4ade80;padding:10px;border-radius:6px;min-height:200px;white-space:pre-wrap;font-family:monospace;font-size:12px;line-height:1.4;border:1px solid #1f2937;margin-bottom:10px;max-height:calc(100vh - 320px);overflow-y:auto}
.err-item{background:#7f1d1d;color:#fee2e2;padding:10px;border-radius:6px;margin:5px 0;cursor:pointer;border-left:4px solid #dc2626;font-family:monospace;font-size:12px}
.err-item:hover{background:#991b1b}
.err-item .loc{color:#fbbf24;font-weight:bold}
.err-item .msg-line{color:#fecaca;margin-top:4px}
.err-item .code-line{background:#450a0a;padding:4px 6px;border-radius:3px;margin-top:4px;font-size:11px;color:#fca5a5;font-family:monospace;overflow-x:auto;white-space:pre}
.build-panel{background:#0b1220;border:1px solid #1f2937;border-radius:10px;padding:14px;margin-bottom:12px}
.build-panel h3{margin:0 0 10px 0;font-size:15px;color:#60a5fa}
.progress-wrap{background:#1f2937;border-radius:20px;height:26px;overflow:hidden;position:relative;margin:10px 0}
.progress-bar{height:100%;background:linear-gradient(90deg,#2563eb,#7c3aed,#2563eb);background-size:200% 100%;animation:shine 2s linear infinite;transition:width 0.4s;width:0%}
@keyframes shine{0%{background-position:0% 50%}100%{background-position:200% 50%}}
.progress-text{position:absolute;top:0;left:0;right:0;bottom:0;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:bold;color:#fff;text-shadow:0 1px 2px rgba(0,0,0,0.8)}
.build-stats{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:10px 0}
.stat-box{background:#111827;padding:10px;border-radius:8px;text-align:center;border:1px solid #1f2937}
.stat-label{font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px}
.stat-value{font-size:16px;font-weight:bold;color:#60a5fa;font-family:monospace}
.current-task{background:#080f1c;padding:10px;border-radius:6px;font-family:monospace;font-size:12px;color:#fbbf24;margin:10px 0;border-left:3px solid #fbbf24;word-break:break-all;min-height:20px}
.build-status-msg{font-size:13px;color:#94a3b8;text-align:center;margin-top:6px}
.build-status-msg.success{color:#4ade80;font-weight:bold}
.build-status-msg.error{color:#f87171;font-weight:bold}
.spinner{display:inline-block;width:14px;height:14px;border:2px solid #60a5fa;border-top-color:transparent;border-radius:50%;animation:spin 0.8s linear infinite;margin-right:6px;vertical-align:middle}
@keyframes spin{to{transform:rotate(360deg)}}
</style>
</head>
<body>
<header>
  <h2>📱 __NAME__</h2>
  <div>
    <button class="btn yellow" onclick="scanAllErrors()" id="scanBtn">🔍 Scan</button>
    <button class="btn purple" onclick="runCurrent()" id="runBtn" style="display:none">▶ Run</button>
    <button class="btn orange" onclick="buildApk()" id="buildBtn">🔨 Build</button>
    <button class="btn gray" onclick="window.location='/'">🏠</button>
  </div>
</header>

<div class="tab-bar">
  <div class="tab active" onclick="switchTab('explorer', this)">📂 Explorer <span id="tabErrBadge" class="badge ok">0</span></div>
  <div class="tab" onclick="switchTab('errors', this)">⚠️ Errors <span id="errBadge" class="badge ok">0</span></div>
  <div class="tab" onclick="switchTab('terminal', this)">💻 Terminal</div>
  <div class="tab" onclick="switchTab('output', this)">📊 Output</div>
  <div class="tab" onclick="switchTab('build', this)">🔨 Build</div>
</div>

<div class="panel active" id="panel-explorer">
  <div class="toolbar">
    <button class="btn green" onclick="newFile()">📄 + File</button>
    <button class="btn orange" onclick="newFolder()">📁 + Folder</button>
    <button class="btn gray" onclick="loadFiles(currentPath)">🔄 Refresh</button>
  </div>
  <div class="breadcrumb" id="breadcrumb">Loading...</div>
  <div id="file-list">Loading...</div>
</div>

<div class="panel" id="panel-errors">
  <div class="info-bar" id="errInfo">Press 🔍 Scan to check all files.</div>
  <div id="err-list"></div>
</div>

<div class="panel" id="panel-terminal">
  <div id="terminal-output">$ Zihad IDE v8 Terminal — Ready
</div>
  <div id="cmd-input">
    <input id="cmd" placeholder="ls, pwd, gradle -v..." onkeydown="if(event.key==='Enter') runCmd()">
    <button onclick="runCmd()">Run</button>
  </div>
</div>

<div class="panel" id="panel-output">
  <div class="info-bar" id="run-info">No code executed yet.</div>
  <div class="output-box" id="output-box">Output will appear here...</div>
</div>

<div class="panel" id="panel-build">
  <div class="build-panel">
    <h3>🔨 APK Build Progress</h3>
    <div class="progress-wrap">
      <div class="progress-bar" id="buildProgressBar"></div>
      <div class="progress-text" id="buildProgressText">0%</div>
    </div>
    <div class="build-stats">
      <div class="stat-box"><div class="stat-label">Tasks</div><div class="stat-value" id="statTasks">0/0</div></div>
      <div class="stat-box"><div class="stat-label">Elapsed</div><div class="stat-value" id="statElapsed">0s</div></div>
      <div class="stat-box"><div class="stat-label">Remaining</div><div class="stat-value" id="statEta">--</div></div>
    </div>
    <div class="current-task" id="currentTask">Press 🔨 Build to start...</div>
    <div class="build-status-msg" id="buildStatusMsg">Ready</div>
    <div id="apk-box" style="display:none;margin-top:10px">
      <button class="btn green" id="apkDownloadBtn" style="width:100%;padding:15px;font-size:15px">⬇ Download APK</button>
    </div>
  </div>
  <div class="info-bar">Live Build Log</div>
  <div class="output-box" id="buildLog">$ Waiting for build...</div>
</div>

<div id="editor-box">
  <div id="editor-header">
    <span class="file-name" id="editor-filename">file.txt</span>
    <span id="editor-err-badge" class="badge ok">0</span>
    <div>
      <button class="btn green" onclick="saveFile()">💾</button>
      <button class="btn yellow" onclick="checkCurrentFile()">🔍</button>
      <button class="btn purple" onclick="runCurrent()">▶</button>
      <button class="btn orange" onclick="renameCurrent()">✏️</button>
      <button class="btn red" onclick="deleteCurrent()">🗑️</button>
      <button class="btn gray" onclick="closeEditor()">✖</button>
    </div>
  </div>
  <div id="editor-toolbar">
    <button onclick="doSelectAll()">📋 Select All</button>
    <button onclick="doCut()">✂️ Cut</button>
    <button onclick="doCopy()">📄 Copy</button>
    <button onclick="doPaste()">📥 Paste</button>
    <button onclick="doUndo()">↶ Undo</button>
    <button onclick="doRedo()">↷ Redo</button>
    <button onclick="doFind()">🔎 Find</button>
    <button onclick="doIndent()">⇥ Indent</button>
    <span class="info">Ctrl+A/C/X/V কাজ করে</span>
  </div>
  <div id="editor-container"><textarea id="editor"></textarea></div>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/edit/matchbrackets.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/edit/closebrackets.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/search/search.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/search/searchcursor.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/search/jump-to-line.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/dialog/dialog.min.js"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/dialog/dialog.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/python/python.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/clike/clike.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/php/php.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/javascript/javascript.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/go/go.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/rust/rust.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/ruby/ruby.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/perl/perl.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/shell/shell.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/xml/xml.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/css/css.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/htmlmixed/htmlmixed.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/markdown/markdown.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/properties/properties.min.js"></script>
<script>
var PROJECT = "__NAME__";
var currentPath = "";
var currentFile = "";
var cm = null;
var errorLines = [];
var buildPollTimer = null;
var buildStartTime = 0;
var elapsedTimer = null;
var tasksSeen = 0;
var EST_TOTAL = 32;
var buildId = null;
var lastLineIdx = 0;

function switchTab(id, el){
  document.querySelectorAll(".tab").forEach(function(t){t.classList.remove("active");});
  document.querySelectorAll(".panel").forEach(function(p){p.classList.remove("active");});
  el.classList.add("active");
  document.getElementById("panel-"+id).classList.add("active");
  if(cm) setTimeout(function(){cm.refresh();}, 50);
}
function getMode(filename){
  var ext = filename.split(".").pop().toLowerCase();
  var map = {py:"python",c:"text/x-csrc",h:"text/x-csrc",cpp:"text/x-c++src",cc:"text/x-c++src",
    java:"text/x-java",kt:"text/x-kotlin",php:"application/x-httpd-php",js:"javascript",
    go:"text/x-go",rs:"text/x-rustsrc",rb:"text/x-ruby",pl:"text/x-perl",sh:"text/x-sh",
    html:"htmlmixed",css:"css",xml:"xml",json:"application/json",md:"markdown",
    gradle:"text/x-groovy",properties:"text/x-properties"};
  return map[ext] || "null";
}
async function loadFiles(path){
  currentPath = path || "";
  var box = document.getElementById("file-list");
  var bc = document.getElementById("breadcrumb");
  box.innerHTML = "Loading...";
  try{
    var r = await fetch("/api/project-files/"+encodeURIComponent(PROJECT)+"?path="+encodeURIComponent(currentPath));
    var d = await r.json();
    if(!r.ok){ box.innerHTML = "<div class='empty'>Error: "+(d.error||"?")+"</div>"; return; }
    var parts = currentPath ? currentPath.split("/") : [];
    var bcHtml = "<span onclick='loadFiles(\\"\\")'>📁 "+PROJECT+"</span>";
    var acc = "";
    parts.forEach(function(p){
      acc += (acc?"/":"") + p;
      var t = acc;
      bcHtml += " / <span onclick='loadFiles(\\""+t+"\\")'>"+p+"</span>";
    });
    bc.innerHTML = bcHtml;
    if(d.files.length === 0){ box.innerHTML = "<div class='empty'>Empty folder</div>"; return; }
    box.innerHTML = "";
    if(currentPath){
      var upPath = parts.slice(0, -1).join("/");
      var upDiv = document.createElement("div");
      upDiv.className = "file-item folder";
      upDiv.innerHTML = "<span>⬆️</span><span class='name'>.. (up)</span>";
      upDiv.onclick = function(){ loadFiles(upPath); };
      box.appendChild(upDiv);
    }
    d.files.forEach(function(f){
      var div = document.createElement("div");
      div.className = "file-item " + (f.type === "directory" ? "folder" : "file");
      var icon = f.type === "directory" ? "📁" : "📄";
      div.innerHTML = "<span>"+icon+"</span><span class='name'>"+esc(f.name)+"</span><button class='menu-btn'>⋮</button>";
      var mb = div.querySelector(".menu-btn");
      mb.onclick = function(e){ e.stopPropagation(); showItemMenu(f); };
      div.onclick = function(){
        if(f.type === "directory") loadFiles(f.path);
        else openFile(f.path);
      };
      box.appendChild(div);
    });
  }catch(e){ box.innerHTML = "<div class='empty'>Error: "+e+"</div>"; }
}
function showItemMenu(f){
  var c = prompt("Action for: "+f.name+"\\n\\n1=Open 2=Rename 3=Delete 4=Check");
  if(c==="1"){ if(f.type==="directory") loadFiles(f.path); else openFile(f.path); }
  else if(c==="2"){ var nn=prompt("New name:", f.name); if(nn&&nn!==f.name) fileOp("rename", f.path, nn); }
  else if(c==="3"){ if(confirm("Delete '"+f.name+"'?")) fileOp("delete", f.path); }
  else if(c==="4"){ if(f.type==="file") checkFileErrors(f.path, true); }
}
async function newFile(){
  var n = prompt("New file name (e.g. main.py):");
  if(!n) return;
  var fp = currentPath ? (currentPath+"/"+n) : n;
  var c = prompt("Initial content (optional):", "") || "";
  fileOp("create-file", fp, null, c);
}
async function newFolder(){
  var n = prompt("New folder name:");
  if(!n) return;
  var fp = currentPath ? (currentPath+"/"+n) : n;
  fileOp("create-folder", fp);
}
async function fileOp(action, path, newName, content){
  try{
    var body = {project: PROJECT, action: action, path: path};
    if(newName) body.newName = newName;
    if(content !== undefined) body.content = content;
    var r = await fetch("/api/file-operation", {
      method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body)
    });
    var d = await r.json();
    if(!r.ok){ alert("Error: "+(d.error||"?")); return; }
    loadFiles(currentPath);
  }catch(e){ alert("Error: "+e); }
}
async function openFile(path){
  currentFile = path; errorLines = [];
  try{
    var r = await fetch("/api/file-content/"+encodeURIComponent(PROJECT)+"?path="+encodeURIComponent(path));
    var d = await r.json();
    if(!r.ok){ alert("Error: "+(d.error||"?")); return; }
    document.getElementById("editor-filename").innerText = path;
    document.getElementById("editor-err-badge").innerText = "0";
    document.getElementById("editor-err-badge").className = "badge ok";
    document.getElementById("editor-box").style.display = "flex";
    var ext = path.split(".").pop().toLowerCase();
    var rExt = ["py","c","cpp","cc","php","js","go","rs","rb","sh","java"];
    if(rExt.indexOf(ext) !== -1) document.getElementById("runBtn").style.display = "inline-block";
    else document.getElementById("runBtn").style.display = "none";
    if(cm){ cm.toTextArea(); cm = null; }
    cm = CodeMirror.fromTextArea(document.getElementById("editor"), {
      lineNumbers: true, mode: getMode(path), theme: "dracula",
      matchBrackets: true, autoCloseBrackets: true,
      indentUnit: 4, tabSize: 4, lineWrapping: true
    });
    cm.setValue(d.content);
    setTimeout(function(){ cm.refresh(); }, 100);
    setTimeout(function(){ checkCurrentFile(); }, 400);
  }catch(e){ alert("Error: "+e); }
}
function closeEditor(){
  document.getElementById("editor-box").style.display = "none";
  document.getElementById("runBtn").style.display = "none";
  currentFile = "";
  if(cm){ cm.toTextArea(); cm = null; }
}

// ===== Editor toolbar actions =====
function doSelectAll(){ if(cm){ cm.execCommand("selectAll"); cm.focus(); } }
async function doCut(){
  if(!cm) return;
  cm.focus();
  var sel = cm.getSelection();
  if(!sel){ alert("Select something first (tap Select All)"); return; }
  try{
    await navigator.clipboard.writeText(sel);
    cm.replaceSelection("");
    alert("Cut! (" + sel.length + " chars)");
  }catch(e){
    alert("Cut error: " + e);
  }
}
async function doCopy(){
  if(!cm) return;
  cm.focus();
  var sel = cm.getSelection();
  if(!sel){ alert("Select something first"); return; }
  try{
    await navigator.clipboard.writeText(sel);
    alert("Copied! (" + sel.length + " chars)");
  }catch(e){
    // Fallback: use execCommand
    var ta = document.createElement("textarea");
    ta.value = sel;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
    alert("Copied (fallback)!");
  }
}
async function doPaste(){
  if(!cm) return;
  cm.focus();
  try{
    var txt = await navigator.clipboard.readText();
    cm.replaceSelection(txt);
  }catch(e){
    alert("Paste from browser blocked. Long-press on editor and paste manually.\\n\\nError: " + e);
  }
}
function doUndo(){ if(cm){ cm.focus(); cm.undo(); } }
function doRedo(){ if(cm){ cm.focus(); cm.redo(); } }
function doFind(){ if(cm){ cm.execCommand("find"); } }
function doIndent(){
  if(!cm) return;
  var sel = cm.getSelection();
  if(!sel){ cm.execCommand("indentMore"); return; }
  var lines = sel.split("\\n");
  var indented = lines.map(function(l){ return "    " + l; }).join("\\n");
  cm.replaceSelection(indented);
}

async function saveFile(){
  if(!currentFile || !cm) return;
  try{
    var r = await fetch("/api/file-content/"+encodeURIComponent(PROJECT)+"?path="+encodeURIComponent(currentFile), {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({content: cm.getValue()})
    });
    var d = await r.json();
    if(!r.ok){ alert("Save error: "+(d.error||"?")); return; }
    var el = document.getElementById("editor-filename");
    var old = el.innerText;
    el.innerText = "✓ Saved";
    setTimeout(function(){ el.innerText = old; }, 1000);
    setTimeout(function(){ checkCurrentFile(); }, 300);
  }catch(e){ alert("Save error: "+e); }
}
function renameCurrent(){
  if(!currentFile) return;
  var parts = currentFile.split("/");
  var oldName = parts[parts.length-1];
  var nn = prompt("Rename to:", oldName);
  if(!nn || nn === oldName) return;
  parts[parts.length-1] = nn;
  fileOp("rename", currentFile, parts.join("/"));
  closeEditor();
}
function deleteCurrent(){
  if(!currentFile) return;
  if(!confirm("Delete '"+currentFile+"'?")) return;
  fileOp("delete", currentFile);
  closeEditor();
}
async function checkCurrentFile(){
  if(!currentFile || !cm) return;
  await saveFile();
  var result = await checkFileErrors(currentFile, false);
  if(!result) return;
  errorLines.forEach(function(line){
    if(cm && cm.getLineHandle(line-1))
      cm.removeLineClass(cm.getLineHandle(line-1), "background", "cm-error-line");
  });
  errorLines = [];
  var badge = document.getElementById("editor-err-badge");
  if(result.errors.length === 0){
    badge.innerText = "0 ✓"; badge.className = "badge ok";
  } else {
    badge.innerText = result.errors.length + " err"; badge.className = "badge err";
    result.errors.forEach(function(e){
      if(e.line && cm){
        var h = cm.getLineHandle(e.line - 1);
        if(h){ cm.addLineClass(h, "background", "cm-error-line"); errorLines.push(e.line); }
      }
    });
  }
}
async function checkFileErrors(path, showAlert){
  try{
    var r = await fetch("/api/check-file/"+encodeURIComponent(PROJECT)+"?path="+encodeURIComponent(path));
    var d = await r.json();
    if(!r.ok){ if(showAlert) alert("Check failed"); return {errors: []}; }
    if(showAlert){
      if(d.errors.length === 0) alert("✓ No errors in "+path);
      else alert(d.errors.length+" error(s) in "+path);
    }
    return d;
  }catch(e){ if(showAlert) alert("Error: "+e); return {errors: []}; }
}
async function scanAllErrors(){
  var btn = document.getElementById("scanBtn");
  btn.innerText = "⏳ ...";
  document.getElementById("errInfo").innerText = "Scanning...";
  document.getElementById("err-list").innerHTML = "";
  try{
    var r = await fetch("/api/scan-errors/"+encodeURIComponent(PROJECT));
    var d = await r.json();
    if(!r.ok){ document.getElementById("errInfo").innerText = "Scan failed"; btn.innerText = "🔍 Scan"; return; }
    var total = 0, badFiles = 0;
    var box = document.getElementById("err-list");
    d.results.forEach(function(f){
      if(f.errors && f.errors.length > 0){
        total += f.errors.length; badFiles++;
        var fh = document.createElement("div");
        fh.style.cssText = "color:#fbbf24;font-weight:bold;margin-top:10px;font-size:13px";
        fh.innerText = "📄 " + f.path + " — " + f.errors.length + " error(s)";
        box.appendChild(fh);
        f.errors.forEach(function(e){
          var item = document.createElement("div");
          item.className = "err-item";
          var html = "<div class='loc'>Line "+e.line+", Col "+(e.col||1)+"</div>";
          html += "<div class='msg-line'>"+esc(e.message)+"</div>";
          if(e.code){ html += "<div class='code-line'>"+esc(e.code)+"</div>"; }
          item.innerHTML = html;
          item.onclick = function(){ jumpToError(f.path, e.line); };
          box.appendChild(item);
        });
      }
    });
    var badge = document.getElementById("errBadge");
    var tabBadge = document.getElementById("tabErrBadge");
    if(total === 0){
      badge.innerText = "0 ✓"; badge.className = "badge ok";
      tabBadge.innerText = "0"; tabBadge.className = "badge ok";
      document.getElementById("errInfo").innerText = "✓ No errors found in " + d.scanned + " files.";
    } else {
      badge.innerText = total + " errors"; badge.className = "badge err";
      tabBadge.innerText = total; tabBadge.className = "badge err";
      document.getElementById("errInfo").innerText = badFiles + " file(s) with " + total + " error(s).";
    }
    btn.innerText = "🔍 Scan";
  }catch(e){ document.getElementById("errInfo").innerText = "Error: " + e; btn.innerText = "🔍 Scan"; }
}
async function jumpToError(path, line){
  document.getElementById("editor-box").style.display = "none";
  await openFile(path);
  setTimeout(function(){
    if(cm && line){
      cm.setCursor({line: line-1, ch: 0});
      cm.focus();
      var coords = cm.charCoords({line: line-1, ch: 0}, "local");
      cm.scrollTo(null, coords.top - 100);
    }
  }, 500);
}
async function runCmd(){
  var cmd = document.getElementById("cmd").value.trim();
  if(!cmd) return;
  var out = document.getElementById("terminal-output");
  out.innerText += "\\n$ " + cmd + "\\n";
  document.getElementById("cmd").value = "";
  out.scrollTop = out.scrollHeight;
  try{
    var r = await fetch("/api/run-command", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({project: PROJECT, cmd: cmd})
    });
    var d = await r.json();
    if(d.stdout) out.innerText += d.stdout;
    if(d.stderr) out.innerText += "\\n[stderr]\\n" + d.stderr;
    if(d.error) out.innerText += "\\n[error] " + d.error;
    out.innerText += "\\n[exit " + (d.returncode !== undefined ? d.returncode : "?") + "]\\n";
    out.scrollTop = out.scrollHeight;
  }catch(e){ out.innerText += "\\n[error] " + e + "\\n"; }
}
async function runCurrent(){
  if(!currentFile){ alert("Open a file first."); return; }
  if(cm) await saveFile();
  switchTab("output", document.querySelectorAll(".tab")[3]);
  var outBox = document.getElementById("output-box");
  outBox.innerText = "Running " + currentFile + "...\\n\\n";
  try{
    var r = await fetch("/api/run-code", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({project: PROJECT, path: currentFile})
    });
    var d = await r.json();
    document.getElementById("run-info").innerHTML = "<b>File:</b> "+esc(currentFile)+" | <b>Lang:</b> "+esc(d.language||"?")+" | <b>Exit:</b> "+(d.returncode!==undefined?d.returncode:"?");
    var text = "";
    if(d.command) text += "$ " + d.command + "\\n\\n";
    if(d.stdout) text += d.stdout;
    if(d.stderr) text += "\\n[stderr]\\n" + d.stderr;
    if(d.error) text += "\\n[error] " + d.error;
    if(!text) text = "(no output)";
    outBox.innerText = text;
  }catch(e){ outBox.innerText = "[error] " + e; }
}
function formatTime(sec){
  sec = Math.floor(sec);
  if(sec < 60) return sec + "s";
  return Math.floor(sec/60) + "m " + (sec % 60) + "s";
}
function startElapsedTimer(){
  if(elapsedTimer) clearInterval(elapsedTimer);
  elapsedTimer = setInterval(function(){
    var el = (Date.now() - buildStartTime) / 1000;
    document.getElementById("statElapsed").innerText = formatTime(el);
    var ratio = tasksSeen / EST_TOTAL;
    if(ratio > 0.05){
      var total = el / ratio;
      var rem = Math.max(0, total - el);
      document.getElementById("statEta").innerText = formatTime(rem);
    } else {
      document.getElementById("statEta").innerText = "--";
    }
  }, 500);
}
function processBuildLine(line){
  var log = document.getElementById("buildLog");
  log.innerText += "\\n" + line;
  log.scrollTop = log.scrollHeight;
  var m = line.match(/^>\\s+Task\\s+(:[\\w:]+)/);
  if(m){
    tasksSeen++;
    document.getElementById("statTasks").innerText = tasksSeen + "/" + EST_TOTAL;
    document.getElementById("currentTask").innerText = "▶ " + m[1];
    var pct = Math.min(95, Math.round((tasksSeen / EST_TOTAL) * 100));
    document.getElementById("buildProgressBar").style.width = pct + "%";
    document.getElementById("buildProgressText").innerText = pct + "%";
  }
  var m2 = line.match(/(\\d+)\\s+actionable tasks/);
  if(m2){
    EST_TOTAL = parseInt(m2[1]);
    document.getElementById("statTasks").innerText = tasksSeen + "/" + EST_TOTAL;
  }
  if(line.indexOf("BUILD SUCCESSFUL") !== -1){
    document.getElementById("buildProgressBar").style.width = "100%";
    document.getElementById("buildProgressText").innerText = "100%";
    document.getElementById("currentTask").innerText = "✅ Build complete";
    var s = document.getElementById("buildStatusMsg");
    s.innerText = line; s.className = "build-status-msg success";
  }
  if(line.indexOf("BUILD FAILED") !== -1){
    var s2 = document.getElementById("buildStatusMsg");
    s2.innerText = line; s2.className = "build-status-msg error";
    document.getElementById("currentTask").innerText = "❌ Build failed";
  }
}
async function pollBuild(){
  if(!buildId) return;
  try{
    var r = await fetch("/api/build-poll/" + buildId + "?since=" + lastLineIdx);
    var d = await r.json();
    if(d.lines && d.lines.length > 0){
      d.lines.forEach(function(line){ processBuildLine(line); });
      lastLineIdx = d.total;
    }
    if(d.status === "done"){
      clearInterval(buildPollTimer); buildPollTimer = null;
      if(elapsedTimer){ clearInterval(elapsedTimer); elapsedTimer = null; }
      if(d.success && d.apk_path){
        document.getElementById("buildProgressBar").style.width = "100%";
        document.getElementById("buildProgressText").innerText = "100%";
        document.getElementById("currentTask").innerText = "✅ Build successful";
        var s = document.getElementById("buildStatusMsg");
        s.innerText = "✓ APK ready!"; s.className = "build-status-msg success";
        document.getElementById("apk-box").style.display = "block";
        document.getElementById("apkDownloadBtn").onclick = function(){
          window.location = "/api/download-apk/" + encodeURIComponent(PROJECT);
        };
      } else {
        document.getElementById("currentTask").innerText = "❌ Build failed";
        var s2 = document.getElementById("buildStatusMsg");
        s2.innerText = "✗ Build failed (exit " + (d.returncode || "?") + ")";
        s2.className = "build-status-msg error";
      }
    }
  }catch(e){}
}
async function buildApk(){
  if(!confirm("Build APK?\\n\\nFirst build: 1-3 min.\\nNext builds: 20-40 sec.")) return;
  switchTab("build", document.querySelectorAll(".tab")[4]);
  document.getElementById("buildLog").innerText = "$ Starting build...";
  document.getElementById("buildProgressBar").style.width = "0%";
  document.getElementById("buildProgressText").innerText = "0%";
  document.getElementById("statTasks").innerText = "0/32";
  document.getElementById("statElapsed").innerText = "0s";
  document.getElementById("statEta").innerText = "--";
  document.getElementById("currentTask").innerHTML = "<span class='spinner'></span>Starting...";
  var st = document.getElementById("buildStatusMsg");
  st.innerText = "Starting build..."; st.className = "build-status-msg";
  document.getElementById("apk-box").style.display = "none";
  tasksSeen = 0; lastLineIdx = 0; EST_TOTAL = 32;
  try{
    var r = await fetch("/api/build-start", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({project: PROJECT})
    });
    var d = await r.json();
    if(!r.ok){ alert("Error: "+(d.error||"?")); return; }
    buildId = d.build_id;
    buildStartTime = Date.now();
    startElapsedTimer();
    if(buildPollTimer) clearInterval(buildPollTimer);
    buildPollTimer = setInterval(pollBuild, 700);
    pollBuild();
  }catch(e){ alert("Error: " + e); }
}
function esc(t){ var d = document.createElement("div"); d.innerText = t; return d.innerHTML; }
loadFiles("");
setTimeout(function(){ scanAllErrors(); }, 1000);
</script>
</body>
</html>
"""


@app.route("/")
def home(): return HOME_HTML

@app.route("/api/status")
def api_status():
    projects = [p for p in PROJECTS_DIR.iterdir() if p.is_dir()]
    langs = set(v["name"] for v in LANGUAGES.values())
    return jsonify({"server":"online","port":PORT,"projects":len(projects),"language_count":len(langs)})

@app.route("/api/projects", methods=["GET"])
def get_projects():
    result = []
    for project in sorted(PROJECTS_DIR.iterdir()):
        if not project.is_dir(): continue
        info_file = project / "project.json"
        if info_file.exists():
            try: info = json.loads(info_file.read_text(encoding="utf-8"))
            except Exception: info = {"name": project.name, "package":"?","language":"?"}
        else: info = {"name": project.name, "package":"?","language":"?"}
        result.append(info)
    return jsonify({"projects": result})

@app.route("/api/projects", methods=["POST"])
def create_project_api():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name","")).strip()
    package = str(data.get("package","")).strip()
    language = str(data.get("language","java")).strip().lower()
    if not name: return jsonify({"error":"Name required"}), 400
    if not package: return jsonify({"error":"Package required"}), 400
    if not valid_package(package): return jsonify({"error":"Invalid package"}), 400
    if language not in ["java","kotlin"]: return jsonify({"error":"Invalid language"}), 400
    try:
        p = create_android_project(name, package, language)
        return jsonify({"success":True,"path":str(p)})
    except Exception as e:
        return jsonify({"error":str(e)}), 400

@app.route("/api/projects/<path:name>", methods=["DELETE"])
def delete_project(name):
    project = safe_project(name)
    if project is None: return jsonify({"error":"Invalid"}), 400
    if not project.exists(): return jsonify({"error":"Not found"}), 404
    if project == PROJECTS_DIR: return jsonify({"error":"Cannot delete root"}), 400
    try:
        shutil.rmtree(str(project))
        return jsonify({"success":True})
    except Exception as e:
        return jsonify({"error":str(e)}), 500

@app.route("/project/<path:name>")
def open_project(name):
    project = safe_project(name)
    if project is None or not project.exists():
        return "Project not found", 404
    return IDE_HTML.replace("__NAME__", project.name)

@app.route("/api/project-files/<path:name>")
def project_files(name):
    project = safe_project(name)
    if project is None or not project.exists():
        return jsonify({"error":"Invalid"}), 400
    sub = request.args.get("path","")
    target = safe_subpath(project, sub)
    if target is None or not target.is_dir():
        return jsonify({"error":"Invalid path"}), 400
    files = []
    try:
        for p in sorted(target.iterdir(), key=lambda x:(not x.is_dir(), x.name.lower())):
            try: rel = str(p.relative_to(project))
            except ValueError: continue
            files.append({"name":p.name,"path":rel,"type":"directory" if p.is_dir() else "file"})
    except Exception as e:
        return jsonify({"error":str(e)}), 500
    return jsonify({"project":name,"current":sub,"files":files})

@app.route("/api/file-content/<path:name>", methods=["GET","POST"])
def file_content(name):
    project = safe_project(name)
    if project is None or not project.exists():
        return jsonify({"error":"Invalid"}), 400
    sub = request.args.get("path","")
    target = safe_subpath(project, sub)
    if target is None or not target.is_file():
        return jsonify({"error":"Not found"}), 404
    if request.method == "GET":
        try:
            return jsonify({"content":target.read_text(encoding="utf-8",errors="replace"),"path":sub})
        except Exception as e:
            return jsonify({"error":str(e)}), 500
    data = request.get_json(silent=True) or {}
    try:
        target.write_text(data.get("content",""), encoding="utf-8")
        return jsonify({"success":True})
    except Exception as e:
        return jsonify({"error":str(e)}), 500

@app.route("/api/file-operation", methods=["POST"])
def file_operation():
    data = request.get_json(silent=True) or {}
    project = safe_project(data.get("project",""))
    if project is None or not project.exists():
        return jsonify({"error":"Invalid"}), 400
    action = data.get("action","")
    target = safe_subpath(project, data.get("path",""))
    if target is None: return jsonify({"error":"Invalid path"}), 400
    try:
        if action == "create-file":
            if target.exists(): return jsonify({"error":"Exists"}), 400
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(data.get("content",""), encoding="utf-8")
            return jsonify({"success":True})
        if action == "create-folder":
            if target.exists(): return jsonify({"error":"Exists"}), 400
            target.mkdir(parents=True, exist_ok=True)
            return jsonify({"success":True})
        if action == "delete":
            if not target.exists(): return jsonify({"error":"Not found"}), 404
            if target == project: return jsonify({"error":"Cannot delete root"}), 400
            if target.is_dir(): shutil.rmtree(target)
            else: target.unlink()
            return jsonify({"success":True})
        if action == "rename":
            nn = data.get("newName","")
            if not nn: return jsonify({"error":"New name required"}), 400
            nt = safe_subpath(project, nn)
            if nt is None: return jsonify({"error":"Invalid"}), 400
            if nt.exists(): return jsonify({"error":"Target exists"}), 400
            if not target.exists(): return jsonify({"error":"Source missing"}), 404
            nt.parent.mkdir(parents=True, exist_ok=True)
            target.rename(nt)
            return jsonify({"success":True})
        return jsonify({"error":"Unknown"}), 400
    except Exception as e:
        return jsonify({"error":str(e)}), 500


def read_file_line(path, line_num):
    """Read a specific line from file."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        if 1 <= line_num <= len(lines):
            return lines[line_num - 1].rstrip()[:300]
    except Exception:
        pass
    return ""


def parse_errors(lang_name, output, file_path=None):
    """Parse errors from various compilers - v8 improved."""
    errors = []
    lines_seen = set()

    for line in output.splitlines():
        line = line.strip()
        if not line: continue

        # === GCC / G++ / Clang: file.c:5:10: error: message ===
        m = re.match(r'^[^:]+:(\d+):(\d+):\s*(error|fatal error):\s*(.+)', line)
        if m:
            ln = int(m.group(1))
            errors.append({
                "line": ln, "col": int(m.group(2)),
                "message": m.group(4)[:200],
                "code": read_file_line(file_path, ln) if file_path else ""
            })
            continue

        # === Python: File "x.py", line 5 ===
        m = re.match(r'^\s*File\s+"[^"]+",\s+line\s+(\d+)', line)
        if m:
            ln = int(m.group(1))
            if ln not in lines_seen:
                lines_seen.add(ln)
                errors.append({
                    "line": ln, "col": 1,
                    "message": "Syntax/Runtime error",
                    "code": read_file_line(file_path, ln) if file_path else ""
                })
            continue

        # === Python: SyntaxError: message (next line) ===
        m = re.match(r'^(SyntaxError|IndentationError|TabError|NameError|TypeError|ValueError|KeyError|AttributeError|ImportError|ModuleNotFoundError|IndexError|ZeroDivisionError):\s*(.+)', line)
        if m:
            if errors and errors[-1]["message"] in ("Syntax/Runtime error", ""):
                errors[-1]["message"] = m.group(1) + ": " + m.group(2)[:150]
            else:
                errors.append({
                    "line": 0, "col": 1,
                    "message": m.group(1) + ": " + m.group(2)[:150],
                    "code": ""
                })
            continue

        # === PHP: Parse error: ... in file on line 5 ===
        m = re.search(r'on line (\d+)', line)
        if m and ("error" in line.lower() or "warning" in line.lower() or "notice" in line.lower()):
            ln = int(m.group(1))
            if ln not in lines_seen:
                lines_seen.add(ln)
                errors.append({
                    "line": ln, "col": 1,
                    "message": line[:200],
                    "code": read_file_line(file_path, ln) if file_path else ""
                })
            continue

        # === Node/JS: file.js:5:10: message ===
        m = re.match(r'^[^:]+:(\d+):(\d+):\s*(.+)', line)
        if m and ("SyntaxError" in line or "error" in line.lower()):
            ln = int(m.group(1))
            if ln not in lines_seen:
                lines_seen.add(ln)
                errors.append({
                    "line": ln, "col": int(m.group(2)),
                    "message": m.group(3)[:200],
                    "code": read_file_line(file_path, ln) if file_path else ""
                })
            continue

        # === Node: file.js:5 (line only) ===
        m = re.match(r'^[^:]+:(\d+)$', line)
        if m:
            ln = int(m.group(1))
            if ln not in lines_seen:
                lines_seen.add(ln)
                errors.append({
                    "line": ln, "col": 1,
                    "message": "Error",
                    "code": read_file_line(file_path, ln) if file_path else ""
                })
            continue

        # === Ruby: file.rb:5: syntax error ===
        m = re.match(r'^[^:]+\.rb:(\d+):\s*(.+)', line)
        if m:
            ln = int(m.group(1))
            if ln not in lines_seen:
                lines_seen.add(ln)
                errors.append({
                    "line": ln, "col": 1,
                    "message": m.group(2)[:200],
                    "code": read_file_line(file_path, ln) if file_path else ""
                })
            continue

        # === Go: file.go:5:10: message ===
        m = re.match(r'^[^:]+\.go:(\d+):(\d+):\s*(.+)', line)
        if m:
            ln = int(m.group(1))
            if ln not in lines_seen:
                lines_seen.add(ln)
                errors.append({
                    "line": ln, "col": int(m.group(2)),
                    "message": m.group(3)[:200],
                    "code": read_file_line(file_path, ln) if file_path else ""
                })
            continue

        # === Bash: file.sh: line 5: message ===
        m = re.match(r'^[^:]+\.sh:\s*line\s+(\d+):\s*(.+)', line)
        if m:
            ln = int(m.group(1))
            if ln not in lines_seen:
                lines_seen.add(ln)
                errors.append({
                    "line": ln, "col": 1,
                    "message": m.group(2)[:200],
                    "code": read_file_line(file_path, ln) if file_path else ""
                })
            continue

    # Deduplicate by line
    seen = {}
    for e in errors:
        key = e["line"] if e["line"] > 0 else ("msg", e["message"][:50])
        if key not in seen:
            seen[key] = e
    return list(seen.values())


@app.route("/api/check-file/<path:name>")
def check_file(name):
    project = safe_project(name)
    if project is None or not project.exists():
        return jsonify({"error":"Invalid"}), 400
    target = safe_subpath(project, request.args.get("path",""))
    if target is None or not target.is_file():
        return jsonify({"error":"Not found"}), 404
    ext = target.suffix.lower()
    lang = LANGUAGES.get(ext)
    if not lang or not lang["check"]:
        return jsonify({"errors":[],"language":lang["name"] if lang else "?","skipped":True})
    cmd = lang["check"].replace("{file}", str(target))
    try:
        result = subprocess.run(cmd, shell=True, cwd=str(target.parent),
                                capture_output=True, text=True, timeout=60)
        output = (result.stdout or "") + "\n" + (result.stderr or "")
        if result.returncode == 0:
            return jsonify({"errors":[],"language":lang["name"]})
        errs = parse_errors(lang["name"], output, str(target))
        return jsonify({"errors":errs,"language":lang["name"],"raw":output[:2000]})
    except subprocess.TimeoutExpired:
        return jsonify({"errors":[],"error":"Timeout"})
    except Exception as e:
        return jsonify({"errors":[],"error":str(e)})

@app.route("/api/scan-errors/<path:name>")
def scan_errors(name):
    project = safe_project(name)
    if project is None or not project.exists():
        return jsonify({"error":"Invalid"}), 400
    results = []; scanned = 0
    for path in sorted(project.rglob("*")):
        if not path.is_file(): continue
        parts = str(path).split(os.sep)
        if any(p in ("build",".gradle",".git","node_modules","__pycache__") for p in parts): continue
        try:
            if path.stat().st_size > 500_000: continue
        except Exception: continue
        ext = path.suffix.lower()
        lang = LANGUAGES.get(ext)
        if not lang or not lang["check"]: continue
        scanned += 1
        rel = str(path.relative_to(project))
        cmd = lang["check"].replace("{file}", str(path))
        try:
            r = subprocess.run(cmd, shell=True, cwd=str(path.parent),
                              capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                out = (r.stdout or "") + "\n" + (r.stderr or "")
                errs = parse_errors(lang["name"], out, str(path))
                if errs:
                    results.append({"path":rel,"language":lang["name"],"errors":errs})
        except Exception: continue
    return jsonify({"scanned":scanned,"results":results})

@app.route("/api/run-command", methods=["POST"])
def run_command():
    data = request.get_json(silent=True) or {}
    project = safe_project(data.get("project",""))
    if project is None or not project.exists():
        return jsonify({"error":"Invalid"}), 400
    cmd = data.get("cmd","").strip()
    if not cmd: return jsonify({"error":"Empty"}), 400
    blocked = ["rm -rf /","mkfs","dd if=",":(){","shutdown","reboot"]
    for b in blocked:
        if b in cmd: return jsonify({"error":"Blocked"}), 403
    try:
        r = subprocess.run(cmd, shell=True, cwd=str(project),
                          capture_output=True, text=True, timeout=180)
        return jsonify({"stdout":r.stdout,"stderr":r.stderr,"returncode":r.returncode})
    except subprocess.TimeoutExpired:
        return jsonify({"error":"Timeout"}), 500
    except Exception as e:
        return jsonify({"error":str(e)}), 500

@app.route("/api/run-code", methods=["POST"])
def run_code():
    data = request.get_json(silent=True) or {}
    project = safe_project(data.get("project",""))
    if project is None or not project.exists():
        return jsonify({"error":"Invalid"}), 400
    target = safe_subpath(project, data.get("path",""))
    if target is None or not target.is_file():
        return jsonify({"error":"Not found"}), 404
    ext = target.suffix.lower()
    lang = LANGUAGES.get(ext)
    if not lang: return jsonify({"error":"Unsupported"}), 400
    if lang["run"] is None: return jsonify({"error":lang["name"]+" not runnable"}), 400
    cmd = lang["run"].replace("{file}", str(target)).replace("{name}", target.name)
    try:
        r = subprocess.run(cmd, shell=True, cwd=str(target.parent),
                          capture_output=True, text=True, timeout=120)
        return jsonify({"language":lang["name"],"command":cmd,
                       "stdout":r.stdout,"stderr":r.stderr,"returncode":r.returncode})
    except subprocess.TimeoutExpired:
        return jsonify({"error":"Timeout","language":lang["name"],"command":cmd}), 500
    except Exception as e:
        return jsonify({"error":str(e),"language":lang["name"],"command":cmd}), 500


def build_worker(build_id, project, env):
    B = BUILDS[build_id]
    cmd = "gradle assembleDebug --no-daemon --console=plain --parallel"
    try:
        proc = subprocess.Popen(cmd, shell=True, cwd=str(project), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in iter(proc.stdout.readline, ""):
            B["output"].append(line.rstrip())
        proc.wait()
        B["returncode"] = proc.returncode
        apks = list(project.glob("app/build/outputs/apk/**/*.apk"))
        B["apk_path"] = str(apks[0]) if apks else None
        B["status"] = "done"
        B["success"] = (proc.returncode == 0 and B["apk_path"] is not None)
    except Exception as e:
        B["output"].append("[build error] " + str(e))
        B["status"] = "done"; B["success"] = False; B["returncode"] = -1

@app.route("/api/build-start", methods=["POST"])
def build_start():
    data = request.get_json(silent=True) or {}
    project = safe_project(data.get("project",""))
    if project is None or not project.exists():
        return jsonify({"error":"Invalid"}), 400
    env = os.environ.copy()
    sdk = Path.home() / "android-sdk"
    if sdk.exists():
        env["ANDROID_HOME"] = str(sdk); env["ANDROID_SDK_ROOT"] = str(sdk)
    env["PATH"] = str(sdk / "platform-tools") + ":" + TERMUX_PREFIX + "/bin:" + env.get("PATH","")
    build_id = str(uuid.uuid4())
    BUILDS[build_id] = {"output":[],"status":"running","apk_path":None,"returncode":None,"success":None}
    t = threading.Thread(target=build_worker, args=(build_id, project, env), daemon=True)
    t.start()
    return jsonify({"build_id": build_id, "status":"started"})

@app.route("/api/build-poll/<build_id>")
def build_poll(build_id):
    B = BUILDS.get(build_id)
    if not B: return jsonify({"error":"Not found"}), 404
    since = int(request.args.get("since", 0))
    return jsonify({
        "lines": B["output"][since:], "total": len(B["output"]),
        "status": B["status"], "success": B.get("success"),
        "apk_path": B.get("apk_path"), "returncode": B.get("returncode")
    })

@app.route("/api/download-apk/<path:name>")
def download_apk(name):
    project = safe_project(name)
    if project is None or not project.exists(): return "Invalid", 400
    apks = list(project.glob("app/build/outputs/apk/**/*.apk"))
    if not apks: return "No APK found.", 404
    apk = apks[0]
    return send_file(str(apk), as_attachment=True, download_name=apk.name)


if __name__ == "__main__":
    print("")
    print("====================================")
    print("⚡ ZIHAD MOBILE IDE v8")
    print("====================================")
    print("Projects  :", PROJECTS_DIR)
    print("Server    :", f"http://127.0.0.1:{PORT}")
    print("Features  : Better errors, Cut/Copy/Paste, Live build")
    print("====================================")
    print("")
    app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)
PYEOF
