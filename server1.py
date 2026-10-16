from flask import Flask, jsonify, request, send_file
from pathlib import Path
import json, re, subprocess, shutil, os, threading, time, uuid, zipfile, io
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)

BASE_DIR = Path.home() / "Projects" / "ZihadIDE"
PROJECTS_DIR = BASE_DIR / "projects"
APKS_DIR = BASE_DIR / "apks"
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
APKS_DIR.mkdir(parents=True, exist_ok=True)

PORT = 3060
TERMUX_PREFIX = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
BUILDS = {}

LANGUAGES = {
    ".py": {"name": "Python", "run": 'python "{file}"', "check": 'python -m py_compile "{file}"'},
    ".c": {"name": "C", "run": 'gcc "{file}" -o /tmp/zh_out && /tmp/zh_out', "check": 'gcc -fsyntax-only -Wall "{file}"'},
    ".cpp": {"name": "C++", "run": 'g++ "{file}" -o /tmp/zh_out && /tmp/zh_out', "check": 'g++ -fsyntax-only -Wall "{file}"'},
    ".cc": {"name": "C++", "run": 'g++ "{file}" -o /tmp/zh_out && /tmp/zh_out', "check": 'g++ -fsyntax-only -Wall "{file}"'},
    ".php": {"name": "PHP", "run": 'php "{file}"', "check": 'php -l "{file}"'},
    ".js": {"name": "JavaScript", "run": 'node "{file}"', "check": 'node --check "{file}"'},
    ".go": {"name": "Go", "run": 'go run "{file}"', "check": 'gofmt -e "{file}"'},
    ".rs": {"name": "Rust", "run": 'rustc "{file}" -o /tmp/zh_out && /tmp/zh_out', "check": None},
    ".rb": {"name": "Ruby", "run": 'ruby "{file}"', "check": 'ruby -c "{file}"'},
    ".pl": {"name": "Perl", "run": 'perl "{file}"', "check": 'perl -c "{file}"'},
    ".sh": {"name": "Bash", "run": 'bash "{file}"', "check": 'bash -n "{file}"'},
    ".java": {"name": "Java", "run": 'java "{file}"', "check": None},
    ".kt": {"name": "Kotlin", "run": None, "check": None},
    ".html": {"name": "HTML", "run": None, "check": None},
    ".css": {"name": "CSS", "run": None, "check": None},
    ".json": {"name": "JSON", "run": None, "check": 'python -c "import json,sys; json.load(open(sys.argv[1]))" "{file}"'},
    ".xml": {"name": "XML", "run": None, "check": 'python -c "import xml.etree.ElementTree as ET,sys; ET.parse(sys.argv[1])" "{file}"'},
    ".md": {"name": "Markdown", "run": None, "check": None},
    ".txt": {"name": "Text", "run": None, "check": None},
    ".gradle": {"name": "Gradle", "run": None, "check": None},
    ".properties": {"name": "Properties", "run": None, "check": None},
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

def human_size(n):
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} TB"

def create_android_project(name, package, language, template="empty"):
    project = PROJECTS_DIR / name
    if project.exists():
        raise ValueError("Project already exists")
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

    if template == "login":
        main_java = f'''package {package};

import android.app.Activity;
import android.os.Bundle;
import android.widget.Button;
import android.widget.EditText;
import android.widget.Toast;

public class MainActivity extends Activity {{
    @Override
    protected void onCreate(Bundle savedInstanceState) {{
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        EditText email = findViewById(R.id.email);
        EditText password = findViewById(R.id.password);
        Button loginBtn = findViewById(R.id.loginBtn);
        loginBtn.setOnClickListener(v -> {{
            String e = email.getText().toString().trim();
            String p = password.getText().toString().trim();
            if (e.isEmpty() || p.isEmpty()) {{
                Toast.makeText(this, "Please fill all fields", Toast.LENGTH_SHORT).show();
            }} else {{
                Toast.makeText(this, "Welcome " + e, Toast.LENGTH_SHORT).show();
            }}
        }});
    }}
}}
'''
        main_kotlin = f'''package {package};

import android.app.Activity
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.Toast

class MainActivity : Activity() {{
    override fun onCreate(savedInstanceState: Bundle?) {{
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        val email = findViewById<EditText>(R.id.email)
        val password = findViewById<EditText>(R.id.password)
        val loginBtn = findViewById<Button>(R.id.loginBtn)
        loginBtn.setOnClickListener {{
            val e = email.text.toString().trim()
            val p = password.text.toString().trim()
            if (e.isEmpty() || p.isEmpty()) {{
                Toast.makeText(this, "Please fill all fields", Toast.LENGTH_SHORT).show()
            }} else {{
                Toast.makeText(this, "Welcome $e", Toast.LENGTH_SHORT).show()
            }}
        }}
    }}
}}
'''
        layout = '''<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent" android:layout_height="match_parent"
    android:orientation="vertical" android:gravity="center"
    android:padding="32dp" android:background="#0f172a">
    <TextView android:layout_width="wrap_content" android:layout_height="wrap_content"
        android:text="Welcome Back" android:textSize="28sp" android:textColor="#ffffff"
        android:layout_marginBottom="32dp"/>
    <EditText android:id="@+id/email" android:layout_width="match_parent"
        android:layout_height="wrap_content" android:hint="Email"
        android:inputType="textEmailAddress" android:textColor="#fff"
        android:textColorHint="#94a3b8" android:background="#1e293b"
        android:padding="16dp" android:layout_marginBottom="16dp"/>
    <EditText android:id="@+id/password" android:layout_width="match_parent"
        android:layout_height="wrap_content" android:hint="Password"
        android:inputType="textPassword" android:textColor="#fff"
        android:textColorHint="#94a3b8" android:background="#1e293b"
        android:padding="16dp" android:layout_marginBottom="24dp"/>
    <Button android:id="@+id/loginBtn" android:layout_width="match_parent"
        android:layout_height="wrap_content" android:text="Login"
        android:backgroundTint="#2563eb" android:textColor="#fff" android:padding="14dp"/>
</LinearLayout>
'''
    elif template == "list":
        main_java = f'''package {package};

import android.app.Activity;
import android.os.Bundle;
import android.widget.ArrayAdapter;
import android.widget.ListView;
import android.widget.Toast;

public class MainActivity extends Activity {{
    @Override
    protected void onCreate(Bundle savedInstanceState) {{
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        ListView list = findViewById(R.id.listView);
        String[] items = {{"Item 1", "Item 2", "Item 3", "Item 4", "Item 5"}};
        list.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_list_item_1, items));
        list.setOnItemClickListener((p, v, pos, id) ->
            Toast.makeText(this, "Clicked: " + items[pos], Toast.LENGTH_SHORT).show());
    }}
}}
'''
        main_kotlin = f'''package {package};

import android.app.Activity
import android.os.Bundle
import android.widget.ArrayAdapter
import android.widget.ListView
import android.widget.Toast

class MainActivity : Activity() {{
    override fun onCreate(savedInstanceState: Bundle?) {{
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        val list = findViewById<ListView>(R.id.listView)
        val items = arrayOf("Item 1", "Item 2", "Item 3", "Item 4", "Item 5")
        list.adapter = ArrayAdapter(this, android.R.layout.simple_list_item_1, items)
        list.setOnItemClickListener {{ _, _, pos, _ ->
            Toast.makeText(this, "Clicked: ${{items[pos]}}", Toast.LENGTH_SHORT).show()
        }}
    }}
}}
'''
        layout = '''<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent" android:layout_height="match_parent"
    android:orientation="vertical" android:background="#0f172a">
    <TextView android:layout_width="match_parent" android:layout_height="wrap_content"
        android:text="My List" android:textSize="22sp" android:textColor="#fff"
        android:padding="16dp" android:background="#1e293b"/>
    <ListView android:id="@+id/listView" android:layout_width="match_parent"
        android:layout_height="match_parent" android:divider="#334155" android:dividerHeight="1dp"/>
</LinearLayout>
'''
    else:
        main_java = f'''package {package};

import android.app.Activity;
import android.os.Bundle;
import android.widget.TextView;

public class MainActivity extends Activity {{
    @Override
    protected void onCreate(Bundle savedInstanceState) {{
        super.onCreate(savedInstanceState);
        TextView text = new TextView(this);
        text.setText("Hello from {name}");
        text.setTextSize(24);
        text.setTextColor(0xFFFFFFFF);
        setContentView(text);
    }}
}}
'''
        main_kotlin = f'''package {package};

import android.app.Activity
import android.os.Bundle
import android.widget.TextView

class MainActivity : Activity() {{
    override fun onCreate(savedInstanceState: Bundle?) {{
        super.onCreate(savedInstanceState)
        val text = TextView(this)
        text.text = "Hello from {name}"
        text.textSize = 24f
        text.setTextColor(0xFFFFFFFF.toInt())
        setContentView(text)
    }}
}}
'''
        layout = '''<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent" android:layout_height="match_parent"
    android:gravity="center" android:orientation="vertical" android:background="#0f172a">
    <TextView android:id="@+id/titleText" android:layout_width="wrap_content"
        android:layout_height="wrap_content" android:text="@string/app_name"
        android:textSize="24sp" android:textColor="#ffffff"/>
</LinearLayout>
'''

    manifest = f'''<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <uses-permission android:name="android.permission.INTERNET"/>
    <application android:theme="@style/AppTheme" android:label="@string/app_name"
        android:allowBackup="true" android:supportsRtl="true">
        <activity android:name="{package}.MainActivity" android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN"/>
                <category android:name="android.intent.category.LAUNCHER"/>
            </intent-filter>
        </activity>
    </application>
</manifest>
'''
    strings_xml = f'''<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">{name}</string>
</resources>
'''
    colors_xml = '''<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="black">#000000</color>
    <color name="white">#FFFFFF</color>
    <color name="primary">#2563EB</color>
    <color name="bg">#0f172a</color>
</resources>
'''
    themes_xml = '''<?xml version="1.0" encoding="utf-8"?>
<resources>
    <style name="AppTheme" parent="android:style/Theme.Material.Light.NoActionBar">
        <item name="android:colorAccent">#2563EB</item>
        <item name="android:statusBarColor">@color/black</item>
        <item name="android:navigationBarColor">@color/black</item>
        <item name="android:windowBackground">@color/bg</item>
    </style>
</resources>
'''
    ic_launcher = '''<?xml version="1.0" encoding="utf-8"?>
<layer-list xmlns:android="http://schemas.android.com/apk/res/android">
    <item><shape android:shape="rectangle"><solid android:color="#2563EB"/></shape></item>
</layer-list>
'''
    settings_gradle = f'''pluginManagement {{
    repositories {{ google(); mavenCentral(); gradlePluginPortal() }}
}}
dependencyResolutionManagement {{
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {{ google(); mavenCentral() }}
}}
rootProject.name = "{name}"
include(":app")
'''
    root_gradle = '''plugins {
    id 'com.android.application' version '8.7.3' apply false
}
'''
    app_gradle = f'''plugins {{
    id "com.android.application"
}}
android {{
    namespace "{package}"
    compileSdk 34
    defaultConfig {{
        applicationId "{package}"
        minSdk 23
        targetSdk 34
        versionCode 1
        versionName "1.0"
    }}
    buildTypes {{
        release {{ minifyEnabled false }}
    }}
    compileOptions {{
        sourceCompatibility JavaVersion.VERSION_17
        targetCompatibility JavaVersion.VERSION_17
    }}
}}
'''
    gradle_props = '''org.gradle.jvmargs=-Xmx1536m -XX:MaxMetaspaceSize=512m
android.useAndroidX=true
android.nonTransitiveRClass=true
org.gradle.caching=true
org.gradle.parallel=true
'''
    aapt2_path = TERMUX_PREFIX + "/bin/aapt2"
    local_props = f"sdk.dir={Path.home() / 'android-sdk'}\nandroid.aapt2FromMavenOverride={aapt2_path}\n"

    project_info = {
        "name": name, "package": package, "language": language,
        "versionCode": 1, "versionName": "1.0", "template": template,
        "created": datetime.now().isoformat()
    }

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
    write_file(project / "hello.py", f'print("Hello from {name}")\n')
    return project


# ========== HOME ==========
HOME_HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>Zihad Mobile IDE</title>
<style>
:root{--bg:#070b14;--card:rgba(17,24,39,.8);--border:rgba(55,65,81,.6);--primary:#3b82f6;--text:#f1f5f9;--muted:#94a3b8;--radius:18px}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;min-height:100vh;background-image:radial-gradient(ellipse at 20% 20%,rgba(59,130,246,.12) 0%,transparent 50%),radial-gradient(ellipse at 80% 80%,rgba(139,92,246,.1) 0%,transparent 50%)}
header{padding:18px 20px;background:rgba(15,23,42,.9);backdrop-filter:blur(20px);border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:50}
header h1{font-size:1.25rem;font-weight:700;background:linear-gradient(135deg,#60a5fa,#a78bfa);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.container{padding:20px;max-width:720px;margin:0 auto}
.card{background:var(--card);backdrop-filter:blur(16px);border:1px solid var(--border);border-radius:var(--radius);padding:20px;margin-bottom:18px;box-shadow:0 8px 32px rgba(0,0,0,.3)}
h2{font-size:1.05rem;margin-bottom:12px;color:#e2e8f0}
.status-dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#22c55e;margin-right:8px;box-shadow:0 0 10px #22c55e}
button{border:0;border-radius:12px;padding:11px 16px;margin:4px;font-weight:600;font-size:13px;cursor:pointer;color:#fff}
.btn-primary{background:linear-gradient(135deg,#3b82f6,#2563eb)}
.btn-success{background:linear-gradient(135deg,#22c55e,#16a34a)}
.btn-danger{background:linear-gradient(135deg,#ef4444,#dc2626)}
.btn-ghost{background:rgba(55,65,81,.6);border:1px solid var(--border)}
.btn-purple{background:linear-gradient(135deg,#8b5cf6,#7c3aed)}
input,select{width:100%;padding:14px 16px;margin:8px 0;border-radius:12px;border:1px solid var(--border);background:rgba(8,15,28,.8);color:var(--text);font-size:14px;outline:none}
.project{background:rgba(8,15,28,.6);border:1px solid var(--border);border-radius:14px;padding:16px;margin:10px 0;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.project-info{flex:1;min-width:160px}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600;margin-left:6px;background:rgba(59,130,246,.2);color:#93c5fd}
.hidden{display:none!important}
.toast-container{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);z-index:9999;display:flex;flex-direction:column;gap:8px;pointer-events:none}
.toast{background:rgba(15,23,42,.95);border:1px solid var(--border);color:#fff;padding:12px 20px;border-radius:14px;font-size:13px}
.toast.success{border-color:rgba(34,197,94,.5)}
.toast.error{border-color:rgba(239,68,68,.5)}
.fab{position:fixed;bottom:28px;right:24px;width:58px;height:58px;border-radius:18px;background:linear-gradient(135deg,#3b82f6,#8b5cf6);display:flex;align-items:center;justify-content:center;font-size:28px;color:#fff;border:0;z-index:40}
.template-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:12px 0}
.template-card{background:rgba(8,15,28,.7);border:2px solid var(--border);border-radius:14px;padding:14px;text-align:center;cursor:pointer;font-size:13px}
.template-card.active{border-color:var(--primary);background:rgba(59,130,246,.12)}
.template-card span{font-size:22px;display:block;margin-bottom:6px}
.apk-item{background:rgba(8,15,28,.55);border:1px solid var(--border);border-radius:12px;padding:12px;margin:7px 0;display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap}
</style>
</head>
<body>
<header>
  <h1>⚡ Zihad IDE v9.2</h1>
  <div>
    <button class="btn-purple" onclick="showApks()">📦 APKs</button>
    <button class="btn-success" onclick="showCreate()">+ New</button>
  </div>
</header>
<div class="container">
  <div class="card">
    <h2><span class="status-dot"></span>System Status</h2>
    <p id="status" style="color:var(--muted);font-size:13px">Checking...</p>
  </div>
  <div class="card hidden" id="createBox">
    <h2>📱 New Android Project</h2>
    <input id="appName" placeholder="App Name">
    <input id="packageName" placeholder="com.zihad.myapp">
    <select id="language"><option value="java">Java</option><option value="kotlin">Kotlin</option></select>
    <p style="font-size:13px;color:var(--muted);margin:10px 0 6px">Template</p>
    <div class="template-grid">
      <div class="template-card active" data-t="empty" onclick="selectTemplate(this)"><span>📄</span>Empty</div>
      <div class="template-card" data-t="login" onclick="selectTemplate(this)"><span>🔐</span>Login</div>
      <div class="template-card" data-t="list" onclick="selectTemplate(this)"><span>📋</span>List</div>
      <div class="template-card" data-t="empty" onclick="selectTemplate(this)"><span>🧭</span>Basic</div>
    </div>
    <div style="display:flex;gap:8px;margin-top:14px">
      <button class="btn-success" style="flex:1" onclick="createProject()">🚀 Create</button>
      <button class="btn-ghost" onclick="hideCreate()">Cancel</button>
    </div>
    <div id="message" style="display:none;padding:12px;border-radius:12px;margin-top:12px"></div>
  </div>
  <div class="card hidden" id="apksBox">
    <h2>📦 Built APKs</h2>
    <div id="apksList">Loading...</div>
    <button class="btn-ghost" style="width:100%;margin-top:10px" onclick="hideApks()">Close</button>
  </div>
  <div class="card">
    <h2>📂 Projects</h2>
    <div id="projects">Loading...</div>
  </div>
</div>
<button class="fab" onclick="showCreate()">+</button>
<div class="toast-container" id="toasts"></div>
<script>
var selectedTemplate="empty";
function selectTemplate(el){document.querySelectorAll(".template-card").forEach(function(c){c.classList.remove("active")});el.classList.add("active");selectedTemplate=el.dataset.t}
function showCreate(){document.getElementById("createBox").classList.remove("hidden");document.getElementById("apksBox").classList.add("hidden")}
function hideCreate(){document.getElementById("createBox").classList.add("hidden")}
function showApks(){document.getElementById("apksBox").classList.remove("hidden");document.getElementById("createBox").classList.add("hidden");loadApks()}
function hideApks(){document.getElementById("apksBox").classList.add("hidden")}
function toast(msg,type){type=type||"success";var c=document.getElementById("toasts");var t=document.createElement("div");t.className="toast "+type;t.innerText=msg;c.appendChild(t);setTimeout(function(){t.remove()},3000)}
function esc(t){var d=document.createElement("div");d.innerText=t;return d.innerHTML}
async function status(){try{var r=await fetch("/api/status");var d=await r.json();document.getElementById("status").innerText="Port "+d.port+"  •  "+d.projects+" projects"}catch(e){document.getElementById("status").innerText="Offline"}}
async function loadProjects(){try{var r=await fetch("/api/projects");var d=await r.json();var box=document.getElementById("projects");if(!d.projects.length){box.innerHTML='<p style="color:#94a3b8;text-align:center;padding:20px">No projects yet</p>';return}box.innerHTML="";d.projects.forEach(function(p){var div=document.createElement("div");div.className="project";div.innerHTML='<div class="project-info"><b>📱 '+esc(p.name)+'</b><span class="badge">'+esc(p.language||"?")+'</span><br><small style="color:#94a3b8">'+esc(p.package||"")+'</small></div><div><button class="btn-primary" onclick="location.href=\'/project/'+encodeURIComponent(p.name)+'\'">Open</button><button class="btn-danger" onclick="deleteProject(\''+esc(p.name)+'\')">🗑</button></div>';box.appendChild(div)})}catch(e){document.getElementById("projects").innerText="Error"}}
async function createProject(){var n=document.getElementById("appName").value.trim();var p=document.getElementById("packageName").value.trim();var l=document.getElementById("language").value;if(!n||!p){msg("Name & Package required",1);return}try{var r=await fetch("/api/projects",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:n,package:p,language:l,template:selectedTemplate})});var d=await r.json();if(!r.ok){msg(d.error||"Failed",1);return}msg("Created!",0);toast("Project created");document.getElementById("appName").value="";document.getElementById("packageName").value="";hideCreate();loadProjects();status()}catch(e){msg("Error",1)}}
async function deleteProject(name){if(!confirm("Delete "+name+"?"))return;try{var r=await fetch("/api/projects/"+encodeURIComponent(name),{method:"DELETE"});if(r.ok){toast("Deleted");loadProjects();status()}else toast("Failed","error")}catch(e){toast("Error","error")}}
async function loadApks(){try{var r=await fetch("/api/apks");var d=await r.json();var box=document.getElementById("apksList");if(!d.apks||!d.apks.length){box.innerHTML='<p style="color:#94a3b8;text-align:center">No APKs</p>';return}box.innerHTML="";d.apks.forEach(function(a){var div=document.createElement("div");div.className="apk-item";div.innerHTML='<div><b>📦 '+esc(a.name)+'</b><br><small style="color:#94a3b8">'+esc(a.size)+' • '+esc(a.mtime)+'</small></div><div><button class="btn-success" onclick="location.href=\'/api/download-saved-apk/'+encodeURIComponent(a.name)+'\'">⬇</button><button class="btn-danger" onclick="deleteApk(\''+esc(a.name)+'\')">🗑</button></div>';box.appendChild(div)})}catch(e){document.getElementById("apksList").innerText="Error"}}
async function deleteApk(name){if(!confirm("Delete?"))return;try{var r=await fetch("/api/apks/"+encodeURIComponent(name),{method:"DELETE"});if(r.ok){toast("Deleted");loadApks()}else toast("Failed","error")}catch(e){toast("Error","error")}}
function msg(t,e){var m=document.getElementById("message");m.style.display="block";m.innerText=t;m.style.background=e?"rgba(127,29,29,.55)":"rgba(20,83,45,.55)"}
status();loadProjects();
</script>
</body>
</html>
'''

# ========== IDE (তোমার আগের সম্পূর্ণ IDE + নতুন ফিচার) ==========
# কোডের দৈর্ঘ্যের কারণে IDE_HTML অংশটা আলাদা করে নিচে দিচ্ছি।
# পুরো ফাইল একসাথে চালানোর জন্য HOME + Backend + IDE সব একত্রিত।

# IDE_HTML শুরু
IDE_HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>__NAME__ - Zihad IDE</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/theme/dracula.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/dialog/dialog.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/fold/foldgutter.min.css">
<style>
:root{--bg:#070b14;--card:#111827;--border:#1f2937;--primary:#3b82f6;--text:#e2e8f0;--muted:#94a3b8;--success:#22c55e;--danger:#ef4444;--radius:14px;--bottom-h:62px}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:14px;overflow:hidden}
header{padding:8px 12px;background:rgba(15,23,42,.95);backdrop-filter:blur(16px);border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;gap:8px;position:relative;z-index:30}
header h2{font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1}
.btn{border:0;border-radius:10px;padding:7px 11px;font-weight:600;font-size:12px;color:#fff;cursor:pointer;background:#374151}
.btn-primary{background:linear-gradient(135deg,#3b82f6,#2563eb)}
.btn-success{background:linear-gradient(135deg,#22c55e,#16a34a)}
.btn-danger{background:linear-gradient(135deg,#ef4444,#dc2626)}
.btn-orange{background:linear-gradient(135deg,#f59e0b,#d97706)}
.btn-purple{background:linear-gradient(135deg,#8b5cf6,#7c3aed)}
.badge{display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700}
.badge.ok{background:rgba(34,197,94,.2);color:#4ade80}
.badge.err{background:rgba(239,68,68,.25);color:#fca5a5}
.bottom-nav{position:fixed;bottom:0;left:0;right:0;height:var(--bottom-h);background:rgba(15,23,42,.96);border-top:1px solid var(--border);display:flex;z-index:40;padding-bottom:env(safe-area-inset-bottom)}
.nav-item{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;font-size:10px;color:var(--muted);cursor:pointer}
.nav-item.active{color:#60a5fa}
.nav-item span{font-size:20px}
.main-area{height:calc(100vh - 52px - var(--bottom-h));overflow:hidden}
.panel{display:none;height:100%;overflow-y:auto;padding:12px;padding-bottom:20px}
.panel.active{display:block}
.breadcrumb{background:rgba(8,15,28,.7);padding:9px 12px;border-radius:10px;margin-bottom:10px;font-size:12px;word-break:break-all}
.breadcrumb span{color:#60a5fa;cursor:pointer}
.file-item{background:var(--card);padding:12px;margin:5px 0;border-radius:12px;border:1px solid var(--border);cursor:pointer;display:flex;align-items:center;gap:10px}
.file-item .name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.file-item.folder .name{color:#fbbf24;font-weight:600}
.file-item.file .name{color:#93c5fd}
.file-item .meta{font-size:10px;color:var(--muted);white-space:nowrap}
.toolbar{display:flex;gap:6px;margin-bottom:10px;flex-wrap:wrap}
.sort-bar{display:flex;gap:6px;margin-bottom:8px}
.sort-bar select{padding:7px 10px;border-radius:8px;border:1px solid var(--border);background:#0b1220;color:#fff;font-size:12px}
#editor-box{position:fixed;inset:0;background:var(--bg);z-index:100;display:none;flex-direction:column}
#editor-header{padding:7px 10px;background:rgba(15,23,42,.95);border-bottom:1px solid var(--border);display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.tab-bar-editor{display:flex;overflow-x:auto;background:#0b1220;border-bottom:1px solid var(--border)}
.editor-tab{padding:9px 14px;font-size:12px;white-space:nowrap;cursor:pointer;border-bottom:2px solid transparent;color:var(--muted)}
.editor-tab.active{color:#60a5fa;border-bottom-color:#3b82f6;background:rgba(59,130,246,.08)}
.editor-tab .close-tab{opacity:.5;font-size:14px;padding:0 2px}
#editor-toolbar{padding:5px 8px;background:#0b1220;border-bottom:1px solid var(--border);display:flex;gap:4px;flex-wrap:wrap}
#editor-toolbar button{background:#1f2937;color:#e2e8f0;border:0;border-radius:7px;padding:6px 10px;font-size:11px;font-weight:600;cursor:pointer}
#editor-container{flex:1;overflow:hidden}
.CodeMirror{height:100%!important;font-size:13px;font-family:'JetBrains Mono',Consolas,monospace}
.cm-error-line{background:rgba(239,68,68,.18)!important}
#terminal-output{background:#000;color:#4ade80;padding:12px;border-radius:12px;min-height:220px;max-height:calc(100vh - 220px);overflow-y:auto;font-size:12px;white-space:pre-wrap;font-family:monospace;border:1px solid #1f2937;margin-bottom:10px}
#cmd-input{display:flex;gap:6px}
#cmd-input input{flex:1;padding:11px;background:#0b1220;color:#e2e8f0;border:1px solid #374151;border-radius:10px;font-family:monospace;font-size:13px}
#cmd-input button{padding:11px 16px;background:var(--success);color:#fff;border:0;border-radius:10px;font-weight:700}
.output-box{background:#000;color:#4ade80;padding:12px;border-radius:12px;min-height:200px;white-space:pre-wrap;font-family:monospace;font-size:12px;border:1px solid #1f2937;max-height:calc(100vh - 280px);overflow-y:auto}
.err-item{background:rgba(127,29,29,.5);color:#fecaca;padding:12px;border-radius:10px;margin:6px 0;cursor:pointer;border-left:4px solid #ef4444;font-family:monospace;font-size:12px}
.info-bar{background:rgba(8,15,28,.7);padding:10px;border-radius:10px;margin-bottom:10px;font-size:12px;border:1px solid var(--border)}
.build-panel{background:#0b1220;border:1px solid #1f2937;border-radius:14px;padding:16px;margin-bottom:14px}
.progress-wrap{background:#1f2937;border-radius:20px;height:28px;overflow:hidden;position:relative;margin:12px 0}
.progress-bar{height:100%;background:linear-gradient(90deg,#3b82f6,#8b5cf6);transition:width .4s;width:0%}
.progress-text{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;color:#fff}
.toast-container{position:fixed;bottom:calc(var(--bottom-h)+16px);left:50%;transform:translateX(-50%);z-index:999;display:flex;flex-direction:column;gap:8px;pointer-events:none}
.toast{background:rgba(15,23,42,.96);border:1px solid var(--border);color:#fff;padding:11px 18px;border-radius:12px;font-size:13px}
.toast.success{border-color:rgba(34,197,94,.45)}
.toast.error{border-color:rgba(239,68,68,.45)}
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.65);z-index:200;display:none;align-items:flex-end;justify-content:center}
.modal-overlay.show{display:flex}
.modal{background:#111827;border-radius:20px 20px 0 0;padding:24px;width:100%;max-width:480px;max-height:80vh;overflow-y:auto}
.empty{color:var(--muted);text-align:center;padding:30px;font-style:italic}
.search-box{display:flex;gap:8px;margin-bottom:10px}
.search-box input{flex:1;padding:11px 14px;border-radius:10px;border:1px solid var(--border);background:#0b1220;color:#fff;font-size:14px}
.upload-btn{position:relative;overflow:hidden}
.upload-btn input{position:absolute;inset:0;opacity:0;cursor:pointer}
.preview-frame{background:#0f172a;border-radius:28px;border:6px solid #1e293b;width:min(320px,90vw);margin:0 auto;overflow:hidden;min-height:480px}
.preview-content{padding:16px;min-height:440px;color:#fff}
</style>
</head>
<body>
<header>
  <h2>📱 __NAME__</h2>
  <div style="display:flex;gap:4px;flex-wrap:wrap">
    <button class="btn btn-orange" onclick="scanAllErrors()" id="scanBtn">🔍</button>
    <button class="btn btn-purple" onclick="runCurrent()" id="runBtn" style="display:none">▶</button>
    <button class="btn btn-primary" onclick="buildApk()">🔨</button>
    <button class="btn" onclick="exportZip()">📦</button>
    <button class="btn" onclick="openPkgRename()">📦Pkg</button>
    <button class="btn" onclick="openSettings()">⚙️</button>
    <button class="btn" onclick="location.href='/'">🏠</button>
  </div>
</header>

<div class="main-area">
  <div class="panel active" id="panel-explorer">
    <div class="toolbar">
      <button class="btn btn-success" onclick="newFile()">📄 +File</button>
      <button class="btn btn-orange" onclick="newFolder()">📁 +Folder</button>
      <button class="btn upload-btn">⬆ Upload<input type="file" id="uploadInput" onchange="doUpload(this)"></button>
      <button class="btn" onclick="loadFiles(currentPath)">🔄</button>
    </div>
    <div class="sort-bar">
      <select id="sortBy" onchange="loadFiles(currentPath)">
        <option value="name">Sort: Name</option>
        <option value="size">Sort: Size</option>
        <option value="date">Sort: Date</option>
      </select>
    </div>
    <div class="search-box">
      <input id="searchInput" placeholder="Search files..." oninput="filterFiles(this.value)">
      <button class="btn" onclick="clearSearch()">✕</button>
    </div>
    <div class="breadcrumb" id="breadcrumb">Loading...</div>
    <div id="file-list"><div class="empty">Loading...</div></div>
  </div>

  <div class="panel" id="panel-preview">
    <div class="info-bar">Live Layout Preview</div>
    <div style="text-align:center;margin-bottom:12px">
      <button class="btn btn-primary" onclick="refreshPreview()">🔄 Refresh Preview</button>
    </div>
    <div class="preview-frame">
      <div class="preview-content" id="previewContent">
        <p style="text-align:center;color:#64748b;padding:40px 20px">Open activity_main.xml or tap Refresh</p>
      </div>
    </div>
  </div>

  <div class="panel" id="panel-errors">
    <div class="info-bar" id="errInfo">Press 🔍 to scan</div>
    <div id="err-list"></div>
  </div>

  <div class="panel" id="panel-terminal">
    <div style="display:flex;justify-content:space-between;margin-bottom:8px">
      <span style="font-size:13px;color:var(--muted)">Terminal</span>
      <div>
        <button class="btn" style="padding:4px 10px;font-size:11px" onclick="showTermHelp()">ℹ️ Info</button>
        <button class="btn" style="padding:4px 10px;font-size:11px" onclick="clearTerminal()">Clear</button>
      </div>
    </div>
    <div id="terminal-output">$ Zihad IDE Terminal — Ready
</div>
    <div id="cmd-input">
      <input id="cmd" placeholder="ls, pwd, gradle -v..." onkeydown="termKey(event)">
      <button onclick="runCmd()">Run</button>
    </div>
  </div>

  <div class="panel" id="panel-output">
    <div class="info-bar" id="run-info">No code executed yet</div>
    <div class="output-box" id="output-box">Output will appear here...</div>
  </div>

  <div class="panel" id="panel-build">
    <div class="build-panel">
      <h3 style="margin:0 0 10px;font-size:15px;color:#60a5fa">🔨 APK Build</h3>
      <div class="progress-wrap">
        <div class="progress-bar" id="buildProgressBar"></div>
        <div class="progress-text" id="buildProgressText">0%</div>
      </div>
      <div id="currentTask" style="font-family:monospace;font-size:12px;color:#fbbf24;margin:10px 0">Press 🔨 to build</div>
      <div id="buildStatusMsg" style="text-align:center;font-size:13px;color:var(--muted)">Ready</div>
      <div id="apk-box" style="display:none;margin-top:12px">
        <button class="btn btn-success" id="apkDownloadBtn" style="width:100%;padding:14px;margin-bottom:8px">⬇ Download APK</button>
        <button class="btn btn-primary" style="width:100%;padding:14px" onclick="adbInstall()">📲 Install via ADB</button>
      </div>
    </div>
    <div class="info-bar">Live Build Log</div>
    <div class="output-box" id="buildLog">$ Waiting...</div>
  </div>
</div>

<nav class="bottom-nav">
  <div class="nav-item active" data-panel="explorer" onclick="switchPanel('explorer',this)"><span>📂</span>Files</div>
  <div class="nav-item" data-panel="preview" onclick="switchPanel('preview',this)"><span>📱</span>Preview</div>
  <div class="nav-item" data-panel="errors" onclick="switchPanel('errors',this)"><span>⚠️</span>Errors <span id="errBadgeNav" class="badge ok" style="font-size:9px">0</span></div>
  <div class="nav-item" data-panel="terminal" onclick="switchPanel('terminal',this)"><span>💻</span>Term</div>
  <div class="nav-item" data-panel="build" onclick="switchPanel('build',this)"><span>🔨</span>Build</div>
</nav>

<div id="editor-box">
  <div id="editor-header">
    <span style="font-size:12px;color:#93c5fd;font-family:monospace;flex:1;overflow:hidden;text-overflow:ellipsis" id="editor-filename">file</span>
    <span id="editor-err-badge" class="badge ok">0</span>
    <button class="btn btn-success" onclick="saveFile(false)">💾</button>
    <button class="btn btn-orange" onclick="checkCurrentFile()">🔍</button>
    <button class="btn btn-purple" onclick="runCurrent()">▶</button>
    <button class="btn" onclick="closeEditor()">✖</button>
  </div>
  <div class="tab-bar-editor" id="editorTabs"></div>
  <div id="editor-toolbar">
    <button onclick="doSelectAll()">Select</button>
    <button onclick="doCut()">Cut</button>
    <button onclick="doCopy()">Copy</button>
    <button onclick="doPaste()">Paste</button>
    <button onclick="doUndo()">Undo</button>
    <button onclick="doRedo()">Redo</button>
    <button onclick="doFind()">Find</button>
    <button onclick="doIndent()">Indent</button>
    <button onclick="formatCode()">Format</button>
  </div>
  <div id="editor-container"><textarea id="editor"></textarea></div>
</div>

<div class="modal-overlay" id="settingsModal" onclick="if(event.target===this)this.classList.remove('show')">
  <div class="modal">
    <h3>⚙️ Settings</h3>
    <div style="margin:12px 0"><label>Font Size</label><input type="range" id="fontSize" min="11" max="20" value="13" oninput="applyFontSize(this.value)" style="width:100%"></div>
    <div style="margin:12px 0"><label>Auto Save</label>
      <select id="autoSave" onchange="localStorage.setItem('autoSave',this.value)" style="width:100%;padding:8px;border-radius:8px;background:#0b1220;color:#fff;border:1px solid #374151">
        <option value="off">Off</option>
        <option value="on">On (silent)</option>
      </select>
    </div>
    <div style="margin:12px 0"><label>Theme</label>
      <select id="cmTheme" onchange="changeTheme(this.value)" style="width:100%;padding:8px;border-radius:8px;background:#0b1220;color:#fff;border:1px solid #374151">
        <option value="dracula">Dracula</option>
        <option value="material-darker">Material</option>
        <option value="monokai">Monokai</option>
      </select>
    </div>
    <button class="btn btn-primary" style="width:100%;margin-top:14px" onclick="document.getElementById('settingsModal').classList.remove('show')">Done</button>
  </div>
</div>

<div class="modal-overlay" id="termHelpModal" onclick="if(event.target===this)this.classList.remove('show')">
  <div class="modal">
    <h3>💻 Terminal Help</h3>
    <div style="font-size:13px;line-height:1.7;color:#cbd5e1">
      <p><b>Basic:</b></p>
      <p><code>ls</code> — list files</p>
      <p><code>pwd</code> — current path</p>
      <p><code>cd app</code> — change directory</p>
      <p><code>cat file.txt</code> — view file</p>
      <p><code>gradle -v</code> — gradle version</p>
      <p><code>gradle assembleDebug</code> — build</p>
      <p style="margin-top:10px"><b>Tips:</b> Commands run inside project folder. Dangerous commands blocked.</p>
    </div>
    <button class="btn btn-primary" style="width:100%;margin-top:14px" onclick="document.getElementById('termHelpModal').classList.remove('show')">Close</button>
  </div>
</div>

<div class="modal-overlay" id="pkgModal" onclick="if(event.target===this)this.classList.remove('show')">
  <div class="modal">
    <h3>📦 Rename Package</h3>
    <input id="oldPkg" placeholder="Old package" style="width:100%;padding:12px;margin:8px 0;border-radius:10px;border:1px solid #374151;background:#0b1220;color:#fff">
    <input id="newPkg" placeholder="New package" style="width:100%;padding:12px;margin:8px 0;border-radius:10px;border:1px solid #374151;background:#0b1220;color:#fff">
    <button class="btn btn-primary" style="width:100%;margin-top:12px" onclick="doPkgRename()">Update All Files</button>
    <button class="btn" style="width:100%;margin-top:6px" onclick="document.getElementById('pkgModal').classList.remove('show')">Cancel</button>
  </div>
</div>

<div class="toast-container" id="toasts"></div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/edit/matchbrackets.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/edit/closebrackets.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/search/search.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/search/searchcursor.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/dialog/dialog.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/fold/foldcode.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/fold/foldgutter.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/python/python.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/clike/clike.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/javascript/javascript.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/xml/xml.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/css/css.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/htmlmixed/htmlmixed.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/shell/shell.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/markdown/markdown.min.js"></script>
<script>
var PROJECT = "__NAME__";
var currentPath = "";
var openTabs = [];
var activeTabIdx = -1;
var cm = null;
var errorLines = [];
var buildPollTimer = null;
var buildStartTime = 0;
var elapsedTimer = null;
var tasksSeen = 0;
var EST_TOTAL = 32;
var buildId = null;
var lastLineIdx = 0;
var cmdHistory = [];
var histIdx = -1;
var autoSaveTimer = null;
var allFilesCache = [];

function toast(msg, type) {
  type = type || "success";
  var c = document.getElementById("toasts");
  var t = document.createElement("div");
  t.className = "toast " + type;
  t.innerText = msg;
  c.appendChild(t);
  setTimeout(function() { t.remove(); }, 3000);
}
function esc(t) { var d = document.createElement("div"); d.innerText = t; return d.innerHTML; }
function switchPanel(id, el) {
  document.querySelectorAll(".nav-item").forEach(function(n) { n.classList.remove("active"); });
  document.querySelectorAll(".panel").forEach(function(p) { p.classList.remove("active"); });
  if (el) el.classList.add("active");
  var panel = document.getElementById("panel-" + id);
  if (panel) panel.classList.add("active");
  if (id === "preview") refreshPreview();
}
function getMode(filename) {
  var ext = filename.split(".").pop().toLowerCase();
  var map = { py: "python", c: "text/x-csrc", cpp: "text/x-c++src", cc: "text/x-c++src", java: "text/x-java", kt: "text/x-kotlin", js: "javascript", xml: "xml", html: "htmlmixed", css: "css", json: "application/json", md: "markdown", sh: "text/x-sh", gradle: "text/x-java" };
  return map[ext] || "null";
}

async function loadFiles(path) {
  currentPath = path || "";
  var box = document.getElementById("file-list");
  var bc = document.getElementById("breadcrumb");
  if (!box || !bc) return;
  box.innerHTML = '<div class="empty">Loading...</div>';
  try {
    var sort = (document.getElementById("sortBy") && document.getElementById("sortBy").value) || "name";
    var r = await fetch("/api/project-files/" + encodeURIComponent(PROJECT) + "?path=" + encodeURIComponent(currentPath) + "&sort=" + sort);
    var d = await r.json();
    if (!r.ok) {
      box.innerHTML = '<div class="empty" style="color:#f87171">Error: ' + (d.error || r.status) + '</div>';
      return;
    }
    var parts = currentPath ? currentPath.split("/") : [];
    var bcHtml = '<span onclick="loadFiles(\'\')">📁 ' + esc(PROJECT) + '</span>';
    var acc = "";
    parts.forEach(function(p) {
      acc += (acc ? "/" : "") + p;
      bcHtml += ' / <span onclick="loadFiles(\'' + acc + '\')">' + esc(p) + '</span>';
    });
    bc.innerHTML = bcHtml;
    allFilesCache = d.files || [];
    if (!allFilesCache.length) {
      box.innerHTML = '<div class="empty">Empty folder</div>';
      return;
    }
    renderFileList(allFilesCache);
  } catch (e) {
    box.innerHTML = '<div class="empty" style="color:#f87171">Error: ' + (e.message || e) + '</div>';
  }
}

function renderFileList(files) {
  var box = document.getElementById("file-list");
  box.innerHTML = "";
  if (currentPath) {
    var parts = currentPath.split("/");
    var up = parts.slice(0, -1).join("/");
    var upDiv = document.createElement("div");
    upDiv.className = "file-item folder";
    upDiv.innerHTML = "<span>⬆️</span><span class='name'>.. (up)</span>";
    upDiv.onclick = function() { loadFiles(up); };
    box.appendChild(upDiv);
  }
  files.forEach(function(f) {
    var div = document.createElement("div");
    div.className = "file-item " + (f.type === "directory" ? "folder" : "file");
    var icon = f.type === "directory" ? "📁" : "📄";
    var meta = f.type === "file" ? ((f.size_h || "") + " • " + (f.mtime || "")) : (f.mtime || "");
    div.innerHTML = "<span>" + icon + "</span><span class='name'>" + esc(f.name) + "</span><span class='meta'>" + esc(meta) + "</span>";
    div.onclick = function() {
      if (f.type === "directory") loadFiles(f.path);
      else openFile(f.path);
    };
    div.oncontextmenu = function(e) {
      e.preventDefault();
      showItemMenu(f);
    };
    box.appendChild(div);
  });
}

function filterFiles(q) {
  q = (q || "").toLowerCase().trim();
  if (!q) { renderFileList(allFilesCache); return; }
  if (q.length >= 2) {
    fetch("/api/search/" + encodeURIComponent(PROJECT) + "?q=" + encodeURIComponent(q))
      .then(function(r) { return r.json(); })
      .then(function(d) {
        var box = document.getElementById("file-list");
        box.innerHTML = "";
        if (!d.results || !d.results.length) {
          box.innerHTML = '<div class="empty">No results</div>';
          return;
        }
        d.results.forEach(function(f) {
          var div = document.createElement("div");
          div.className = "file-item file";
          div.innerHTML = "<span>📄</span><span class='name'>" + esc(f.path) + "</span>";
          div.onclick = function() { openFile(f.path); };
          box.appendChild(div);
        });
      });
  } else {
    var filtered = allFilesCache.filter(function(f) { return f.name.toLowerCase().indexOf(q) !== -1; });
    renderFileList(filtered);
  }
}
function clearSearch() {
  document.getElementById("searchInput").value = "";
  renderFileList(allFilesCache);
}

function showItemMenu(f) {
  var c = prompt("Action for: " + f.name + "\n1=Open  2=Rename  3=Delete  4=Check");
  if (c === "1") {
    if (f.type === "directory") loadFiles(f.path);
    else openFile(f.path);
  } else if (c === "2") {
    var nn = prompt("New name:", f.name);
    if (nn && nn !== f.name) fileOp("rename", f.path, nn);
  } else if (c === "3") {
    if (confirm("Delete " + f.name + "?")) fileOp("delete", f.path);
  } else if (c === "4" && f.type === "file") checkFileErrors(f.path, true);
}

async function newFile() {
  var n = prompt("New file name (can use folder/file.java):");
  if (!n) return;
  var fp = currentPath ? currentPath + "/" + n : n;
  var c = prompt("Initial content (optional):", "") || "";
  await fileOp("create-file", fp, null, c);
}
async function newFolder() {
  var n = prompt("New folder name (can use a/b/c):");
  if (!n) return;
  var fp = currentPath ? currentPath + "/" + n : n;
  await fileOp("create-folder", fp);
}
async function fileOp(action, path, newName, content) {
  try {
    var body = { project: PROJECT, action: action, path: path };
    if (newName) body.newName = newName;
    if (content !== undefined) body.content = content;
    var r = await fetch("/api/file-operation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    var d = await r.json();
    if (!r.ok) { toast(d.error || "Error", "error"); return; }
    loadFiles(currentPath);
    toast("Done");
  } catch (e) { toast("Error: " + e, "error"); }
}
async function doUpload(input) {
  if (!input.files || !input.files[0]) return;
  var fd = new FormData();
  fd.append("file", input.files[0]);
  fd.append("path", currentPath);
  try {
    var r = await fetch("/api/upload/" + encodeURIComponent(PROJECT), { method: "POST", body: fd });
    var d = await r.json();
    if (r.ok) { toast("Uploaded"); loadFiles(currentPath); }
    else toast(d.error || "Fail", "error");
  } catch (e) { toast("Error", "error"); }
  input.value = "";
}

async function openFile(path) {
  var existing = -1;
  for (var i = 0; i < openTabs.length; i++) {
    if (openTabs[i].path === path) { existing = i; break; }
  }
  if (existing >= 0) {
    switchTab(existing);
    document.getElementById("editor-box").style.display = "flex";
    return;
  }
  try {
    var r = await fetch("/api/file-content/" + encodeURIComponent(PROJECT) + "?path=" + encodeURIComponent(path));
    var d = await r.json();
    if (!r.ok) { toast(d.error || "Error", "error"); return; }
    openTabs.push({ path: path, content: d.content, mode: getMode(path), dirty: false });
    activeTabIdx = openTabs.length - 1;
    document.getElementById("editor-box").style.display = "flex";
    renderTabs();
    loadTabContent();
    var ext = path.split(".").pop().toLowerCase();
    var runnable = ["py", "c", "cpp", "cc", "php", "js", "go", "rs", "rb", "sh", "java"];
    document.getElementById("runBtn").style.display = runnable.indexOf(ext) !== -1 ? "inline-block" : "none";
    setTimeout(checkCurrentFile, 400);
  } catch (e) { toast("Error: " + e, "error"); }
}

function renderTabs() {
  var bar = document.getElementById("editorTabs");
  bar.innerHTML = "";
  openTabs.forEach(function(t, i) {
    var div = document.createElement("div");
    div.className = "editor-tab" + (i === activeTabIdx ? " active" : "");
    var name = t.path.split("/").pop();
    div.innerHTML = (t.dirty ? "• " : "") + esc(name) + ' <span class="close-tab" data-i="' + i + '">×</span>';
    div.onclick = function(e) {
      if (e.target.classList.contains("close-tab")) closeTab(parseInt(e.target.dataset.i));
      else switchTab(i);
    };
    bar.appendChild(div);
  });
}
function switchTab(idx) {
  if (cm && activeTabIdx >= 0) openTabs[activeTabIdx].content = cm.getValue();
  activeTabIdx = idx;
  renderTabs();
  loadTabContent();
}
function loadTabContent() {
  if (activeTabIdx < 0 || !openTabs[activeTabIdx]) return;
  var tab = openTabs[activeTabIdx];
  document.getElementById("editor-filename").innerText = tab.path;
  if (cm) { cm.toTextArea(); cm = null; }
  cm = CodeMirror.fromTextArea(document.getElementById("editor"), {
    lineNumbers: true, mode: tab.mode, theme: localStorage.getItem("cmTheme") || "dracula",
    matchBrackets: true, autoCloseBrackets: true, indentUnit: 4, tabSize: 4, lineWrapping: true,
    foldGutter: true, gutters: ["CodeMirror-linenumbers", "CodeMirror-foldgutter"]
  });
  cm.setValue(tab.content);
  cm.on("change", function() {
    openTabs[activeTabIdx].dirty = true;
    renderTabs();
    if (localStorage.getItem("autoSave") === "on") {
      clearTimeout(autoSaveTimer);
      autoSaveTimer = setTimeout(function() { saveFile(true); }, 2500);
    }
  });
  setTimeout(function() { cm.refresh(); }, 80);
  applyFontSize(localStorage.getItem("fontSize") || 13);
}
function closeTab(idx) {
  if (openTabs[idx].dirty && !confirm("Unsaved changes. Close anyway?")) return;
  openTabs.splice(idx, 1);
  if (openTabs.length === 0) { closeEditor(); return; }
  if (activeTabIdx >= openTabs.length) activeTabIdx = openTabs.length - 1;
  if (idx <= activeTabIdx && activeTabIdx > 0) activeTabIdx--;
  renderTabs();
  loadTabContent();
}
function closeEditor() {
  if (cm && activeTabIdx >= 0) openTabs[activeTabIdx].content = cm.getValue();
  document.getElementById("editor-box").style.display = "none";
  document.getElementById("runBtn").style.display = "none";
  if (cm) { cm.toTextArea(); cm = null; }
}

function doSelectAll() { if (cm) { cm.execCommand("selectAll"); cm.focus(); } }
async function doCut() {
  if (!cm) return;
  var sel = cm.getSelection();
  if (!sel) { toast("Select first"); return; }
  try {
    await navigator.clipboard.writeText(sel);
    cm.replaceSelection("");
    toast("Cut");
  } catch (e) { toast("Cut failed", "error"); }
}
async function doCopy() {
  if (!cm) return;
  var sel = cm.getSelection();
  if (!sel) { toast("Select first"); return; }
  try {
    await navigator.clipboard.writeText(sel);
    toast("Copied");
  } catch (e) {
    var ta = document.createElement("textarea");
    ta.value = sel;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
    toast("Copied");
  }
}
async function doPaste() {
  if (!cm) return;
  try {
    var txt = await navigator.clipboard.readText();
    cm.replaceSelection(txt);
  } catch (e) { toast("Paste blocked – long press editor", "error"); }
}
function doUndo() { if (cm) cm.undo(); }
function doRedo() { if (cm) cm.redo(); }
function doFind() { if (cm) cm.execCommand("find"); }
function doIndent() {
  if (!cm) return;
  var sel = cm.getSelection();
  if (!sel) { cm.execCommand("indentMore"); return; }
  cm.replaceSelection(sel.split("\n").map(function(l) { return "    " + l; }).join("\n"));
}
function formatCode() {
  if (!cm) return;
  var lines = cm.getValue().split("\n");
  var indent = 0;
  var formatted = lines.map(function(l) {
    var t = l.trim();
    if (t.startsWith("}") || t.startsWith(")") || t.startsWith("]")) indent = Math.max(0, indent - 1);
    var res = "    ".repeat(indent) + t;
    if (t.endsWith("{") || t.endsWith("(")) indent++;
    return res;
  }).join("\n");
  cm.setValue(formatted);
  toast("Formatted");
}

async function saveFile(silent) {
  if (activeTabIdx < 0 || !cm) return;
  var tab = openTabs[activeTabIdx];
  var content = cm.getValue();
  try {
    var r = await fetch("/api/file-content/" + encodeURIComponent(PROJECT) + "?path=" + encodeURIComponent(tab.path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: content })
    });
    var d = await r.json();
    if (!r.ok) {
      if (!silent) toast(d.error || "Save failed", "error");
      return;
    }
    tab.content = content;
    tab.dirty = false;
    renderTabs();
    if (!silent) toast("Saved");
  } catch (e) {
    if (!silent) toast("Save error", "error");
  }
}

async function checkCurrentFile() {
  if (activeTabIdx < 0 || !cm) return;
  await saveFile(true);
  var path = openTabs[activeTabIdx].path;
  var result = await checkFileErrors(path, false);
  if (!result) return;
  errorLines.forEach(function(line) {
    if (cm && cm.getLineHandle(line - 1))
      cm.removeLineClass(cm.getLineHandle(line - 1), "background", "cm-error-line");
  });
  errorLines = [];
  var badge = document.getElementById("editor-err-badge");
  if (!result.errors.length) {
    badge.innerText = "0 ✓";
    badge.className = "badge ok";
  } else {
    badge.innerText = result.errors.length + " err";
    badge.className = "badge err";
    result.errors.forEach(function(e) {
      if (e.line && cm) {
        var h = cm.getLineHandle(e.line - 1);
        if (h) {
          cm.addLineClass(h, "background", "cm-error-line");
          errorLines.push(e.line);
        }
      }
    });
  }
}

async function checkFileErrors(path, showAlert) {
  try {
    var r = await fetch("/api/check-file/" + encodeURIComponent(PROJECT) + "?path=" + encodeURIComponent(path));
    var d = await r.json();
    if (!r.ok) return { errors: [] };
    if (showAlert) {
      if (!d.errors.length) toast("No errors");
      else toast(d.errors.length + " error(s)", "error");
    }
    return d;
  } catch (e) { return { errors: [] }; }
}

async function scanAllErrors() {
  document.getElementById("scanBtn").innerText = "⏳";
  document.getElementById("errInfo").innerText = "Scanning...";
  document.getElementById("err-list").innerHTML = "";
  try {
    var r = await fetch("/api/scan-errors/" + encodeURIComponent(PROJECT));
    var d = await r.json();
    if (!r.ok) { document.getElementById("errInfo").innerText = "Scan failed"; return; }
    var total = 0, bad = 0;
    var box = document.getElementById("err-list");
    (d.results || []).forEach(function(f) {
      if (f.errors && f.errors.length) {
        total += f.errors.length;
        bad++;
        var fh = document.createElement("div");
        fh.style.cssText = "color:#fbbf24;font-weight:700;margin-top:12px;font-size:13px";
        fh.innerText = "📄 " + f.path + " — " + f.errors.length + " error(s)";
        box.appendChild(fh);
        f.errors.forEach(function(e) {
          var item = document.createElement("div");
          item.className = "err-item";
          item.innerHTML = '<div style="color:#fbbf24;font-weight:700">Line ' + e.line + ', Col ' + (e.col || 1) + '</div><div>' + esc(e.message) + '</div>' +
            (e.code ? '<div style="background:#450a0a;padding:4px;margin-top:4px;border-radius:4px;font-size:11px">' + esc(e.code) + '</div>' : "");
          item.onclick = function() { jumpToError(f.path, e.line); };
          box.appendChild(item);
        });
      }
    });
    var badge = document.getElementById("errBadgeNav");
    if (total === 0) {
      badge.innerText = "0";
      badge.className = "badge ok";
      document.getElementById("errInfo").innerText = "✓ No errors in " + d.scanned + " files";
    } else {
      badge.innerText = total;
      badge.className = "badge err";
      document.getElementById("errInfo").innerText = bad + " file(s) • " + total + " error(s)";
    }
  } catch (e) {
    document.getElementById("errInfo").innerText = "Error: " + e;
  }
  document.getElementById("scanBtn").innerText = "🔍";
}

async function jumpToError(path, line) {
  await openFile(path);
  setTimeout(function() {
    if (cm && line) {
      cm.setCursor({ line: line - 1, ch: 0 });
      cm.focus();
      var coords = cm.charCoords({ line: line - 1, ch: 0 }, "local");
      cm.scrollTo(null, coords.top - 80);
    }
  }, 400);
}

function clearTerminal() { document.getElementById("terminal-output").innerText = "$ Terminal cleared\n"; }
function showTermHelp() { document.getElementById("termHelpModal").classList.add("show"); }
function termKey(e) {
  if (e.key === "Enter") runCmd();
  else if (e.key === "ArrowUp") {
    e.preventDefault();
    if (cmdHistory.length && histIdx < cmdHistory.length - 1) {
      histIdx++;
      document.getElementById("cmd").value = cmdHistory[cmdHistory.length - 1 - histIdx];
    }
  } else if (e.key === "ArrowDown") {
    e.preventDefault();
    if (histIdx > 0) {
      histIdx--;
      document.getElementById("cmd").value = cmdHistory[cmdHistory.length - 1 - histIdx];
    } else {
      histIdx = -1;
      document.getElementById("cmd").value = "";
    }
  }
}
async function runCmd() {
  var cmd = document.getElementById("cmd").value.trim();
  if (!cmd) return;
  cmdHistory.push(cmd);
  histIdx = -1;
  var out = document.getElementById("terminal-output");
  out.innerText += "\n$ " + cmd + "\n";
  document.getElementById("cmd").value = "";
  out.scrollTop = out.scrollHeight;
  try {
    var r = await fetch("/api/run-command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project: PROJECT, cmd: cmd })
    });
    var d = await r.json();
    if (d.stdout) out.innerText += d.stdout;
    if (d.stderr) out.innerText += "\n[stderr]\n" + d.stderr;
    if (d.error) out.innerText += "\n[error] " + d.error;
    out.innerText += "\n[exit " + (d.returncode != null ? d.returncode : "?") + "]\n";
    out.scrollTop = out.scrollHeight;
  } catch (e) {
    out.innerText += "\n[error] " + e + "\n";
  }
}

async function runCurrent() {
  if (activeTabIdx < 0) { toast("Open a file first", "error"); return; }
  if (cm) await saveFile(true);
  document.querySelectorAll(".panel").forEach(function(p) { p.classList.remove("active"); });
  document.getElementById("panel-output").classList.add("active");
  var path = openTabs[activeTabIdx].path;
  var outBox = document.getElementById("output-box");
  outBox.innerText = "Running " + path + "...\n\n";
  try {
    var r = await fetch("/api/run-code", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project: PROJECT, path: path })
    });
    var d = await r.json();
    document.getElementById("run-info").innerHTML = "<b>File:</b> " + esc(path) + " | <b>Lang:</b> " + esc(d.language || "?") + " | <b>Exit:</b> " + (d.returncode != null ? d.returncode : "?");
    var text = "";
    if (d.command) text += "$ " + d.command + "\n\n";
    if (d.stdout) text += d.stdout;
    if (d.stderr) text += "\n[stderr]\n" + d.stderr;
    if (d.error) text += "\n[error] " + d.error;
    outBox.innerText = text || "(no output)";
  } catch (e) {
    outBox.innerText = "[error] " + e;
  }
}

async function refreshPreview() {
  var box = document.getElementById("previewContent");
  box.innerHTML = '<p style="text-align:center;color:#64748b;padding:30px">Loading...</p>';
  try {
    var candidates = ["app/src/main/res/layout/activity_main.xml", "res/layout/activity_main.xml"];
    var content = null;
    for (var i = 0; i < candidates.length; i++) {
      var r = await fetch("/api/file-content/" + encodeURIComponent(PROJECT) + "?path=" + encodeURIComponent(candidates[i]));
      if (r.ok) {
        var d = await r.json();
        content = d.content;
        break;
      }
    }
    if (!content && activeTabIdx >= 0 && openTabs[activeTabIdx].path.endsWith(".xml")) {
      content = cm ? cm.getValue() : openTabs[activeTabIdx].content;
    }
    if (!content) {
      box.innerHTML = '<p style="text-align:center;color:#64748b;padding:40px">No layout found</p>';
      return;
    }
    box.innerHTML = renderAndroidXml(content);
  } catch (e) {
    box.innerHTML = '<p style="color:#f87171">Error</p>';
  }
}
function renderAndroidXml(xmlStr) {
  try {
    var parser = new DOMParser();
    var doc = parser.parseFromString(xmlStr, "text/xml");
    var root = doc.documentElement;
    if (!root || root.tagName === "parsererror") return '<p style="color:#f87171">Invalid XML</p>';
    return renderNode(root);
  } catch (e) {
    return '<p style="color:#f87171">Parse error</p>';
  }
}
function renderNode(node) {
  if (node.nodeType !== 1) return "";
  var tag = node.tagName.replace(/^.*:/, "");
  var attrs = {};
  if (node.attributes) {
    for (var i = 0; i < node.attributes.length; i++) {
      var a = node.attributes[i];
      attrs[a.name.replace(/^android:/, "").replace(/^app:/, "")] = a.value;
    }
  }
  var children = "";
  for (var j = 0; j < node.childNodes.length; j++) children += renderNode(node.childNodes[j]);
  if (tag === "TextView" || tag === "textView") return '<div style="margin:6px 0;color:#fff">' + esc(attrs.text || attrs.hint || "Text") + '</div>';
  if (tag === "Button" || tag === "button") return '<button style="width:100%;padding:12px;margin:8px 0;border:0;border-radius:10px;background:#3b82f6;color:#fff">' + esc(attrs.text || "Button") + '</button>';
  if (tag === "EditText" || tag === "editText") return '<input style="width:100%;padding:12px;margin:8px 0;border-radius:10px;border:1px solid #334155;background:#1e293b;color:#fff" placeholder="' + esc(attrs.hint || "") + '">';
  if (tag === "LinearLayout" || tag === "ScrollView" || tag === "FrameLayout" || tag === "RelativeLayout") return '<div>' + children + '</div>';
  return '<div>' + children + '</div>';
}

function formatTime(sec) {
  sec = Math.floor(sec);
  if (sec < 60) return sec + "s";
  return Math.floor(sec / 60) + "m " + (sec % 60) + "s";
}
function startElapsedTimer() {
  if (elapsedTimer) clearInterval(elapsedTimer);
  elapsedTimer = setInterval(function() {
    var el = (Date.now() - buildStartTime) / 1000;
    var elEl = document.getElementById("statElapsed");
    if (elEl) elEl.innerText = formatTime(el);
  }, 500);
}
function processBuildLine(line) {
  var log = document.getElementById("buildLog");
  var cls = "";
  if (line.indexOf("BUILD SUCCESSFUL") !== -1) cls = "color:#4ade80";
  else if (line.indexOf("BUILD FAILED") !== -1 || line.indexOf("error:") !== -1) cls = "color:#f87171";
  else if (line.indexOf("> Task") !== -1) cls = "color:#fbbf24";
  log.innerHTML += "\n<span style='" + cls + "'>" + esc(line) + "</span>";
  log.scrollTop = log.scrollHeight;
  var m = line.match(/^>\s+Task\s+(:[\w:]+)/);
  if (m) {
    tasksSeen++;
    document.getElementById("currentTask").innerText = "▶ " + m[1];
    var pct = Math.min(95, Math.round(tasksSeen / EST_TOTAL * 100));
    document.getElementById("buildProgressBar").style.width = pct + "%";
    document.getElementById("buildProgressText").innerText = pct + "%";
  }
  if (line.indexOf("BUILD SUCCESSFUL") !== -1) {
    document.getElementById("buildProgressBar").style.width = "100%";
    document.getElementById("buildProgressText").innerText = "100%";
    document.getElementById("currentTask").innerText = "✅ Build complete";
  }
  if (line.indexOf("BUILD FAILED") !== -1) {
    document.getElementById("currentTask").innerText = "❌ Build failed";
  }
}
async function pollBuild() {
  if (!buildId) return;
  try {
    var r = await fetch("/api/build-poll/" + buildId + "?since=" + lastLineIdx);
    var d = await r.json();
    if (d.lines && d.lines.length) {
      d.lines.forEach(processBuildLine);
      lastLineIdx = d.total;
    }
    if (d.status === "done") {
      clearInterval(buildPollTimer);
      buildPollTimer = null;
      if (elapsedTimer) { clearInterval(elapsedTimer); elapsedTimer = null; }
      if (d.success && d.apk_path) {
        document.getElementById("buildProgressBar").style.width = "100%";
        document.getElementById("buildProgressText").innerText = "100%";
        document.getElementById("currentTask").innerText = "✅ Build successful";
        document.getElementById("buildStatusMsg").innerText = "✓ APK ready!";
        document.getElementById("buildStatusMsg").style.color = "#4ade80";
        document.getElementById("apk-box").style.display = "block";
        document.getElementById("apkDownloadBtn").onclick = function() {
          location.href = "/api/download-apk/" + encodeURIComponent(PROJECT);
        };
        toast("APK Ready!");
      } else {
        document.getElementById("currentTask").innerText = "❌ Build failed";
        document.getElementById("buildStatusMsg").innerText = "✗ Failed";
        document.getElementById("buildStatusMsg").style.color = "#f87171";
        toast("Build failed", "error");
      }
    }
  } catch (e) {}
}
async function buildApk() {
  if (!confirm("Build APK?\nFirst build: 1-3 min\nNext: 20-40 sec")) return;
  switchPanel("build", document.querySelector('[data-panel="build"]'));
  document.getElementById("buildLog").innerHTML = "$ Starting build...";
  document.getElementById("buildProgressBar").style.width = "0%";
  document.getElementById("buildProgressText").innerText = "0%";
  document.getElementById("currentTask").innerHTML = "Starting...";
  document.getElementById("buildStatusMsg").innerText = "Starting...";
  document.getElementById("buildStatusMsg").style.color = "#94a3b8";
  document.getElementById("apk-box").style.display = "none";
  tasksSeen = 0;
  lastLineIdx = 0;
  EST_TOTAL = 32;
  try {
    var r = await fetch("/api/build-start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project: PROJECT })
    });
    var d = await r.json();
    if (!r.ok) { toast(d.error || "Error", "error"); return; }
    buildId = d.build_id;
    buildStartTime = Date.now();
    startElapsedTimer();
    if (buildPollTimer) clearInterval(buildPollTimer);
    buildPollTimer = setInterval(pollBuild, 700);
    pollBuild();
  } catch (e) { toast("Error: " + e, "error"); }
}
async function adbInstall() {
  toast("Trying ADB install...");
  try {
    var r = await fetch("/api/adb-install", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project: PROJECT })
    });
    var d = await r.json();
    if (r.ok && d.success) toast("Installed via ADB!");
    else toast(d.error || "ADB failed", "error");
  } catch (e) { toast("ADB error", "error"); }
}
async function exportZip() {
  toast("Creating ZIP...");
  location.href = "/api/export-zip/" + encodeURIComponent(PROJECT);
}

function openSettings() {
  document.getElementById("fontSize").value = localStorage.getItem("fontSize") || 13;
  document.getElementById("autoSave").value = localStorage.getItem("autoSave") || "off";
  document.getElementById("cmTheme").value = localStorage.getItem("cmTheme") || "dracula";
  document.getElementById("settingsModal").classList.add("show");
}
function applyFontSize(v) {
  localStorage.setItem("fontSize", v);
  if (cm) cm.getWrapperElement().style.fontSize = v + "px";
}
function changeTheme(t) {
  localStorage.setItem("cmTheme", t);
  if (cm) cm.setOption("theme", t);
}
function openPkgRename() { document.getElementById("pkgModal").classList.add("show"); }
async function doPkgRename() {
  var oldP = document.getElementById("oldPkg").value.trim();
  var newP = document.getElementById("newPkg").value.trim();
  if (!oldP || !newP) { toast("Fill both", "error"); return; }
  try {
    var r = await fetch("/api/rename-package", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project: PROJECT, old: oldP, new: newP })
    });
    var d = await r.json();
    if (r.ok) {
      toast("Updated " + d.updated + " files");
      document.getElementById("pkgModal").classList.remove("show");
    } else toast(d.error || "Fail", "error");
  } catch (e) { toast("Error", "error"); }
}

try {
  loadFiles("");
  setTimeout(function() {
    try { scanAllErrors(); } catch (e) {}
  }, 1500);
} catch (e) {
  var fl = document.getElementById("file-list");
  if (fl) fl.innerHTML = '<div style="color:#f87171;padding:20px">JS Error: ' + e.message + '</div>';
}
</script>
</body>
</html>
'''

# ========== ROUTES ==========
@app.route("/")
def home():
    return HOME_HTML

@app.route("/api/status")
def api_status():
    projects = [p for p in PROJECTS_DIR.iterdir() if p.is_dir()]
    langs = set(v["name"] for v in LANGUAGES.values())
    return jsonify({"server": "online", "port": PORT, "projects": len(projects), "language_count": len(langs)})

@app.route("/api/projects", methods=["GET"])
def get_projects():
    result = []
    for project in sorted(PROJECTS_DIR.iterdir()):
        if not project.is_dir(): continue
        info_file = project / "project.json"
        if info_file.exists():
            try: info = json.loads(info_file.read_text(encoding="utf-8"))
            except: info = {"name": project.name, "package": "?", "language": "?"}
        else: info = {"name": project.name, "package": "?", "language": "?"}
        result.append(info)
    return jsonify({"projects": result})

@app.route("/api/projects", methods=["POST"])
def create_project_api():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    package = str(data.get("package", "")).strip()
    language = str(data.get("language", "java")).strip().lower()
    template = str(data.get("template", "empty")).strip().lower()
    if not name: return jsonify({"error": "Name required"}), 400
    if not package: return jsonify({"error": "Package required"}), 400
    if not valid_package(package): return jsonify({"error": "Invalid package"}), 400
    if language not in ["java", "kotlin"]: return jsonify({"error": "Invalid language"}), 400
    if template not in ["empty", "login", "list"]: template = "empty"
    try:
        p = create_android_project(name, package, language, template)
        return jsonify({"success": True, "path": str(p)})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/projects/<path:name>", methods=["DELETE"])
def delete_project(name):
    project = safe_project(name)
    if project is None: return jsonify({"error": "Invalid"}), 400
    if not project.exists(): return jsonify({"error": "Not found"}), 404
    try:
        shutil.rmtree(str(project))
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
        return jsonify({"error": "Invalid"}), 400
    sub = request.args.get("path", "")
    sort_by = request.args.get("sort", "name")
    target = safe_subpath(project, sub)
    if target is None or not target.is_dir():
        return jsonify({"error": "Invalid path"}), 400
    files = []
    try:
        for p in target.iterdir():
            try:
                rel = str(p.relative_to(project))
                st = p.stat()
                files.append({
                    "name": p.name, "path": rel,
                    "type": "directory" if p.is_dir() else "file",
                    "size": st.st_size if p.is_file() else 0,
                    "size_h": human_size(st.st_size) if p.is_file() else "-",
                    "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    "mtime_ts": st.st_mtime
                })
            except: continue
        if sort_by == "size":
            files.sort(key=lambda x: (x["type"] != "directory", -x["size"], x["name"].lower()))
        elif sort_by == "date":
            files.sort(key=lambda x: (x["type"] != "directory", -x["mtime_ts"]))
        else:
            files.sort(key=lambda x: (x["type"] != "directory", x["name"].lower()))
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"project": name, "current": sub, "files": files})

@app.route("/api/search/<path:name>")
def search_files(name):
    project = safe_project(name)
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    q = request.args.get("q", "").strip().lower()
    if not q: return jsonify({"results": []})
    results = []
    for p in project.rglob("*"):
        if not p.is_file(): continue
        parts = str(p).split(os.sep)
        if any(x in ("build", ".gradle", ".git") for x in parts): continue
        try:
            rel = str(p.relative_to(project))
            if q in p.name.lower() or q in rel.lower():
                results.append({"name": p.name, "path": rel})
        except: continue
        if len(results) > 60: break
    return jsonify({"results": results})

@app.route("/api/file-content/<path:name>", methods=["GET", "POST"])
def file_content(name):
    project = safe_project(name)
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    sub = request.args.get("path", "")
    target = safe_subpath(project, sub)
    if target is None or not target.is_file():
        return jsonify({"error": "Not found"}), 404
    if request.method == "GET":
        try:
            return jsonify({"content": target.read_text(encoding="utf-8", errors="replace"), "path": sub})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    data = request.get_json(silent=True) or {}
    try:
        target.write_text(data.get("content", ""), encoding="utf-8")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/file-operation", methods=["POST"])
def file_operation():
    data = request.get_json(silent=True) or {}
    project = safe_project(data.get("project", ""))
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    action = data.get("action", "")
    path = data.get("path", "")
    target = safe_subpath(project, path)
    if target is None:
        return jsonify({"error": "Invalid path"}), 400
    try:
        if action == "create-file":
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists(): return jsonify({"error": "Exists"}), 400
            target.write_text(data.get("content", ""), encoding="utf-8")
            return jsonify({"success": True})
        if action == "create-folder":
            target.mkdir(parents=True, exist_ok=True)
            return jsonify({"success": True})
        if action == "delete":
            if not target.exists(): return jsonify({"error": "Not found"}), 404
            if target == project: return jsonify({"error": "Cannot delete root"}), 400
            if target.is_dir(): shutil.rmtree(target)
            else: target.unlink()
            return jsonify({"success": True})
        if action == "rename":
            nn = data.get("newName", "")
            if not nn: return jsonify({"error": "New name required"}), 400
            nt = safe_subpath(project, nn)
            if nt is None: return jsonify({"error": "Invalid"}), 400
            if nt.exists(): return jsonify({"error": "Target exists"}), 400
            nt.parent.mkdir(parents=True, exist_ok=True)
            target.rename(nt)
            return jsonify({"success": True})
        return jsonify({"error": "Unknown"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/upload/<path:name>", methods=["POST"])
def upload_file(name):
    project = safe_project(name)
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    sub = request.form.get("path", "")
    target_dir = safe_subpath(project, sub)
    if target_dir is None or not target_dir.is_dir():
        return jsonify({"error": "Invalid folder"}), 400
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty"}), 400
    fname = secure_filename(f.filename)
    dest = target_dir / fname
    f.save(str(dest))
    return jsonify({"success": True})

@app.route("/api/rename-package", methods=["POST"])
def rename_package():
    data = request.get_json(silent=True) or {}
    project = safe_project(data.get("project", ""))
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    old_pkg = data.get("old", "").strip()
    new_pkg = data.get("new", "").strip()
    if not old_pkg or not new_pkg or not valid_package(new_pkg):
        return jsonify({"error": "Invalid package"}), 400
    count = 0
    for p in project.rglob("*"):
        if not p.is_file(): continue
        if p.suffix.lower() not in (".java", ".kt", ".xml", ".gradle", ".json", ".properties"): continue
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
            if old_pkg in txt:
                p.write_text(txt.replace(old_pkg, new_pkg), encoding="utf-8")
                count += 1
        except: continue
    info_file = project / "project.json"
    if info_file.exists():
        try:
            info = json.loads(info_file.read_text(encoding="utf-8"))
            info["package"] = new_pkg
            info_file.write_text(json.dumps(info, indent=4), encoding="utf-8")
        except: pass
    return jsonify({"success": True, "updated": count})

@app.route("/api/apks")
def list_apks():
    apks = []
    for p in sorted(APKS_DIR.glob("*.apk"), key=lambda x: -x.stat().st_mtime):
        st = p.stat()
        apks.append({"name": p.name, "size": human_size(st.st_size),
                     "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")})
    return jsonify({"apks": apks})

@app.route("/api/apks/<path:name>", methods=["DELETE"])
def delete_apk(name):
    p = APKS_DIR / name
    if p.exists() and p.is_file():
        p.unlink()
        return jsonify({"success": True})
    return jsonify({"error": "Not found"}), 404

@app.route("/api/download-saved-apk/<path:name>")
def download_saved_apk(name):
    p = APKS_DIR / name
    if p.exists():
        return send_file(str(p), as_attachment=True, download_name=name)
    return "Not found", 404

def read_file_line(path, line_num):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        if 1 <= line_num <= len(lines):
            return lines[line_num - 1].rstrip()[:300]
    except: pass
    return ""

def parse_errors(lang_name, output, file_path=None):
    errors = []
    lines_seen = set()
    for line in output.splitlines():
        line = line.strip()
        if not line: continue
        m = re.match(r'^[^:]+:(\d+):(\d+):\s*(error|fatal error):\s*(.+)', line)
        if m:
            ln = int(m.group(1))
            errors.append({"line": ln, "col": int(m.group(2)), "message": m.group(4)[:200],
                           "code": read_file_line(file_path, ln) if file_path else ""})
            continue
        m = re.match(r'^\s*File\s+"[^"]+",\s+line\s+(\d+)', line)
        if m:
            ln = int(m.group(1))
            if ln not in lines_seen:
                lines_seen.add(ln)
                errors.append({"line": ln, "col": 1, "message": "Syntax error",
                               "code": read_file_line(file_path, ln) if file_path else ""})
    seen = {}
    for e in errors:
        key = e["line"] if e["line"] > 0 else e["message"][:40]
        if key not in seen: seen[key] = e
    return list(seen.values())

@app.route("/api/check-file/<path:name>")
def check_file(name):
    project = safe_project(name)
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    target = safe_subpath(project, request.args.get("path", ""))
    if target is None or not target.is_file():
        return jsonify({"error": "Not found"}), 404
    ext = target.suffix.lower()
    lang = LANGUAGES.get(ext)
    if not lang or not lang["check"]:
        return jsonify({"errors": [], "language": lang["name"] if lang else "?"})
    cmd = lang["check"].replace("{file}", str(target))
    try:
        result = subprocess.run(cmd, shell=True, cwd=str(target.parent), capture_output=True, text=True, timeout=60)
        output = (result.stdout or "") + "\n" + (result.stderr or "")
        if result.returncode == 0:
            return jsonify({"errors": [], "language": lang["name"]})
        return jsonify({"errors": parse_errors(lang["name"], output, str(target)), "language": lang["name"]})
    except Exception as e:
        return jsonify({"errors": [], "error": str(e)})

@app.route("/api/scan-errors/<path:name>")
def scan_errors(name):
    project = safe_project(name)
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    results, scanned = [], 0
    for path in sorted(project.rglob("*")):
        if not path.is_file(): continue
        parts = str(path).split(os.sep)
        if any(p in ("build", ".gradle", ".git") for p in parts): continue
        try:
            if path.stat().st_size > 500000: continue
        except: continue
        ext = path.suffix.lower()
        lang = LANGUAGES.get(ext)
        if not lang or not lang["check"]: continue
        scanned += 1
        rel = str(path.relative_to(project))
        cmd = lang["check"].replace("{file}", str(path))
        try:
            r = subprocess.run(cmd, shell=True, cwd=str(path.parent), capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                out = (r.stdout or "") + "\n" + (r.stderr or "")
                errs = parse_errors(lang["name"], out, str(path))
                if errs:
                    results.append({"path": rel, "language": lang["name"], "errors": errs})
        except: continue
    return jsonify({"scanned": scanned, "results": results})

@app.route("/api/run-command", methods=["POST"])
def run_command():
    data = request.get_json(silent=True) or {}
    project = safe_project(data.get("project", ""))
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    cmd = data.get("cmd", "").strip()
    if not cmd: return jsonify({"error": "Empty"}), 400
    blocked = ["rm -rf /", "mkfs", "dd if=", ":(){", "shutdown", "reboot"]
    for b in blocked:
        if b in cmd: return jsonify({"error": "Blocked"}), 403
    try:
        r = subprocess.run(cmd, shell=True, cwd=str(project), capture_output=True, text=True, timeout=180)
        return jsonify({"stdout": r.stdout, "stderr": r.stderr, "returncode": r.returncode})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/run-code", methods=["POST"])
def run_code():
    data = request.get_json(silent=True) or {}
    project = safe_project(data.get("project", ""))
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    target = safe_subpath(project, data.get("path", ""))
    if target is None or not target.is_file():
        return jsonify({"error": "Not found"}), 404
    ext = target.suffix.lower()
    lang = LANGUAGES.get(ext)
    if not lang or lang["run"] is None:
        return jsonify({"error": "Not runnable"}), 400
    cmd = lang["run"].replace("{file}", str(target))
    try:
        r = subprocess.run(cmd, shell=True, cwd=str(target.parent), capture_output=True, text=True, timeout=120)
        return jsonify({"language": lang["name"], "command": cmd, "stdout": r.stdout, "stderr": r.stderr, "returncode": r.returncode})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
        if B["success"] and B["apk_path"]:
            try:
                src = Path(B["apk_path"])
                shutil.copy2(src, APKS_DIR / (project.name + "-" + src.name))
            except: pass
    except Exception as e:
        B["output"].append("[build error] " + str(e))
        B["status"] = "done"
        B["success"] = False
        B["returncode"] = -1

@app.route("/api/build-start", methods=["POST"])
def build_start():
    data = request.get_json(silent=True) or {}
    project = safe_project(data.get("project", ""))
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    env = os.environ.copy()
    sdk = Path.home() / "android-sdk"
    if sdk.exists():
        env["ANDROID_HOME"] = str(sdk)
        env["ANDROID_SDK_ROOT"] = str(sdk)
    env["PATH"] = str(sdk / "platform-tools") + ":" + TERMUX_PREFIX + "/bin:" + env.get("PATH", "")
    build_id = str(uuid.uuid4())
    BUILDS[build_id] = {"output": [], "status": "running", "apk_path": None, "returncode": None, "success": None}
    t = threading.Thread(target=build_worker, args=(build_id, project, env), daemon=True)
    t.start()
    return jsonify({"build_id": build_id, "status": "started"})

@app.route("/api/build-poll/<build_id>")
def build_poll(build_id):
    B = BUILDS.get(build_id)
    if not B: return jsonify({"error": "Not found"}), 404
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
    if not apks: return "No APK", 404
    return send_file(str(apks[0]), as_attachment=True, download_name=apks[0].name)

@app.route("/api/export-zip/<path:name>")
def export_zip(name):
    project = safe_project(name)
    if project is None or not project.exists(): return "Invalid", 400
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in project.rglob("*"):
            if f.is_file():
                parts = str(f).split(os.sep)
                if any(p in ("build", ".gradle") for p in parts): continue
                zf.write(f, f.relative_to(project))
    mem.seek(0)
    return send_file(mem, as_attachment=True, download_name=name + ".zip", mimetype="application/zip")

@app.route("/api/adb-install", methods=["POST"])
def adb_install():
    data = request.get_json(silent=True) or {}
    project = safe_project(data.get("project", ""))
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    apks = list(project.glob("app/build/outputs/apk/**/*.apk"))
    if not apks:
        return jsonify({"error": "No APK. Build first."}), 404
    try:
        r = subprocess.run(["adb", "install", "-r", str(apks[0])], capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            return jsonify({"success": True})
        return jsonify({"error": r.stderr or r.stdout or "Failed"}), 500
    except FileNotFoundError:
        return jsonify({"error": "adb not found"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    print("")
    print("====================================")
    print("⚡ ZIHAD MOBILE IDE v9.2 FULL")
    print("====================================")
    print("Projects :", PROJECTS_DIR)
    print("APKs     :", APKS_DIR)
    print("Server   : http://127.0.0.1:%d" % PORT)
    print("====================================")
    print("")
    app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)
