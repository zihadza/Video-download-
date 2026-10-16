# ============================================================
# ZIHAD MOBILE IDE v10.0 — FULL EDITION
# PART 1/3 : Core + Templates + Home Page
# ============================================================
from flask import Flask, jsonify, request, send_file, Response
from pathlib import Path
import json, re, subprocess, shutil, os, threading, time, uuid, zipfile, io, sys, base64, hashlib
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200MB upload

# ---------------- CONFIG ----------------
BASE_DIR       = Path.home() / "Projects" / "ZihadIDE"
PROJECTS_DIR   = BASE_DIR / "projects"
APKS_DIR       = BASE_DIR / "apks"
HISTORY_DIR    = BASE_DIR / "history"
BACKUP_DIR     = BASE_DIR / "backups"
SIGNED_DIR     = BASE_DIR / "signed"
TEMPLATES_DIR  = BASE_DIR / "template_gallery"
for d in [PROJECTS_DIR, APKS_DIR, HISTORY_DIR, BACKUP_DIR, SIGNED_DIR, TEMPLATES_DIR]:
    d.mkdir(parents=True, exist_ok=True)

SAVED_COMMANDS_FILE = BASE_DIR / "saved_commands.json"
RECENT_FILES_FILE   = BASE_DIR / "recent_files.json"
KEYSTORE_FILE       = BASE_DIR / "keystore.json"
ENV_FILE            = BASE_DIR / "env_vault.json"

PORT = 3090
TERMUX_PREFIX = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
BUILDS = {}
LOGCAT_PROCS = {}
PTY_SESSIONS = {}

# ---------------- LANGUAGES ----------------
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

# ---------------- GRADLE HINTS ----------------
GRADLE_HINTS = {
    "SDK location not found": "Create local.properties with sdk.dir=... or install Android SDK",
    "Could not find": "Run `gradle --refresh-dependencies` or check internet",
    "Unsupported class file major version": "Update Java version or Gradle wrapper",
    "Could not resolve": "Check internet and dependency versions",
    "processDebugResources": "Check XML files in res/ for errors",
    "Duplicate class": "Remove duplicate dependency with exclude",
    "AAPT2": "Run `pkg install aapt2` in Termux",
    "compileSdkVersion": "Set compileSdk 34 in build.gradle",
    "No signature of method": "Gradle DSL mismatch. Check plugin version",
    "Could not download": "Check internet connection",
    "Execution failed": "See error above for detail",
    "OutOfMemory": "Increase org.gradle.jvmargs in gradle.properties",
    "MANIFEST": "AndroidManifest.xml has invalid entry",
    "package ": "Package name conflict",
    "minSdk": "minSdk must be >= 21",
    "Duplicate resources": "Multiple res files with same name",
    "library": "Missing library dependency",
}

def suggest_fix(line):
    for k, v in GRADLE_HINTS.items():
        if k.lower() in line.lower():
            return v
    return None

# ---------------- HELPERS ----------------
def load_json(p, default=None):
    try: return json.loads(Path(p).read_text(encoding="utf-8"))
    except: return default if default is not None else {}

def save_json(p, data):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(data, indent=2), encoding="utf-8")

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

def backup_file_version(project_name, file_path, content):
    """Save a backup version of file (max 20 versions kept)."""
    key = f"{project_name}__{str(file_path).replace('/', '_').replace(chr(92), '_')}"
    hist_dir = HISTORY_DIR / key
    hist_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    try:
        (hist_dir / f"{ts}.bak").write_text(content, encoding="utf-8")
    except: return
    versions = sorted(hist_dir.iterdir(), key=lambda x: -x.stat().st_mtime)
    for v in versions[20:]:
        try: v.unlink()
        except: pass

def add_recent(project, path):
    data = load_json(RECENT_FILES_FILE, {"items": []})
    items = [i for i in data.get("items", [])
             if not (i["project"] == project and i["path"] == path)]
    items.insert(0, {"project": project, "path": path, "ts": time.time()})
    data["items"] = items[:40]
    save_json(RECENT_FILES_FILE, data)

def get_saved_commands():
    return load_json(SAVED_COMMANDS_FILE, {"items": []}).get("items", [])

def save_saved_commands(items):
    save_json(SAVED_COMMANDS_FILE, {"items": items[:60]})

# ---------------- PROJECT CREATION (with all templates) ----------------
def create_android_project(name, package, language, template="empty"):
    project = PROJECTS_DIR / name
    if project.exists():
        raise ValueError("Project already exists")
    pkg_path = package.replace(".", "/")
    main_dir  = project / "app" / "src" / "main"
    java_dir  = main_dir / "java" / pkg_path
    kotlin_dir= main_dir / "kotlin" / pkg_path
    res_dir   = main_dir / "res"
    values_dir= res_dir / "values"
    layout_dir= res_dir / "layout"
    mipmap_dir= res_dir / "mipmap-hdpi"
    for d in [java_dir, kotlin_dir, values_dir, layout_dir, mipmap_dir,
              res_dir / "drawable", main_dir / "assets", main_dir / "jniLibs"]:
        d.mkdir(parents=True, exist_ok=True)

    # ---- TEMPLATE: LOGIN ----
    def login_tpl():
        java = f'''package {package};
import android.app.Activity; import android.os.Bundle;
import android.widget.*;
public class MainActivity extends Activity {{
    @Override protected void onCreate(Bundle s) {{
        super.onCreate(s); setContentView(R.layout.activity_main);
        EditText email = findViewById(R.id.email), password = findViewById(R.id.password);
        Button btn = findViewById(R.id.loginBtn);
        btn.setOnClickListener(v -> {{
            String e = email.getText().toString().trim(), p = password.getText().toString().trim();
            if (e.isEmpty() || p.isEmpty())
                Toast.makeText(this, "Fill all fields", Toast.LENGTH_SHORT).show();
            else Toast.makeText(this, "Welcome " + e, Toast.LENGTH_SHORT).show();
        }});
    }}
}}'''
        layout = '''<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent" android:layout_height="match_parent"
    android:orientation="vertical" android:gravity="center" android:padding="32dp" android:background="#0f172a">
    <TextView android:layout_width="wrap_content" android:layout_height="wrap_content" android:text="Welcome Back"
        android:textSize="28sp" android:textColor="#ffffff" android:layout_marginBottom="32dp"/>
    <EditText android:id="@+id/email" android:layout_width="match_parent" android:layout_height="wrap_content"
        android:hint="Email" android:inputType="textEmailAddress" android:textColor="#fff" android:textColorHint="#94a3b8"
        android:background="#1e293b" android:padding="16dp" android:layout_marginBottom="16dp"/>
    <EditText android:id="@+id/password" android:layout_width="match_parent" android:layout_height="wrap_content"
        android:hint="Password" android:inputType="textPassword" android:textColor="#fff" android:textColorHint="#94a3b8"
        android:background="#1e293b" android:padding="16dp" android:layout_marginBottom="24dp"/>
    <Button android:id="@+id/loginBtn" android:layout_width="match_parent" android:layout_height="wrap_content"
        android:text="Login" android:backgroundTint="#2563eb" android:textColor="#fff" android:padding="14dp"/>
</LinearLayout>'''
        return java, layout

    # ---- TEMPLATE: LIST ----
    def list_tpl():
        java = f'''package {package};
import android.app.Activity; import android.os.Bundle; import android.widget.*;
public class MainActivity extends Activity {{
    @Override protected void onCreate(Bundle s) {{
        super.onCreate(s); setContentView(R.layout.activity_main);
        ListView list = findViewById(R.id.listView);
        String[] items = {{"Item 1","Item 2","Item 3","Item 4","Item 5"}};
        list.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_list_item_1, items));
        list.setOnItemClickListener((p,v,pos,id) -> Toast.makeText(this, "Clicked: " + items[pos], Toast.LENGTH_SHORT).show());
    }}
}}'''
        layout = '''<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent" android:layout_height="match_parent"
    android:orientation="vertical" android:background="#0f172a">
    <TextView android:layout_width="match_parent" android:layout_height="wrap_content" android:text="My List"
        android:textSize="22sp" android:textColor="#fff" android:padding="16dp" android:background="#1e293b"/>
    <ListView android:id="@+id/listView" android:layout_width="match_parent" android:layout_height="match_parent"
        android:divider="#334155" android:dividerHeight="1dp"/>
</LinearLayout>'''
        return java, layout

    # ---- TEMPLATE: SPLASH ----
    def splash_tpl():
        java = f'''package {package};
import android.app.Activity; import android.os.Bundle;
import android.content.Intent; import android.os.Handler; import android.os.Looper;
public class MainActivity extends Activity {{
    @Override protected void onCreate(Bundle s) {{
        super.onCreate(s); setContentView(R.layout.activity_main);
        new Handler(Looper.getMainLooper()).postDelayed(() -> {{
            startActivity(new Intent(this, HomeActivity.class)); finish();
        }}, 2000);
    }}
}}'''
        layout = '''<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent" android:layout_height="match_parent"
    android:orientation="vertical" android:gravity="center" android:background="#2563eb">
    <TextView android:layout_width="wrap_content" android:layout_height="wrap_content"
        android:text="&#9889;" android:textSize="72sp"/>
    <TextView android:layout_width="wrap_content" android:layout_height="wrap_content"
        android:text="@string/app_name" android:textColor="#ffffff" android:textSize="24sp" android:textStyle="bold"/>
</LinearLayout>'''
        home_java = f'''package {package};
import android.app.Activity; import android.os.Bundle; import android.widget.TextView; import android.view.Gravity;
public class HomeActivity extends Activity {{
    @Override protected void onCreate(Bundle s) {{ super.onCreate(s);
        TextView tv = new TextView(this); tv.setText("Home"); tv.setTextSize(24);
        tv.setTextColor(0xFFFFFFFF); tv.setBackgroundColor(0xFF0F172A);
        tv.setGravity(Gravity.CENTER); setContentView(tv);
    }}
}}'''
        home_kt = f'''package {package}
import android.app.Activity
import android.os.Bundle
import android.view.Gravity
import android.widget.TextView
class HomeActivity : Activity() {{
    override fun onCreate(s: Bundle?) {{ super.onCreate(s)
        val tv = TextView(this).apply {{
            text = "Home"; textSize = 24f; setTextColor(0xFFFFFFFF.toInt())
            setBackgroundColor(0xFF0F172A.toInt()); gravity = Gravity.CENTER
        }}
        setContentView(tv)
    }}
}}'''
        write_file(java_dir / "HomeActivity.java", home_java)
        write_file(kotlin_dir / "HomeActivity.kt", home_kt)
        return java, layout

    # ---- TEMPLATE: BOTTOM NAV ----
    def bottom_nav_tpl():
        java = f'''package {package};
import android.app.Activity; import android.os.Bundle; import android.widget.TextView;
public class MainActivity extends Activity {{
    @Override protected void onCreate(Bundle s) {{
        super.onCreate(s); setContentView(R.layout.activity_main);
        TextView content = findViewById(R.id.content);
        int[] btnIds = {{R.id.nav1, R.id.nav2, R.id.nav3}};
        String[] labels = {{"Home", "Search", "Profile"}};
        for (int i = 0; i < btnIds.length; i++) {{
            final int idx = i;
            findViewById(btnIds[i]).setOnClickListener(v -> content.setText(labels[idx]));
        }}
        content.setText(labels[0]);
    }}
}}'''
        layout = '''<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent" android:layout_height="match_parent"
    android:orientation="vertical" android:background="#0f172a">
    <FrameLayout android:layout_width="match_parent" android:layout_height="0dp" android:layout_weight="1">
        <TextView android:id="@+id/content" android:layout_width="wrap_content" android:layout_height="wrap_content"
            android:layout_gravity="center" android:text="Home" android:textColor="#fff" android:textSize="28sp"/>
    </FrameLayout>
    <LinearLayout android:layout_width="match_parent" android:layout_height="60dp" android:background="#1e293b"
        android:orientation="horizontal">
        <Button android:id="@+id/nav1" android:layout_width="0dp" android:layout_weight="1" android:layout_height="match_parent"
            android:text="Home" android:background="@android:color/transparent" android:textColor="#fff"/>
        <Button android:id="@+id/nav2" android:layout_width="0dp" android:layout_weight="1" android:layout_height="match_parent"
            android:text="Search" android:background="@android:color/transparent" android:textColor="#fff"/>
        <Button android:id="@+id/nav3" android:layout_width="0dp" android:layout_weight="1" android:layout_height="match_parent"
            android:text="Profile" android:background="@android:color/transparent" android:textColor="#fff"/>
    </LinearLayout>
</LinearLayout>'''
        return java, layout

    # ---- TEMPLATE: EMPTY ----
    def empty_tpl():
        java = f'''package {package};
import android.app.Activity; import android.os.Bundle; import android.widget.TextView; import android.view.Gravity;
public class MainActivity extends Activity {{
    @Override protected void onCreate(Bundle s) {{ super.onCreate(s);
        TextView tv = new TextView(this); tv.setText("Hello from {name}"); tv.setTextSize(24);
        tv.setTextColor(0xFFFFFFFF); tv.setBackgroundColor(0xFF0F172A);
        tv.setGravity(Gravity.CENTER); setContentView(tv);
    }}
}}'''
        layout = '''<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent" android:layout_height="match_parent"
    android:gravity="center" android:orientation="vertical" android:background="#0f172a">
    <TextView android:id="@+id/titleText" android:layout_width="wrap_content" android:layout_height="wrap_content"
        android:text="@string/app_name" android:textSize="24sp" android:textColor="#ffffff"/>
</LinearLayout>'''
        return java, layout

    tpl_map = {"login": login_tpl, "list": list_tpl, "splash": splash_tpl,
               "bottom_nav": bottom_nav_tpl, "empty": empty_tpl}
    main_java, layout = tpl_map.get(template, empty_tpl)()

    # Simple Kotlin variant
    main_kotlin = f'''package {package}
import android.app.Activity
import android.os.Bundle
import android.widget.TextView
import android.view.Gravity
class MainActivity : Activity() {{
    override fun onCreate(s: Bundle?) {{ super.onCreate(s)
        val tv = TextView(this).apply {{
            text = "Hello from {name}"; textSize = 24f
            setTextColor(0xFFFFFFFF.toInt()); setBackgroundColor(0xFF0F172A.toInt())
            gravity = Gravity.CENTER
        }}
        setContentView(tv)
    }}
}}'''

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
        release {{
            minifyEnabled false
            proguardFiles getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro"
        }}
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
    write_file(project / "app" / "proguard-rules.pro", "# Add ProGuard rules here\n")
    write_file(project / "project.json", json.dumps(project_info, indent=4))
    write_file(project / "hello.py", f'print("Hello from {name}")\n')
    write_file(project / ".gitignore", "build/\n.gradle/\nlocal.properties\n*.iml\n.idea/\n")
    return project


# ============================================================
# HOME PAGE (with theme toggle + backup/restore)
# ============================================================
HOME_HTML = r'''<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>Zihad Mobile IDE v10</title>
<style>
:root{--bg:#070b14;--card:rgba(17,24,39,.8);--border:rgba(55,65,81,.6);--primary:#3b82f6;--text:#f1f5f9;--muted:#94a3b8;--radius:18px}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;min-height:100vh;background-image:radial-gradient(ellipse at 20% 20%,rgba(59,130,246,.12) 0%,transparent 50%),radial-gradient(ellipse at 80% 80%,rgba(139,92,246,.1) 0%,transparent 50%)}
header{padding:16px 20px;background:rgba(15,23,42,.9);backdrop-filter:blur(20px);border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:50;gap:8px;flex-wrap:wrap}
header h1{font-size:1.15rem;font-weight:700;background:linear-gradient(135deg,#60a5fa,#a78bfa);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.container{padding:20px;max-width:720px;margin:0 auto}
.card{background:var(--card);backdrop-filter:blur(16px);border:1px solid var(--border);border-radius:var(--radius);padding:20px;margin-bottom:18px;box-shadow:0 8px 32px rgba(0,0,0,.3)}
h2{font-size:1.05rem;margin-bottom:12px;color:#e2e8f0}
.status-dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#22c55e;margin-right:8px;box-shadow:0 0 10px #22c55e}
button{border:0;border-radius:12px;padding:10px 14px;margin:4px;font-weight:600;font-size:13px;cursor:pointer;color:#fff}
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
.toast.success{border-color:rgba(34,197,94,.5)}.toast.error{border-color:rgba(239,68,68,.5)}
.fab{position:fixed;bottom:28px;right:24px;width:58px;height:58px;border-radius:18px;background:linear-gradient(135deg,#3b82f6,#8b5cf6);display:flex;align-items:center;justify-content:center;font-size:28px;color:#fff;border:0;z-index:40}
.template-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:12px 0}
.template-card{background:rgba(8,15,28,.7);border:2px solid var(--border);border-radius:14px;padding:12px 8px;text-align:center;cursor:pointer;font-size:12px}
.template-card.active{border-color:var(--primary);background:rgba(59,130,246,.12)}
.template-card span{font-size:22px;display:block;margin-bottom:6px}
.apk-item{background:rgba(8,15,28,.55);border:1px solid var(--border);border-radius:12px;padding:12px;margin:7px 0;display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap}
body.light{--bg:#f1f5f9;--card:#fff;--border:#cbd5e1;--text:#0f172a;--muted:#64748b;background-image:none}
body.light .card{background:#fff;color:#0f172a}
body.light input,body.light select{background:#f8fafc;color:#0f172a}
body.light header{background:#fff;color:#0f172a}
body.light .project,body.light .apk-item,body.light .template-card{background:#f8fafc;color:#0f172a}
</style></head>
<body>
<header>
  <h1>⚡ Zihad IDE v10</h1>
  <div style="display:flex;gap:2px;flex-wrap:wrap">
    <button class="btn-ghost" onclick="toggleTheme()" id="themeBtn">🌙</button>
    <button class="btn-ghost" onclick="location.href='/api/backup'">💾</button>
    <button class="btn-ghost upload-btn" style="position:relative;overflow:hidden">📥<input type="file" style="position:absolute;inset:0;opacity:0;cursor:pointer;width:100%" onchange="restoreBackup(this)"></button>
    <button class="btn-ghost" onclick="showApks()">📦</button>
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
      <div class="template-card" data-t="splash" onclick="selectTemplate(this)"><span>✨</span>Splash</div>
      <div class="template-card" data-t="bottom_nav" onclick="selectTemplate(this)"><span>🧭</span>BottomNav</div>
      <div class="template-card" data-t="empty" onclick="selectTemplate(this)"><span>⚡</span>Basic</div>
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
if(localStorage.getItem("theme")==="light")document.body.classList.add("light");
document.getElementById("themeBtn").innerText=document.body.classList.contains("light")?"☀️":"🌙";
function toggleTheme(){document.body.classList.toggle("light");localStorage.setItem("theme",document.body.classList.contains("light")?"light":"dark");document.getElementById("themeBtn").innerText=document.body.classList.contains("light")?"☀️":"🌙";}
function selectTemplate(el){document.querySelectorAll(".template-card").forEach(function(c){c.classList.remove("active")});el.classList.add("active");selectedTemplate=el.dataset.t}
function showCreate(){document.getElementById("createBox").classList.remove("hidden");document.getElementById("apksBox").classList.add("hidden")}
function hideCreate(){document.getElementById("createBox").classList.add("hidden")}
function showApks(){document.getElementById("apksBox").classList.remove("hidden");document.getElementById("createBox").classList.add("hidden");loadApks()}
function hideApks(){document.getElementById("apksBox").classList.add("hidden")}
function toast(msg,type){type=type||"success";var c=document.getElementById("toasts");var t=document.createElement("div");t.className="toast "+type;t.innerText=msg;c.appendChild(t);setTimeout(function(){t.remove()},3000)}
function esc(t){var d=document.createElement("div");d.innerText=t;return d.innerHTML}
async function status(){try{var r=await fetch("/api/status");var d=await r.json();document.getElementById("status").innerText="Port "+d.port+"  •  "+d.projects+" projects  •  "+d.language_count+" languages"}catch(e){document.getElementById("status").innerText="Offline"}}
async function loadProjects(){try{var r=await fetch("/api/projects");var d=await r.json();var box=document.getElementById("projects");if(!d.projects.length){box.innerHTML='<p style="color:#94a3b8;text-align:center;padding:20px">No projects yet</p>';return}box.innerHTML="";d.projects.forEach(function(p){var div=document.createElement("div");div.className="project";div.innerHTML='<div class="project-info"><b>📱 '+esc(p.name)+'</b><span class="badge">'+esc(p.language||"?")+'</span><br><small style="color:#94a3b8">'+esc(p.package||"")+'</small></div><div><button class="btn-primary" onclick="location.href=\'/project/'+encodeURIComponent(p.name)+'\'">Open</button><button class="btn-danger" onclick="deleteProject(\''+esc(p.name)+'\')">🗑</button></div>';box.appendChild(div)})}catch(e){document.getElementById("projects").innerText="Error"}}
async function createProject(){var n=document.getElementById("appName").value.trim();var p=document.getElementById("packageName").value.trim();var l=document.getElementById("language").value;if(!n||!p){msg("Name & Package required",1);return}try{var r=await fetch("/api/projects",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:n,package:p,language:l,template:selectedTemplate})});var d=await r.json();if(!r.ok){msg(d.error||"Failed",1);return}msg("Created!",0);toast("Project created");document.getElementById("appName").value="";document.getElementById("packageName").value="";hideCreate();loadProjects();status()}catch(e){msg("Error",1)}}
async function deleteProject(name){if(!confirm("Delete "+name+"?"))return;try{var r=await fetch("/api/projects/"+encodeURIComponent(name),{method:"DELETE"});if(r.ok){toast("Deleted");loadProjects();status()}else toast("Failed","error")}catch(e){toast("Error","error")}}
async function loadApks(){try{var r=await fetch("/api/apks");var d=await r.json();var box=document.getElementById("apksList");if(!d.apks||!d.apks.length){box.innerHTML='<p style="color:#94a3b8;text-align:center">No APKs</p>';return}box.innerHTML="";d.apks.forEach(function(a){var div=document.createElement("div");div.className="apk-item";div.innerHTML='<div><b>📦 '+esc(a.name)+'</b><br><small style="color:#94a3b8">'+esc(a.size)+' • '+esc(a.mtime)+'</small></div><div><button class="btn-success" onclick="location.href=\'/api/download-saved-apk/'+encodeURIComponent(a.name)+'\'">⬇</button><button class="btn-danger" onclick="deleteApk(\''+esc(a.name)+'\')">🗑</button></div>';box.appendChild(div)})}catch(e){document.getElementById("apksList").innerText="Error"}}
async function deleteApk(name){if(!confirm("Delete?"))return;try{var r=await fetch("/api/apks/"+encodeURIComponent(name),{method:"DELETE"});if(r.ok){toast("Deleted");loadApks()}else toast("Failed","error")}catch(e){toast("Error","error")}}
function msg(t,e){var m=document.getElementById("message");m.style.display="block";m.innerText=t;m.style.background=e?"rgba(127,29,29,.55)":"rgba(20,83,45,.55)"}
async function restoreBackup(input){if(!input.files[0])return;if(!confirm("Restore backup? Existing projects may be overwritten."))return;var fd=new FormData();fd.append("file",input.files[0]);try{var r=await fetch("/api/restore",{method:"POST",body:fd});var d=await r.json();if(r.ok){toast("Restored!");loadProjects();status()}else toast(d.error||"Failed","error")}catch(e){toast("Error","error")}input.value=""}
status();loadProjects();
</script>
</body></html>
'''

# ============================================================
# END OF PART 1 — Now paste PART 2 below this line
# ============================================================
# ============================================================
# PART 2/3 : ALL FLASK ROUTES
# ============================================================

# ---------------- HOME ----------------
@app.route("/")
def home():
    return HOME_HTML

@app.route("/api/status")
def api_status():
    projects = [p for p in PROJECTS_DIR.iterdir() if p.is_dir()]
    langs = set(v["name"] for v in LANGUAGES.values())
    return jsonify({"server": "online", "port": PORT, "projects": len(projects),
                    "language_count": len(langs), "version": "10.0"})

# ---------------- PROJECTS ----------------
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
    if template not in ["empty", "login", "list", "splash", "bottom_nav"]: template = "empty"
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

# ---------------- FILES ----------------
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
        if any(x in ("build", ".gradle", ".git", "node_modules") for x in parts): continue
        try:
            rel = str(p.relative_to(project))
            if q in p.name.lower() or q in rel.lower():
                results.append({"name": p.name, "path": rel})
        except: continue
        if len(results) > 80: break
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
            content = target.read_text(encoding="utf-8", errors="replace")
            add_recent(name, sub)
            return jsonify({"content": content, "path": sub})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    data = request.get_json(silent=True) or {}
    new_content = data.get("content", "")
    try:
        if target.exists():
            try: backup_file_version(name, sub, target.read_text(encoding="utf-8", errors="replace"))
            except: pass
        target.write_text(new_content, encoding="utf-8")
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
        if action == "copy":
            nn = data.get("newName", "")
            if not nn: return jsonify({"error": "New name required"}), 400
            nt = safe_subpath(project, nn)
            if nt is None or nt.exists(): return jsonify({"error": "Invalid/Exists"}), 400
            nt.parent.mkdir(parents=True, exist_ok=True)
            if target.is_dir(): shutil.copytree(target, nt)
            else: shutil.copy2(target, nt)
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
    f.save(str(target_dir / fname))
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

# ---------------- BULK RENAME ----------------
@app.route("/api/bulk-rename", methods=["POST"])
def bulk_rename():
    data = request.get_json(silent=True) or {}
    project = safe_project(data.get("project", ""))
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    pattern = data.get("pattern", "")
    replace = data.get("replace", "")
    only_ext = data.get("ext", "").strip()
    if not pattern: return jsonify({"error": "Pattern required"}), 400
    try: rx = re.compile(pattern)
    except: return jsonify({"error": "Invalid regex"}), 400
    count = 0
    for p in sorted(project.rglob("*"), reverse=True):
        if not p.is_file(): continue
        if only_ext and p.suffix.lower() != only_ext.lower(): continue
        new_name = rx.sub(replace, p.name)
        if new_name != p.name:
            try:
                p.rename(p.parent / new_name)
                count += 1
            except: continue
    return jsonify({"success": True, "renamed": count})

# ---------------- EXTRACT ZIP ----------------
@app.route("/api/extract/<path:name>", methods=["POST"])
def extract_zip(name):
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
    try:
        with zipfile.ZipFile(f) as zf:
            for m in zf.namelist():
                if ".." in m or m.startswith("/"): continue
                zf.extract(m, target_dir)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------- FIREBASE INJECT ----------------
@app.route("/api/firebase-inject", methods=["POST"])
def firebase_inject():
    data = request.get_json(silent=True) or {}
    project = safe_project(data.get("project", ""))
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    json_str = data.get("json", "").strip()
    if not json_str:
        return jsonify({"error": "google-services.json content required"}), 400
    try:
        parsed = json.loads(json_str)
    except:
        return jsonify({"error": "Invalid JSON"}), 400
    write_file(project / "app" / "google-services.json", json.dumps(parsed, indent=2))
    # Update app/build.gradle
    app_gradle = project / "app" / "build.gradle"
    if app_gradle.exists():
        txt = app_gradle.read_text(encoding="utf-8")
        if "com.google.gms.google-services" not in txt:
            txt = txt.replace('plugins {\n    id "com.android.application"\n}',
                              'plugins {\n    id "com.android.application"\n    id "com.google.gms.google-services"\n}')
            app_gradle.write_text(txt, encoding="utf-8")
    # Update root build.gradle
    root_gradle = project / "build.gradle"
    if root_gradle.exists():
        txt = root_gradle.read_text(encoding="utf-8")
        if "com.google.gms:google-services" not in txt:
            txt = txt.rstrip() + '\nplugins { id "com.google.gms.google-services" version "4.4.2" apply false }\n'
            root_gradle.write_text(txt, encoding="utf-8")
    return jsonify({"success": True})

# ---------------- APKs ----------------
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

# ---------------- CHECK / SCAN ----------------
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
        result = subprocess.run(cmd, shell=True, cwd=str(target.parent),
                                capture_output=True, text=True, timeout=60)
        output = (result.stdout or "") + "\n" + (result.stderr or "")
        if result.returncode == 0:
            return jsonify({"errors": [], "language": lang["name"]})
        return jsonify({"errors": parse_errors(lang["name"], output, str(target)),
                        "language": lang["name"]})
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
        if any(p in ("build", ".gradle", ".git", "node_modules") for p in parts): continue
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
            r = subprocess.run(cmd, shell=True, cwd=str(path.parent),
                               capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                out = (r.stdout or "") + "\n" + (r.stderr or "")
                errs = parse_errors(lang["name"], out, str(path))
                if errs:
                    results.append({"path": rel, "language": lang["name"], "errors": errs})
        except: continue
    return jsonify({"scanned": scanned, "results": results})

# ---------------- RUN / TERMINAL ----------------
@app.route("/api/run-command", methods=["POST"])
def run_command():
    data = request.get_json(silent=True) or {}
    project = safe_project(data.get("project", ""))
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    cmd = data.get("cmd", "").strip()
    if not cmd: return jsonify({"error": "Empty"}), 400
    blocked = ["rm -rf /", "mkfs", "dd if=", ":(){", "shutdown", "reboot", "> /dev/sda"]
    for b in blocked:
        if b in cmd: return jsonify({"error": "Blocked"}), 403
    try:
        r = subprocess.run(cmd, shell=True, cwd=str(project),
                           capture_output=True, text=True, timeout=300)
        return jsonify({"stdout": r.stdout, "stderr": r.stderr, "returncode": r.returncode})
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Timeout (300s)"}), 500
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
        r = subprocess.run(cmd, shell=True, cwd=str(target.parent),
                           capture_output=True, text=True, timeout=120)
        return jsonify({"language": lang["name"], "command": cmd,
                        "stdout": r.stdout, "stderr": r.stderr, "returncode": r.returncode})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------- BUILD ----------------
def build_worker(build_id, project, env):
    B = BUILDS[build_id]
    cmd = "gradle assembleDebug --no-daemon --console=plain --parallel"
    try:
        proc = subprocess.Popen(cmd, shell=True, cwd=str(project), env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1)
        for line in iter(proc.stdout.readline, ""):
            line = line.rstrip()
            B["output"].append(line)
            hint = suggest_fix(line)
            if hint:
                B["output"].append(f"💡 Hint: {hint}")
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
    BUILDS[build_id] = {"output": [], "status": "running", "apk_path": None,
                        "returncode": None, "success": None}
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
        r = subprocess.run(["adb", "install", "-r", str(apks[0])],
                           capture_output=True, text=True, timeout=90)
        if r.returncode == 0:
            return jsonify({"success": True})
        return jsonify({"error": r.stderr or r.stdout or "Failed"}), 500
    except FileNotFoundError:
        return jsonify({"error": "adb not found"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/cache-clean", methods=["POST"])
def cache_clean():
    data = request.get_json(silent=True) or {}
    project = safe_project(data.get("project", ""))
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    cleared = []
    for name in ["build", "app/build", ".gradle", "app/.cxx"]:
        d = project / name
        if d.exists():
            try:
                shutil.rmtree(d)
                cleared.append(name)
            except: pass
    gcache = Path.home() / ".gradle" / "caches" / "transforms-3"
    if data.get("deep") and gcache.exists():
        try:
            shutil.rmtree(gcache)
            cleared.append("~/.gradle/transforms-3")
        except: pass
    return jsonify({"success": True, "cleared": cleared})

# ---------------- GIT ----------------
def git_run(project, args, timeout=60):
    try:
        r = subprocess.run(["git"] + args, cwd=str(project),
                           capture_output=True, text=True, timeout=timeout)
        return {"ok": r.returncode == 0, "out": r.stdout, "err": r.stderr,
                "code": r.returncode}
    except FileNotFoundError:
        return {"ok": False, "out": "", "err": "git not installed. Run: pkg install git", "code": -1}
    except Exception as e:
        return {"ok": False, "out": "", "err": str(e), "code": -1}

@app.route("/api/git/status/<path:name>")
def git_status(name):
    project = safe_project(name)
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    if not (project / ".git").exists():
        return jsonify({"init": False, "files": [], "branch": "-"})
    st = git_run(project, ["status", "--porcelain"])
    br = git_run(project, ["branch", "--show-current"])
    return jsonify({"init": True, "files": st["out"].splitlines(),
                    "branch": (br["out"] or "").strip() or "master"})

@app.route("/api/git/init/<path:name>", methods=["POST"])
def git_init(name):
    project = safe_project(name)
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    r = git_run(project, ["init"])
    git_run(project, ["add", "."])
    git_run(project, ["-c", "user.email=zihad@local", "-c", "user.name=Zihad",
                      "commit", "-m", "Initial commit"])
    return jsonify({"success": r["ok"], "out": r["out"], "err": r["err"]})

@app.route("/api/git/add/<path:name>", methods=["POST"])
def git_add(name):
    project = safe_project(name)
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    r = git_run(project, ["add", "."])
    return jsonify({"success": r["ok"], "err": r["err"]})

@app.route("/api/git/commit/<path:name>", methods=["POST"])
def git_commit(name):
    project = safe_project(name)
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    data = request.get_json(silent=True) or {}
    msg = data.get("message", "Update").strip() or "Update"
    r = git_run(project, ["-c", "user.email=zihad@local", "-c", "user.name=Zihad",
                          "commit", "-m", msg])
    return jsonify({"success": r["ok"], "out": r["out"], "err": r["err"]})

@app.route("/api/git/log/<path:name>")
def git_log(name):
    project = safe_project(name)
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    r = git_run(project, ["log", "--oneline", "-20"])
    return jsonify({"log": r["out"].splitlines()})

@app.route("/api/git/diff/<path:name>")
def git_diff(name):
    project = safe_project(name)
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    r = git_run(project, ["diff"])
    return jsonify({"diff": r["out"]})

@app.route("/api/git/branch/<path:name>", methods=["POST"])
def git_branch(name):
    project = safe_project(name)
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    data = request.get_json(silent=True) or {}
    action = data.get("action", "list")
    if action == "list":
        r = git_run(project, ["branch", "-a"])
        return jsonify({"branches": r["out"].splitlines()})
    if action == "new":
        br = data.get("name", "dev").strip()
        r = git_run(project, ["checkout", "-b", br])
        return jsonify({"success": r["ok"], "err": r["err"]})
    if action == "switch":
        br = data.get("name", "").strip()
        r = git_run(project, ["checkout", br])
        return jsonify({"success": r["ok"], "err": r["err"]})
    return jsonify({"error": "Unknown action"}), 400

@app.route("/api/git/remote/<path:name>", methods=["POST"])
def git_remote(name):
    project = safe_project(name)
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    data = request.get_json(silent=True) or {}
    action = data.get("action", "")
    url = data.get("url", "").strip()
    if action == "set" and url:
        git_run(project, ["remote", "remove", "origin"])
        r = git_run(project, ["remote", "add", "origin", url])
        return jsonify({"success": r["ok"], "err": r["err"]})
    if action == "push":
        r = git_run(project, ["push", "-u", "origin", "HEAD"], timeout=180)
        return jsonify({"success": r["ok"], "out": r["out"], "err": r["err"]})
    if action == "pull":
        r = git_run(project, ["pull"], timeout=180)
        return jsonify({"success": r["ok"], "out": r["out"], "err": r["err"]})
    if action == "fetch":
        r = git_run(project, ["fetch"], timeout=180)
        return jsonify({"success": r["ok"], "out": r["out"], "err": r["err"]})
    return jsonify({"error": "Unknown"}), 400

# ---------------- LOGCAT ----------------
@app.route("/api/logcat/start", methods=["POST"])
def logcat_start():
    sid = str(uuid.uuid4())
    try:
        proc = subprocess.Popen(["adb", "logcat", "-v", "brief"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1)
        LOGCAT_PROCS[sid] = {"proc": proc, "lines": [], "started": time.time()}
        def reader():
            try:
                for line in iter(proc.stdout.readline, ""):
                    if sid in LOGCAT_PROCS:
                        LOGCAT_PROCS[sid]["lines"].append(line.rstrip())
                        if len(LOGCAT_PROCS[sid]["lines"]) > 2000:
                            LOGCAT_PROCS[sid]["lines"] = LOGCAT_PROCS[sid]["lines"][-1500:]
            except: pass
        threading.Thread(target=reader, daemon=True).start()
        return jsonify({"success": True, "session": sid})
    except FileNotFoundError:
        return jsonify({"error": "adb not found"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/logcat/poll/<sid>")
def logcat_poll(sid):
    S = LOGCAT_PROCS.get(sid)
    if not S: return jsonify({"error": "Not found"}), 404
    since = int(request.args.get("since", 0))
    return jsonify({"lines": S["lines"][since:], "total": len(S["lines"])})

@app.route("/api/logcat/stop/<sid>", methods=["POST"])
def logcat_stop(sid):
    S = LOGCAT_PROCS.pop(sid, None)
    if S:
        try: S["proc"].terminate()
        except: pass
    return jsonify({"success": True})

# ---------------- ICON GENERATOR ----------------
@app.route("/api/icon-generate/<path:name>", methods=["POST"])
def icon_generate(name):
    project = safe_project(name)
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    f = request.files["file"]
    try:
        from PIL import Image
    except ImportError:
        return jsonify({"error": "Install Pillow: pkg install python-pillow"}), 500
    try:
        img = Image.open(f).convert("RGBA")
        sizes = {"mipmap-mdpi": 48, "mipmap-hdpi": 72, "mipmap-xhdpi": 96,
                 "mipmap-xxhdpi": 144, "mipmap-xxxhdpi": 192}
        res_dir = project / "app" / "src" / "main" / "res"
        for folder, px in sizes.items():
            d = res_dir / folder
            d.mkdir(parents=True, exist_ok=True)
            img.resize((px, px), Image.LANCZOS).save(d / "ic_launcher.png")
        return jsonify({"success": True, "sizes": list(sizes.keys())})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------- STRINGS EDITOR ----------------
@app.route("/api/strings/<path:name>", methods=["GET", "POST"])
def strings_editor(name):
    project = safe_project(name)
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    strings_file = project / "app" / "src" / "main" / "res" / "values" / "strings.xml"
    if request.method == "GET":
        if not strings_file.exists():
            return jsonify({"items": []})
        try:
            import xml.etree.ElementTree as ET
            tree = ET.parse(str(strings_file))
            root = tree.getroot()
            items = []
            for s in root.findall("string"):
                items.append({"name": s.get("name", ""), "value": s.text or ""})
            return jsonify({"items": items})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    data = request.get_json(silent=True) or {}
    items = data.get("items", [])
    try:
        xml_lines = ['<?xml version="1.0" encoding="utf-8"?>', "<resources>"]
        for it in items:
            nm = re.sub(r"[^a-zA-Z0-9_]", "_", it.get("name", ""))[:60]
            val = (it.get("value", "") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            xml_lines.append(f'    <string name="{nm}">{val}</string>')
        xml_lines.append("</resources>")
        strings_file.parent.mkdir(parents=True, exist_ok=True)
        strings_file.write_text("\n".join(xml_lines), encoding="utf-8")
        return jsonify({"success": True, "count": len(items)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------- THEME BUILDER ----------------
@app.route("/api/theme/<path:name>", methods=["GET", "POST"])
def theme_builder(name):
    project = safe_project(name)
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    colors_file = project / "app" / "src" / "main" / "res" / "values" / "colors.xml"
    if request.method == "GET":
        if not colors_file.exists():
            return jsonify({"colors": []})
        try:
            import xml.etree.ElementTree as ET
            tree = ET.parse(str(colors_file))
            items = [{"name": c.get("name", ""), "value": c.text or ""}
                     for c in tree.getroot().findall("color")]
            return jsonify({"colors": items})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    data = request.get_json(silent=True) or {}
    colors = data.get("colors", [])
    try:
        lines = ['<?xml version="1.0" encoding="utf-8"?>', "<resources>"]
        for c in colors:
            nm = re.sub(r"[^a-zA-Z0-9_]", "_", c.get("name", ""))[:50]
            val = c.get("value", "#000000")
            lines.append(f'    <color name="{nm}">{val}</color>')
        lines.append("</resources>")
        colors_file.parent.mkdir(parents=True, exist_ok=True)
        colors_file.write_text("\n".join(lines), encoding="utf-8")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------- VERSION BUMP ----------------
@app.route("/api/version-bump/<path:name>", methods=["POST"])
def version_bump(name):
    project = safe_project(name)
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    data = request.get_json(silent=True) or {}
    bump_code = bool(data.get("versionCode", True))
    bump_name = bool(data.get("versionName", False))
    gradle_file = project / "app" / "build.gradle"
    if not gradle_file.exists():
        return jsonify({"error": "app/build.gradle not found"}), 404
    txt = gradle_file.read_text(encoding="utf-8")
    m_code = re.search(r"versionCode\s+(\d+)", txt)
    m_name = re.search(r'versionName\s+"([^"]+)"', txt)
    if bump_code and m_code:
        new_code = int(m_code.group(1)) + 1
        txt = txt.replace(m_code.group(0), f"versionCode {new_code}")
    if bump_name and m_name:
        parts = m_name.group(1).split(".")
        try:
            parts[-1] = str(int(parts[-1]) + 1)
        except: parts.append("1")
        new_name = ".".join(parts)
        txt = txt.replace(m_name.group(0), f'versionName "{new_name}"')
    gradle_file.write_text(txt, encoding="utf-8")
    # update project.json
    info_file = project / "project.json"
    if info_file.exists():
        try:
            info = json.loads(info_file.read_text(encoding="utf-8"))
            if bump_code: info["versionCode"] = info.get("versionCode", 1) + 1
            if bump_name:
                p = info.get("versionName", "1.0").split(".")
                try: p[-1] = str(int(p[-1]) + 1)
                except: p.append("1")
                info["versionName"] = ".".join(p)
            info_file.write_text(json.dumps(info, indent=4), encoding="utf-8")
        except: pass
    return jsonify({"success": True})

# ---------------- KEYSTORE / SIGN RELEASE ----------------
@app.route("/api/keystore", methods=["GET", "POST"])
def keystore_mgr():
    if request.method == "GET":
        ks = load_json(KEYSTORE_FILE, {})
        ks.pop("storePassword", None)
        ks.pop("keyPassword", None)
        return jsonify(ks)
    data = request.get_json(silent=True) or {}
    save_json(KEYSTORE_FILE, data)
    return jsonify({"success": True})

@app.route("/api/sign-release/<path:name>", methods=["POST"])
def sign_release(name):
    project = safe_project(name)
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    ks = load_json(KEYSTORE_FILE, {})
    if not ks.get("storeFile") or not ks.get("storePassword"):
        return jsonify({"error": "Keystore not configured"}), 400
    # Inject signing config into build.gradle
    gradle_file = project / "app" / "build.gradle"
    if not gradle_file.exists():
        return jsonify({"error": "app/build.gradle missing"}), 404
    txt = gradle_file.read_text(encoding="utf-8")
    if "signingConfigs" not in txt:
        sign_cfg = f'''
    signingConfigs {{
        release {{
            storeFile file("{ks['storeFile']}")
            storePassword "{ks['storePassword']}"
            keyAlias "{ks.get('keyAlias','release')}"
            keyPassword "{ks.get('keyPassword','')}"
        }}
    }}
'''
        txt = txt.replace("    buildTypes {", sign_cfg + "    buildTypes {")
        txt = txt.replace("release { minifyEnabled false }",
                          'release { minifyEnabled false; signingConfig signingConfigs.release }')
        txt = txt.replace('release {\n            minifyEnabled false\n        }',
                          'release {\n            minifyEnabled false\n            signingConfig signingConfigs.release\n        }')
        gradle_file.write_text(txt, encoding="utf-8")
    # Build release
    env = os.environ.copy()
    sdk = Path.home() / "android-sdk"
    if sdk.exists():
        env["ANDROID_HOME"] = str(sdk)
        env["ANDROID_SDK_ROOT"] = str(sdk)
    env["PATH"] = str(sdk / "platform-tools") + ":" + TERMUX_PREFIX + "/bin:" + env.get("PATH", "")
    try:
        r = subprocess.run("gradle assembleRelease --no-daemon --console=plain",
                           shell=True, cwd=str(project), env=env,
                           capture_output=True, text=True, timeout=900)
        apks = list(project.glob("app/build/outputs/apk/release/*.apk"))
        if r.returncode == 0 and apks:
            dest = SIGNED_DIR / f"{project.name}-release-{int(time.time())}.apk"
            shutil.copy2(apks[0], dest)
            return jsonify({"success": True, "signed_path": str(dest),
                            "download": f"/api/download-signed/{dest.name}"})
        return jsonify({"error": "Build failed", "out": r.stdout[-3000:],
                        "err": r.stderr[-1000:]}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/download-signed/<path:fname>")
def download_signed(fname):
    p = SIGNED_DIR / fname
    if p.exists():
        return send_file(str(p), as_attachment=True, download_name=fname)
    return "Not found", 404

# ---------------- MANIFEST EDITOR ----------------
@app.route("/api/manifest/<path:name>", methods=["GET", "POST"])
def manifest_editor(name):
    project = safe_project(name)
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    manifest_file = project / "app" / "src" / "main" / "AndroidManifest.xml"
    if request.method == "GET":
        if not manifest_file.exists():
            return jsonify({"permissions": [], "activities": [], "raw": ""})
        try:
            raw = manifest_file.read_text(encoding="utf-8")
            perms = re.findall(r'<uses-permission android:name="([^"]+)"', raw)
            acts = re.findall(r'<activity android:name="([^"]+)"', raw)
            return jsonify({"permissions": perms, "activities": acts, "raw": raw})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    data = request.get_json(silent=True) or {}
    raw = data.get("raw", "")
    if not raw: return jsonify({"error": "Empty"}), 400
    try:
        import xml.etree.ElementTree as ET
        ET.fromstring(raw)
        manifest_file.write_text(raw, encoding="utf-8")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": "Invalid XML: " + str(e)}), 400

# ---------------- ENV MANAGER ----------------
@app.route("/api/env/<path:name>", methods=["GET", "POST"])
def env_mgr(name):
    project = safe_project(name)
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    vault = load_json(ENV_FILE, {})
    if request.method == "GET":
        return jsonify({"items": vault.get(name, [])})
    data = request.get_json(silent=True) or {}
    vault[name] = data.get("items", [])
    save_json(ENV_FILE, vault)
    # Also write .env
    env_txt = "\n".join(f'{it["key"]}={it["value"]}' for it in vault[name])
    write_file(project / ".env", env_txt + "\n")
    return jsonify({"success": True})

# ---------------- HISTORY ----------------
@app.route("/api/history/<path:name>")
def history_list(name):
    path = request.args.get("path", "")
    key = f"{name}__{path.replace('/', '_').replace(chr(92), '_')}"
    hist_dir = HISTORY_DIR / key
    if not hist_dir.exists():
        return jsonify({"versions": []})
    versions = sorted(hist_dir.iterdir(), key=lambda x: -x.stat().st_mtime)
    return jsonify({"versions": [
        {"file": v.name, "size": human_size(v.stat().st_size),
         "mtime": datetime.fromtimestamp(v.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")}
        for v in versions
    ]})

@app.route("/api/history-restore", methods=["POST"])
def history_restore():
    data = request.get_json(silent=True) or {}
    project = safe_project(data.get("project", ""))
    path = data.get("path", "")
    version = data.get("version", "")
    if project is None or not project.exists(): return jsonify({"error": "Invalid"}), 400
    key = f"{project.name}__{path.replace('/', '_').replace(chr(92), '_')}"
    bak = HISTORY_DIR / key / version
    if not bak.exists(): return jsonify({"error": "Version not found"}), 404
    target = safe_subpath(project, path)
    if target is None: return jsonify({"error": "Invalid"}), 400
    try:
        target.write_text(bak.read_text(encoding="utf-8"), encoding="utf-8")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------- RECENT ----------------
@app.route("/api/recent")
def recent_list():
    data = load_json(RECENT_FILES_FILE, {"items": []})
    items = data.get("items", [])[:20]
    for it in items:
        it["mtime"] = datetime.fromtimestamp(it["ts"]).strftime("%Y-%m-%d %H:%M")
    return jsonify({"items": items})

# ---------------- SAVED COMMANDS ----------------
@app.route("/api/saved-commands", methods=["GET", "POST", "DELETE"])
def saved_commands():
    items = get_saved_commands()
    if request.method == "GET":
        return jsonify({"items": items})
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        cmd = data.get("cmd", "").strip()
        if not cmd: return jsonify({"error": "Empty"}), 400
        if cmd not in items: items.insert(0, cmd)
        save_saved_commands(items)
        return jsonify({"success": True, "items": items})
    data = request.get_json(silent=True) or {}
    cmd = data.get("cmd", "")
    items = [i for i in items if i != cmd]
    save_saved_commands(items)
    return jsonify({"success": True, "items": items})

# ---------------- BACKUP / RESTORE ----------------
@app.route("/api/backup")
def backup_all():
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zf:
        for proj in PROJECTS_DIR.iterdir():
            if not proj.is_dir(): continue
            for f in proj.rglob("*"):
                if not f.is_file(): continue
                parts = str(f).split(os.sep)
                if any(p in ("build", ".gradle", ".git", "node_modules") for p in parts): continue
                try: zf.write(f, f.relative_to(PROJECTS_DIR))
                except: continue
    mem.seek(0)
    name = f"zihad-ide-backup-{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
    return send_file(mem, as_attachment=True, download_name=name, mimetype="application/zip")

@app.route("/api/restore", methods=["POST"])
def restore_backup():
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    f = request.files["file"]
    try:
        with zipfile.ZipFile(f) as zf:
            for m in zf.namelist():
                if ".." in m or m.startswith("/"): continue
                zf.extract(m, PROJECTS_DIR)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------- EXPORT ZIP ----------------
@app.route("/api/export-zip/<path:name>")
def export_zip(name):
    project = safe_project(name)
    if project is None or not project.exists(): return "Invalid", 400
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in project.rglob("*"):
            if f.is_file():
                parts = str(f).split(os.sep)
                if any(p in ("build", ".gradle", ".git") for p in parts): continue
                zf.write(f, f.relative_to(project))
    mem.seek(0)
    return send_file(mem, as_attachment=True, download_name=name + ".zip",
                     mimetype="application/zip")

# ---------------- LIVE HTML PREVIEW ----------------
@app.route("/api/live-preview/<path:name>")
def live_preview(name):
    project = safe_project(name)
    if project is None or not project.exists(): return "Invalid", 404
    target = safe_subpath(project, request.args.get("path", "index.html"))
    if target is None or not target.is_file(): return "Not found", 404
    content = target.read_text(encoding="utf-8", errors="replace")
    return Response(content, mimetype="text/html")

# ---------------- PWA ----------------
@app.route("/manifest.json")
def pwa_manifest():
    return jsonify({
        "name": "Zihad Mobile IDE", "short_name": "ZihadIDE",
        "start_url": "/", "display": "standalone",
        "background_color": "#070b14", "theme_color": "#3b82f6",
        "icons": [{"src": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E%E2%9A%A1%3C/text%3E%3C/svg%3E",
                   "sizes": "192x192", "type": "image/svg+xml"}]
    })

@app.route("/sw.js")
def service_worker():
    sw = """
const CACHE='zihad-ide-v10';
self.addEventListener('install',e=>self.skipWaiting());
self.addEventListener('activate',e=>e.waitUntil(clients.claim()));
self.addEventListener('fetch',e=>{
  if(e.request.method!=='GET')return;
  e.respondWith(fetch(e.request).catch(()=>caches.match(e.request)));
});
"""
    return Response(sw, mimetype="application/javascript")

# ============================================================
# END OF PART 2 — Paste PART 3 below
# ============================================================

# ============================================================
# PART 3/3 : IDE_HTML + Main Block
# ============================================================

IDE_HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta name="theme-color" content="#3b82f6">
<link rel="manifest" href="/manifest.json">
<title>__NAME__ - Zihad IDE</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/theme/dracula.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/theme/material-darker.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/theme/monokai.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/dialog/dialog.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/fold/foldgutter.min.css">
<style>
:root{--bg:#070b14;--card:#111827;--border:#1f2937;--primary:#3b82f6;--text:#e2e8f0;--muted:#94a3b8;--success:#22c55e;--danger:#ef4444;--radius:14px;--bottom-h:62px}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:14px;overflow:hidden}
header{padding:8px 10px;background:rgba(15,23,42,.95);backdrop-filter:blur(16px);border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;gap:6px;position:relative;z-index:30;flex-wrap:wrap}
header h2{font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;min-width:80px}
.btn{border:0;border-radius:9px;padding:6px 9px;font-weight:600;font-size:11px;color:#fff;cursor:pointer;background:#374151}
.btn-primary{background:linear-gradient(135deg,#3b82f6,#2563eb)}
.btn-success{background:linear-gradient(135deg,#22c55e,#16a34a)}
.btn-danger{background:linear-gradient(135deg,#ef4444,#dc2626)}
.btn-orange{background:linear-gradient(135deg,#f59e0b,#d97706)}
.btn-purple{background:linear-gradient(135deg,#8b5cf6,#7c3aed)}
.badge{display:inline-block;padding:2px 7px;border-radius:20px;font-size:10px;font-weight:700}
.badge.ok{background:rgba(34,197,94,.2);color:#4ade80}
.badge.err{background:rgba(239,68,68,.25);color:#fca5a5}
.bottom-nav{position:fixed;bottom:0;left:0;right:0;height:var(--bottom-h);background:rgba(15,23,42,.96);border-top:1px solid var(--border);display:flex;z-index:40;padding-bottom:env(safe-area-inset-bottom)}
.nav-item{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;font-size:10px;color:var(--muted);cursor:pointer}
.nav-item.active{color:#60a5fa}
.nav-item span:first-child{font-size:19px}
.main-area{height:calc(100vh - 48px - var(--bottom-h));overflow:hidden}
.panel{display:none;height:100%;overflow-y:auto;padding:10px;padding-bottom:20px}
.panel.active{display:block}
.breadcrumb{background:rgba(8,15,28,.7);padding:8px 11px;border-radius:10px;margin-bottom:8px;font-size:12px;word-break:break-all}
.breadcrumb span{color:#60a5fa;cursor:pointer}
.file-item{background:var(--card);padding:11px;margin:4px 0;border-radius:11px;border:1px solid var(--border);cursor:pointer;display:flex;align-items:center;gap:9px}
.file-item .name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px}
.file-item.folder .name{color:#fbbf24;font-weight:600}
.file-item.file .name{color:#93c5fd}
.file-item .meta{font-size:10px;color:var(--muted);white-space:nowrap}
.toolbar{display:flex;gap:5px;margin-bottom:8px;flex-wrap:wrap}
.sort-bar{display:flex;gap:5px;margin-bottom:8px}
.sort-bar select{padding:7px 9px;border-radius:8px;border:1px solid var(--border);background:#0b1220;color:#fff;font-size:12px;flex:1}
#editor-box{position:fixed;inset:0;background:var(--bg);z-index:100;display:none;flex-direction:column}
#editor-header{padding:6px 9px;background:rgba(15,23,42,.95);border-bottom:1px solid var(--border);display:flex;align-items:center;gap:5px;flex-wrap:wrap}
.tab-bar-editor{display:flex;overflow-x:auto;background:#0b1220;border-bottom:1px solid var(--border)}
.editor-tab{padding:8px 12px;font-size:12px;white-space:nowrap;cursor:pointer;border-bottom:2px solid transparent;color:var(--muted)}
.editor-tab.active{color:#60a5fa;border-bottom-color:#3b82f6;background:rgba(59,130,246,.08)}
.editor-tab .close-tab{opacity:.5;font-size:13px;padding:0 2px}
#editor-toolbar{padding:4px 7px;background:#0b1220;border-bottom:1px solid var(--border);display:flex;gap:3px;flex-wrap:wrap}
#editor-toolbar button{background:#1f2937;color:#e2e8f0;border:0;border-radius:6px;padding:5px 9px;font-size:11px;font-weight:600;cursor:pointer}
#editor-container{flex:1;overflow:hidden;position:relative}
.CodeMirror{height:100%!important;font-size:13px;font-family:'JetBrains Mono',Consolas,monospace}
.cm-error-line{background:rgba(239,68,68,.18)!important}
#terminal-output{background:#000;color:#4ade80;padding:11px;border-radius:11px;min-height:200px;max-height:calc(100vh - 240px);overflow-y:auto;font-size:12px;white-space:pre-wrap;font-family:monospace;border:1px solid #1f2937;margin-bottom:8px}
#cmd-input{display:flex;gap:5px}
#cmd-input input{flex:1;padding:10px;background:#0b1220;color:#e2e8f0;border:1px solid #374151;border-radius:9px;font-family:monospace;font-size:13px}
#cmd-input button{padding:10px 14px;background:var(--success);color:#fff;border:0;border-radius:9px;font-weight:700}
.output-box{background:#000;color:#4ade80;padding:11px;border-radius:11px;min-height:180px;white-space:pre-wrap;font-family:monospace;font-size:12px;border:1px solid #1f2937;max-height:calc(100vh - 260px);overflow-y:auto}
.err-item{background:rgba(127,29,29,.5);color:#fecaca;padding:11px;border-radius:9px;margin:5px 0;cursor:pointer;border-left:4px solid #ef4444;font-family:monospace;font-size:12px}
.info-bar{background:rgba(8,15,28,.7);padding:9px;border-radius:9px;margin-bottom:9px;font-size:12px;border:1px solid var(--border)}
.build-panel{background:#0b1220;border:1px solid #1f2937;border-radius:13px;padding:14px;margin-bottom:12px}
.progress-wrap{background:#1f2937;border-radius:20px;height:26px;overflow:hidden;position:relative;margin:10px 0}
.progress-bar{height:100%;background:linear-gradient(90deg,#3b82f6,#8b5cf6);transition:width .4s;width:0%}
.progress-text{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;color:#fff}
.toast-container{position:fixed;bottom:calc(var(--bottom-h)+16px);left:50%;transform:translateX(-50%);z-index:999;display:flex;flex-direction:column;gap:7px;pointer-events:none}
.toast{background:rgba(15,23,42,.96);border:1px solid var(--border);color:#fff;padding:10px 16px;border-radius:11px;font-size:13px}
.toast.success{border-color:rgba(34,197,94,.45)}.toast.error{border-color:rgba(239,68,68,.45)}
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:200;display:none;align-items:flex-end;justify-content:center}
.modal-overlay.show{display:flex}
.modal{background:#111827;border-radius:20px 20px 0 0;padding:20px;width:100%;max-width:520px;max-height:85vh;overflow-y:auto}
.modal h3{font-size:15px;margin-bottom:10px;color:#60a5fa}
.modal input,.modal textarea,.modal select{width:100%;padding:10px 12px;margin:6px 0;border-radius:10px;border:1px solid #374151;background:#0b1220;color:#fff;font-size:13px}
.modal textarea{font-family:monospace;min-height:120px;resize:vertical}
.empty{color:var(--muted);text-align:center;padding:25px;font-style:italic}
.search-box{display:flex;gap:6px;margin-bottom:8px}
.search-box input{flex:1;padding:10px 12px;border-radius:10px;border:1px solid var(--border);background:#0b1220;color:#fff;font-size:13px}
.upload-btn{position:relative;overflow:hidden}
.upload-btn input{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%}
.preview-frame{background:#0f172a;border-radius:24px;border:6px solid #1e293b;width:min(320px,90vw);margin:0 auto;overflow:hidden;min-height:480px;position:relative}
.preview-frame.tablet{width:min(520px,95vw);min-height:380px}
.preview-frame.desktop{width:min(90vw,900px);min-height:400px}
.preview-content{padding:14px;min-height:440px;color:#fff}
.device-frames{display:flex;gap:6px;margin-bottom:10px;justify-content:center;flex-wrap:wrap}
.device-frames button{background:#1f2937;color:#94a3b8;padding:6px 12px;font-size:11px}
.device-frames button.active{background:#3b82f6;color:#fff}
.cmd-palette{position:fixed;top:20%;left:50%;transform:translateX(-50%);width:min(500px,92vw);background:#0b1220;border:1px solid #1f2937;border-radius:14px;z-index:500;display:none;box-shadow:0 20px 60px rgba(0,0,0,.6);overflow:hidden}
.cmd-palette.show{display:block}
.cmd-palette input{width:100%;padding:14px 16px;background:transparent;border:0;color:#fff;font-size:15px;outline:none;border-bottom:1px solid #1f2937}
.cmd-palette ul{list-style:none;max-height:340px;overflow-y:auto}
.cmd-palette li{padding:11px 16px;cursor:pointer;font-size:13px;color:#cbd5e1;border-bottom:1px solid #111827}
.cmd-palette li:hover,.cmd-palette li.active{background:#1f2937;color:#60a5fa}
.git-item{background:#0b1220;border:1px solid #1f2937;border-radius:8px;padding:8px 10px;margin:3px 0;font-family:monospace;font-size:11px}
.logcat-line{font-family:monospace;font-size:11px;padding:2px 4px;border-bottom:1px solid #0f172a}
.logcat-line.err{color:#f87171}.logcat-line.warn{color:#fbbf24}.logcat-line.info{color:#60a5fa}
.more-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px;margin:8px 0}
.more-item{background:#0b1220;border:1px solid #1f2937;border-radius:11px;padding:14px 8px;text-align:center;cursor:pointer;font-size:12px;color:#cbd5e1}
.more-item:hover{background:#1f2937;color:#60a5fa}
.more-item span{font-size:22px;display:block;margin-bottom:5px}
.hint-line{color:#fbbf24;font-weight:600}
.split-toggle{position:absolute;top:5px;right:5px;z-index:101;padding:5px 10px;font-size:10px;background:#1f2937;color:#94a3b8;border:0;border-radius:6px;cursor:pointer}
.split-pane{position:absolute;right:0;top:0;bottom:0;width:45%;background:#0f172a;border-left:1px solid #1f2937;overflow:auto;padding:10px;display:none}
.split-pane.show{display:block}
</style>
</head>
<body>
<header>
  <h2>📱 __NAME__</h2>
  <div style="display:flex;gap:3px;flex-wrap:wrap">
    <button class="btn btn-orange" onclick="scanAllErrors()" id="scanBtn" title="Scan errors">🔍</button>
    <button class="btn btn-purple" onclick="runCurrent()" id="runBtn" style="display:none">▶</button>
    <button class="btn btn-primary" onclick="buildApk()" title="Build APK">🔨</button>
    <button class="btn" onclick="exportZip()" title="Export ZIP">📦</button>
    <button class="btn" onclick="showMoreMenu()" title="More">⋯</button>
    <button class="btn" onclick="openCommandPalette()" title="Command Palette">⌘</button>
    <button class="btn" onclick="openSettings()" title="Settings">⚙️</button>
    <button class="btn" onclick="location.href='/'" title="Home">🏠</button>
  </div>
</header>

<div class="main-area">
  <!-- FILES -->
  <div class="panel active" id="panel-explorer">
    <div class="toolbar">
      <button class="btn btn-success" onclick="newFile()">📄 +File</button>
      <button class="btn btn-orange" onclick="newFolder()">📁 +Folder</button>
      <button class="btn upload-btn">⬆ Upload<input type="file" onchange="doUpload(this)"></button>
      <button class="btn upload-btn">🗜 Extract<input type="file" accept=".zip" onchange="doExtract(this)"></button>
      <button class="btn" onclick="loadFiles(currentPath)">🔄</button>
      <button class="btn" onclick="showRecent()">🕒 Recent</button>
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

  <!-- PREVIEW -->
  <div class="panel" id="panel-preview">
    <div class="info-bar">Live Layout / HTML Preview</div>
    <div class="device-frames">
      <button class="active" onclick="setDevice('phone',this)">📱 Phone</button>
      <button onclick="setDevice('tablet',this)">📱 Tablet</button>
      <button onclick="setDevice('desktop',this)">💻 Desktop</button>
      <button onclick="refreshPreview()">🔄</button>
      <button onclick="togglePreviewMode()" id="prevModeBtn">HTML</button>
    </div>
    <div class="preview-frame" id="previewFrame">
      <div class="preview-content" id="previewContent">
        <p style="text-align:center;color:#64748b;padding:40px 20px">Tap 🔄 to load layout or HTML</p>
      </div>
    </div>
  </div>

  <!-- ERRORS -->
  <div class="panel" id="panel-errors">
    <div class="info-bar" id="errInfo">Press 🔍 to scan</div>
    <div id="err-list"></div>
  </div>

  <!-- TERMINAL -->
  <div class="panel" id="panel-terminal">
    <div style="display:flex;justify-content:space-between;margin-bottom:7px;gap:5px;flex-wrap:wrap">
      <span style="font-size:12px;color:var(--muted)">Terminal</span>
      <div>
        <button class="btn" style="padding:4px 9px;font-size:11px" onclick="showSavedCommands()">⭐ Saved</button>
        <button class="btn" style="padding:4px 9px;font-size:11px" onclick="saveCurrentCmd()">+ Save</button>
        <button class="btn" style="padding:4px 9px;font-size:11px" onclick="clearTerminal()">Clear</button>
      </div>
    </div>
    <div id="terminal-output">$ Zihad IDE Terminal — Ready
</div>
    <div id="cmd-input">
      <input id="cmd" placeholder="ls, gradle -v, git status..." onkeydown="termKey(event)">
      <button onclick="runCmd()">Run</button>
    </div>
  </div>

  <!-- OUTPUT -->
  <div class="panel" id="panel-output">
    <div class="info-bar" id="run-info">No code executed yet</div>
    <div class="output-box" id="output-box">Output will appear here...</div>
  </div>

  <!-- BUILD -->
  <div class="panel" id="panel-build">
    <div class="build-panel">
      <h3 style="margin:0 0 8px;font-size:14px;color:#60a5fa">🔨 APK Build</h3>
      <div class="progress-wrap">
        <div class="progress-bar" id="buildProgressBar"></div>
        <div class="progress-text" id="buildProgressText">0%</div>
      </div>
      <div id="currentTask" style="font-family:monospace;font-size:11px;color:#fbbf24;margin:8px 0">Press 🔨 to build</div>
      <div id="buildStatusMsg" style="text-align:center;font-size:12px;color:var(--muted)">Ready</div>
      <div id="apk-box" style="display:none;margin-top:10px">
        <button class="btn btn-success" id="apkDownloadBtn" style="width:100%;padding:12px;margin-bottom:6px">⬇ Download APK</button>
        <div style="display:flex;gap:5px">
          <button class="btn btn-primary" style="flex:1;padding:12px" onclick="adbInstall()">📲 ADB Install</button>
          <button class="btn btn-danger" style="flex:1;padding:12px" onclick="cleanBuild()">🧹 Clean</button>
        </div>
      </div>
    </div>
    <div class="info-bar">Live Build Log</div>
    <div class="output-box" id="buildLog">$ Waiting...</div>
  </div>

  <!-- GIT -->
  <div class="panel" id="panel-git">
    <div class="info-bar" id="gitInfo">Git</div>
    <div class="toolbar">
      <button class="btn btn-success" onclick="gitAction('init')">🔧 Init</button>
      <button class="btn btn-primary" onclick="gitAction('add')">➕ Add All</button>
      <button class="btn btn-purple" onclick="gitCommitPrompt()">💾 Commit</button>
      <button class="btn" onclick="gitAction('log')">📜 Log</button>
      <button class="btn" onclick="gitAction('diff')">🔍 Diff</button>
      <button class="btn" onclick="gitAction('branches')">🌿 Branch</button>
    </div>
    <div class="toolbar">
      <button class="btn btn-success" onclick="gitRemote('push')">⬆ Push</button>
      <button class="btn btn-orange" onclick="gitRemote('pull')">⬇ Pull</button>
      <button class="btn" onclick="gitSetRemote()">🔗 Set Remote</button>
    </div>
    <div id="gitOutput" class="output-box" style="min-height:150px;max-height:calc(100vh - 340px)"></div>
  </div>

  <!-- LOGCAT -->
  <div class="panel" id="panel-logcat">
    <div class="toolbar">
      <button class="btn btn-success" onclick="logcatStart()" id="lcStartBtn">▶ Start</button>
      <button class="btn btn-danger" onclick="logcatStop()">⏹ Stop</button>
      <button class="btn" onclick="logcatClear()">🗑 Clear</button>
      <select id="lcFilter" onchange="renderLogcat()" style="padding:7px 9px;border-radius:8px;border:1px solid var(--border);background:#0b1220;color:#fff;font-size:12px">
        <option value="all">All</option>
        <option value="error">Errors only</option>
        <option value="warn">Warn+</option>
        <option value="info">Info+</option>
      </select>
    </div>
    <div id="logcatBox" style="background:#000;border:1px solid #1f2937;border-radius:11px;max-height:calc(100vh - 260px);overflow-y:auto;padding:6px">Not started</div>
  </div>
</div>

<nav class="bottom-nav">
  <div class="nav-item active" data-panel="explorer" onclick="switchPanel('explorer',this)"><span>📂</span>Files</div>
  <div class="nav-item" data-panel="preview" onclick="switchPanel('preview',this)"><span>📱</span>Preview</div>
  <div class="nav-item" data-panel="errors" onclick="switchPanel('errors',this)"><span>⚠️</span>Errors <span id="errBadgeNav" class="badge ok" style="font-size:9px">0</span></div>
  <div class="nav-item" data-panel="terminal" onclick="switchPanel('terminal',this)"><span>💻</span>Term</div>
  <div class="nav-item" data-panel="build" onclick="switchPanel('build',this)"><span>🔨</span>Build</div>
  <div class="nav-item" data-panel="git" onclick="switchPanel('git',this)"><span>🔀</span>Git</div>
  <div class="nav-item" data-panel="logcat" onclick="switchPanel('logcat',this)"><span>📜</span>Log</div>
</nav>

<!-- EDITOR -->
<div id="editor-box">
  <div id="editor-header">
    <span style="font-size:12px;color:#93c5fd;font-family:monospace;flex:1;overflow:hidden;text-overflow:ellipsis" id="editor-filename">file</span>
    <span id="editor-err-badge" class="badge ok">0</span>
    <button class="btn btn-success" onclick="saveFile(false)">💾</button>
    <button class="btn btn-orange" onclick="checkCurrentFile()">🔍</button>
    <button class="btn btn-purple" onclick="runCurrent()">▶</button>
    <button class="btn" onclick="toggleSplitPreview()" title="Split Preview">◧</button>
    <button class="btn" onclick="showHistory()" title="History">🕒</button>
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
  <div id="editor-container">
    <textarea id="editor"></textarea>
    <button class="split-toggle" onclick="toggleSplitPreview()">Split Preview</button>
    <div class="split-pane" id="splitPane"></div>
  </div>
</div>

<!-- MODALS -->
<div class="modal-overlay" id="settingsModal" onclick="if(event.target===this)this.classList.remove('show')">
  <div class="modal">
    <h3>⚙️ Settings</h3>
    <label style="font-size:12px">Font Size</label>
    <input type="range" id="fontSize" min="11" max="20" value="13" oninput="applyFontSize(this.value);localStorage.setItem('fontSize',this.value)">
    <label style="font-size:12px">Auto Save</label>
    <select id="autoSave" onchange="localStorage.setItem('autoSave',this.value)">
      <option value="off">Off</option><option value="on">On</option>
    </select>
    <label style="font-size:12px">Editor Theme</label>
    <select id="cmTheme" onchange="changeTheme(this.value)">
      <option value="dracula">Dracula</option>
      <option value="material-darker">Material Darker</option>
      <option value="monokai">Monokai</option>
    </select>
    <label style="font-size:12px">UI Language</label>
    <select id="uiLang" onchange="setLang(this.value)">
      <option value="en">English</option><option value="bn">বাংলা</option>
    </select>
    <button class="btn btn-primary" style="width:100%;margin-top:12px;padding:12px" onclick="document.getElementById('settingsModal').classList.remove('show')">Done</button>
  </div>
</div>

<div class="modal-overlay" id="moreModal" onclick="if(event.target===this)this.classList.remove('show')">
  <div class="modal">
    <h3>⋯ More Tools</h3>
    <div class="more-grid">
      <div class="more-item" onclick="openPkgRename()"><span>📦</span>Rename Pkg</div>
      <div class="more-item" onclick="openStrings()"><span>🔤</span>Strings</div>
      <div class="more-item" onclick="openThemeBuilder()"><span>🎨</span>Theme</div>
      <div class="more-item" onclick="openManifest()"><span>📋</span>Manifest</div>
      <div class="more-item" onclick="openIconGen()"><span>🖼</span>Icon</div>
      <div class="more-item" onclick="openEnvMgr()"><span>🔑</span>ENV</div>
      <div class="more-item" onclick="openBulkRename()"><span>✏️</span>Bulk Rename</div>
      <div class="more-item" onclick="openFirebase()"><span>🔥</span>Firebase</div>
      <div class="more-item" onclick="bumpVersion()"><span>🔢</span>Bump Ver</div>
      <div class="more-item" onclick="openKeystore()"><span>🔐</span>Keystore</div>
      <div class="more-item" onclick="signRelease()"><span>✅</span>Sign Rel</div>
      <div class="more-item" onclick="cleanBuild(true)"><span>🧹</span>Clean All</div>
      <div class="more-item" onclick="showRecent()"><span>🕒</span>Recent</div>
      <div class="more-item" onclick="showShortcuts()"><span>⌨️</span>Shortcuts</div>
      <div class="more-item" onclick="location.href='/api/backup'"><span>💾</span>Backup</div>
      <div class="more-item" onclick="openRestore()"><span>📥</span>Restore</div>
    </div>
    <button class="btn" style="width:100%;margin-top:10px;padding:12px" onclick="document.getElementById('moreModal').classList.remove('show')">Close</button>
  </div>
</div>

<div class="modal-overlay" id="genericModal" onclick="if(event.target===this)this.classList.remove('show')">
  <div class="modal" id="genericModalContent"></div>
</div>

<div class="cmd-palette" id="cmdPalette">
  <input id="cmdPaletteInput" placeholder="Type a command..." oninput="filterPalette()" onkeydown="paletteKey(event)">
  <ul id="cmdPaletteList"></ul>
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
var PROJECT="__NAME__";
var currentPath="";
var openTabs=[];
var activeTabIdx=-1;
var cm=null;
var errorLines=[];
var buildPollTimer=null;
var buildStartTime=0;
var elapsedTimer=null;
var tasksSeen=0;
var EST_TOTAL=32;
var buildId=null;
var lastLineIdx=0;
var cmdHistory=[];
var histIdx=-1;
var autoSaveTimer=null;
var allFilesCache=[];
var previewMode="android";
var currentDevice="phone";
var logcatSid=null;
var logcatTimer=null;
var logcatLines=[];
var logcatLastIdx=0;

var I18N={
  en:{files:"Files",preview:"Preview",errors:"Errors",term:"Term",build:"Build",git:"Git",log:"Log"},
  bn:{files:"ফাইল",preview:"প্রিভিউ",errors:"ভুল",term:"টার্ম",build:"বিল্ড",git:"গিট",log:"লগ"}
};
function T(k){var l=localStorage.getItem("uiLang")||"en";return (I18N[l]&&I18N[l][k])||k;}

// ============ UTILS ============
function toast(msg,type){type=type||"success";var c=document.getElementById("toasts");var t=document.createElement("div");t.className="toast "+type;t.innerText=msg;c.appendChild(t);setTimeout(function(){t.remove()},3000);}
function esc(t){var d=document.createElement("div");d.innerText=t;return d.innerHTML;}
function switchPanel(id,el){
  document.querySelectorAll(".nav-item").forEach(function(n){n.classList.remove("active");});
  document.querySelectorAll(".panel").forEach(function(p){p.classList.remove("active");});
  if(el) el.classList.add("active");
  var panel=document.getElementById("panel-"+id);
  if(panel) panel.classList.add("active");
  if(id==="preview") refreshPreview();
  if(id==="git") gitAction("status");
}
function getMode(filename){
  var ext=filename.split(".").pop().toLowerCase();
  var map={py:"python",c:"text/x-csrc",cpp:"text/x-c++src",cc:"text/x-c++src",
    java:"text/x-java",kt:"text/x-kotlin",js:"javascript",xml:"xml",html:"htmlmixed",
    css:"css",json:"application/json",md:"markdown",sh:"text/x-sh",gradle:"text/x-java"};
  return map[ext]||"null";
}
function showModal(html){
  document.getElementById("genericModalContent").innerHTML=html;
  document.getElementById("genericModal").classList.add("show");
}
function closeModal(){document.getElementById("genericModal").classList.remove("show");}

// ============ FILES ============
async function loadFiles(path){
  currentPath=path||"";
  var box=document.getElementById("file-list");
  var bc=document.getElementById("breadcrumb");
  box.innerHTML='<div class="empty">Loading...</div>';
  try{
    var sort=(document.getElementById("sortBy")&&document.getElementById("sortBy").value)||"name";
    var r=await fetch("/api/project-files/"+encodeURIComponent(PROJECT)+"?path="+encodeURIComponent(currentPath)+"&sort="+sort);
    var d=await r.json();
    if(!r.ok){box.innerHTML='<div class="empty" style="color:#f87171">'+(d.error||r.status)+'</div>';return;}
    var parts=currentPath?currentPath.split("/"):[];
    var bcHtml='<span onclick="loadFiles(\'\')">📁 '+esc(PROJECT)+'</span>';
    var acc="";
    parts.forEach(function(p){acc+=(acc?"/":"")+p;
      bcHtml+=' / <span onclick="loadFiles(\''+acc+'\')">'+esc(p)+'</span>';});
    bc.innerHTML=bcHtml;
    allFilesCache=d.files||[];
    if(!allFilesCache.length){box.innerHTML='<div class="empty">Empty folder</div>';return;}
    renderFileList(allFilesCache);
  }catch(e){box.innerHTML='<div class="empty" style="color:#f87171">'+e.message+'</div>';}
}
function renderFileList(files){
  var box=document.getElementById("file-list");box.innerHTML="";
  if(currentPath){
    var parts=currentPath.split("/");var up=parts.slice(0,-1).join("/");
    var d=document.createElement("div");d.className="file-item folder";
    d.innerHTML="<span>⬆️</span><span class='name'>.. (up)</span>";
    d.onclick=function(){loadFiles(up);};box.appendChild(d);
  }
  files.forEach(function(f){
    var div=document.createElement("div");
    div.className="file-item "+(f.type==="directory"?"folder":"file");
    var icon=f.type==="directory"?"📁":"📄";
    var meta=f.type==="file"?((f.size_h||"")+" • "+(f.mtime||"")):(f.mtime||"");
    div.innerHTML="<span>"+icon+"</span><span class='name'>"+esc(f.name)+"</span><span class='meta'>"+esc(meta)+"</span>";
    div.onclick=function(){if(f.type==="directory")loadFiles(f.path);else openFile(f.path);};
    div.oncontextmenu=function(e){e.preventDefault();showItemMenu(f);};
    box.appendChild(div);
  });
}
function filterFiles(q){
  q=(q||"").toLowerCase().trim();
  if(!q){renderFileList(allFilesCache);return;}
  if(q.length>=2){
    fetch("/api/search/"+encodeURIComponent(PROJECT)+"?q="+encodeURIComponent(q))
      .then(function(r){return r.json();}).then(function(d){
        var box=document.getElementById("file-list");box.innerHTML="";
        if(!d.results||!d.results.length){box.innerHTML='<div class="empty">No results</div>';return;}
        d.results.forEach(function(f){
          var div=document.createElement("div");div.className="file-item file";
          div.innerHTML="<span>📄</span><span class='name'>"+esc(f.path)+"</span>";
          div.onclick=function(){openFile(f.path);};box.appendChild(div);
        });
      });
  }else{
    var filtered=allFilesCache.filter(function(f){return f.name.toLowerCase().indexOf(q)!==-1;});
    renderFileList(filtered);
  }
}
function clearSearch(){document.getElementById("searchInput").value="";renderFileList(allFilesCache);}
function showItemMenu(f){
  var c=prompt("Action for: "+f.name+"\n1=Open  2=Rename  3=Delete  4=Copy  5=Check");
  if(c==="1"){if(f.type==="directory")loadFiles(f.path);else openFile(f.path);}
  else if(c==="2"){var nn=prompt("New name:",f.name);if(nn&&nn!==f.name)fileOp("rename",f.path,nn);}
  else if(c==="3"){if(confirm("Delete "+f.name+"?"))fileOp("delete",f.path);}
  else if(c==="4"){var nn=prompt("Copy as:",f.name+"_copy");if(nn)fileOp("copy",f.path,nn);}
  else if(c==="5"&&f.type==="file")checkFileErrors(f.path,true);
}
async function newFile(){
  var n=prompt("New file name:");if(!n)return;
  var fp=currentPath?currentPath+"/"+n:n;
  var c=prompt("Initial content (optional):","")||"";
  await fileOp("create-file",fp,null,c);
}
async function newFolder(){
  var n=prompt("New folder name:");if(!n)return;
  var fp=currentPath?currentPath+"/"+n:n;
  await fileOp("create-folder",fp);
}
async function fileOp(action,path,newName,content){
  try{
    var body={project:PROJECT,action:action,path:path};
    if(newName) body.newName=newName;
    if(content!==undefined) body.content=content;
    var r=await fetch("/api/file-operation",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    var d=await r.json();
    if(!r.ok){toast(d.error||"Error","error");return;}
    loadFiles(currentPath);toast("Done");
  }catch(e){toast("Error: "+e,"error");}
}
async function doUpload(input){
  if(!input.files||!input.files[0])return;
  var fd=new FormData();fd.append("file",input.files[0]);fd.append("path",currentPath);
  try{
    var r=await fetch("/api/upload/"+encodeURIComponent(PROJECT),{method:"POST",body:fd});
    var d=await r.json();
    if(r.ok){toast("Uploaded");loadFiles(currentPath);}else toast(d.error||"Fail","error");
  }catch(e){toast("Error","error");}
  input.value="";
}
async function doExtract(input){
  if(!input.files||!input.files[0])return;
  var fd=new FormData();fd.append("file",input.files[0]);fd.append("path",currentPath);
  try{
    var r=await fetch("/api/extract/"+encodeURIComponent(PROJECT),{method:"POST",body:fd});
    var d=await r.json();
    if(r.ok){toast("Extracted");loadFiles(currentPath);}else toast(d.error||"Fail","error");
  }catch(e){toast("Error","error");}
  input.value="";
}
async function showRecent(){
  try{
    var r=await fetch("/api/recent");var d=await r.json();
    var html='<h3>🕒 Recent Files</h3>';
    if(!d.items||!d.items.length){html+='<div class="empty">No recent files</div>';}
    else{
      html+='<div style="max-height:400px;overflow-y:auto">';
      d.items.forEach(function(it){
        html+='<div class="file-item file" onclick="closeModal();location.href=\'/project/'+encodeURIComponent(it.project)+'\'"><span>📄</span><span class="name">'+esc(it.project)+' / '+esc(it.path)+'<br><small style="color:#94a3b8">'+esc(it.mtime)+'</small></span></div>';
      });
      html+='</div>';
    }
    html+='<button class="btn" style="width:100%;margin-top:10px;padding:12px" onclick="closeModal()">Close</button>';
    showModal(html);
  }catch(e){toast("Error","error");}
}

// ============ EDITOR ============
async function openFile(path){
  var existing=-1;
  for(var i=0;i<openTabs.length;i++){if(openTabs[i].path===path){existing=i;break;}}
  if(existing>=0){switchTab(existing);document.getElementById("editor-box").style.display="flex";return;}
  try{
    var r=await fetch("/api/file-content/"+encodeURIComponent(PROJECT)+"?path="+encodeURIComponent(path));
    var d=await r.json();
    if(!r.ok){toast(d.error||"Error","error");return;}
    openTabs.push({path:path,content:d.content,mode:getMode(path),dirty:false});
    activeTabIdx=openTabs.length-1;
    document.getElementById("editor-box").style.display="flex";
    renderTabs();loadTabContent();
    var ext=path.split(".").pop().toLowerCase();
    var runnable=["py","c","cpp","cc","php","js","go","rs","rb","sh","java"];
    document.getElementById("runBtn").style.display=runnable.indexOf(ext)!==-1?"inline-block":"none";
    setTimeout(checkCurrentFile,500);
  }catch(e){toast("Error: "+e,"error");}
}
function renderTabs(){
  var bar=document.getElementById("editorTabs");bar.innerHTML="";
  openTabs.forEach(function(t,i){
    var div=document.createElement("div");
    div.className="editor-tab"+(i===activeTabIdx?" active":"");
    var name=t.path.split("/").pop();
    div.innerHTML=(t.dirty?"• ":"")+esc(name)+' <span class="close-tab" data-i="'+i+'">×</span>';
    div.onclick=function(e){
      if(e.target.classList.contains("close-tab"))closeTab(parseInt(e.target.dataset.i));
      else switchTab(i);
    };
    bar.appendChild(div);
  });
}
function switchTab(idx){
  if(cm&&activeTabIdx>=0)openTabs[activeTabIdx].content=cm.getValue();
  activeTabIdx=idx;renderTabs();loadTabContent();
}
function loadTabContent(){
  if(activeTabIdx<0||!openTabs[activeTabIdx])return;
  var tab=openTabs[activeTabIdx];
  document.getElementById("editor-filename").innerText=tab.path;
  if(cm){cm.toTextArea();cm=null;}
  cm=CodeMirror.fromTextArea(document.getElementById("editor"),{
    lineNumbers:true,mode:tab.mode,
    theme:localStorage.getItem("cmTheme")||"dracula",
    matchBrackets:true,autoCloseBrackets:true,indentUnit:4,tabSize:4,
    lineWrapping:true,foldGutter:true,
    gutters:["CodeMirror-linenumbers","CodeMirror-foldgutter"],
    extraKeys:{
      "Ctrl-S":function(){saveFile(false);},
      "Cmd-S":function(){saveFile(false);},
      "Ctrl-B":function(){buildApk();},
      "Ctrl-Shift-P":function(){openCommandPalette();}
    }
  });
  cm.setValue(tab.content);
  cm.on("change",function(){
    openTabs[activeTabIdx].dirty=true;renderTabs();
    if(localStorage.getItem("autoSave")==="on"){
      clearTimeout(autoSaveTimer);
      autoSaveTimer=setTimeout(function(){saveFile(true);},2500);
    }
    updateSplitPreview();
  });
  setTimeout(function(){cm.refresh();},80);
  applyFontSize(localStorage.getItem("fontSize")||13);
}
function closeTab(idx){
  if(openTabs[idx].dirty&&!confirm("Unsaved changes. Close anyway?"))return;
  openTabs.splice(idx,1);
  if(openTabs.length===0){closeEditor();return;}
  if(activeTabIdx>=openTabs.length)activeTabIdx=openTabs.length-1;
  if(idx<=activeTabIdx&&activeTabIdx>0)activeTabIdx--;
  renderTabs();loadTabContent();
}
function closeEditor(){
  if(cm&&activeTabIdx>=0)openTabs[activeTabIdx].content=cm.getValue();
  document.getElementById("editor-box").style.display="none";
  document.getElementById("runBtn").style.display="none";
  document.getElementById("splitPane").classList.remove("show");
  if(cm){cm.toTextArea();cm=null;}
}
function doSelectAll(){if(cm){cm.execCommand("selectAll");cm.focus();}}
async function doCut(){if(!cm)return;var sel=cm.getSelection();if(!sel){toast("Select first");return;}try{await navigator.clipboard.writeText(sel);cm.replaceSelection("");toast("Cut");}catch(e){toast("Cut failed","error");}}
async function doCopy(){if(!cm)return;var sel=cm.getSelection();if(!sel){toast("Select first");return;}try{await navigator.clipboard.writeText(sel);toast("Copied");}catch(e){var ta=document.createElement("textarea");ta.value=sel;document.body.appendChild(ta);ta.select();document.execCommand("copy");document.body.removeChild(ta);toast("Copied");}}
async function doPaste(){if(!cm)return;try{var txt=await navigator.clipboard.readText();cm.replaceSelection(txt);}catch(e){toast("Paste blocked","error");}}
function doUndo(){if(cm)cm.undo();}
function doRedo(){if(cm)cm.redo();}
function doFind(){if(cm)cm.execCommand("find");}
function doIndent(){if(!cm)return;var sel=cm.getSelection();if(!sel){cm.execCommand("indentMore");return;}cm.replaceSelection(sel.split("\n").map(function(l){return "    "+l;}).join("\n"));}
function formatCode(){
  if(!cm)return;
  var lines=cm.getValue().split("\n");
  var indent=0;
  var formatted=lines.map(function(l){
    var t=l.trim();
    if(t.startsWith("}")||t.startsWith(")")||t.startsWith("]"))indent=Math.max(0,indent-1);
    var res="    ".repeat(indent)+t;
    if(t.endsWith("{")||t.endsWith("("))indent++;
    return res;
  }).join("\n");
  cm.setValue(formatted);toast("Formatted");
}
async function saveFile(silent){
  if(activeTabIdx<0||!cm)return;
  var tab=openTabs[activeTabIdx];
  var content=cm.getValue();
  try{
    var r=await fetch("/api/file-content/"+encodeURIComponent(PROJECT)+"?path="+encodeURIComponent(tab.path),{
      method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({content:content})
    });
    var d=await r.json();
    if(!r.ok){if(!silent)toast(d.error||"Save failed","error");return;}
    tab.content=content;tab.dirty=false;renderTabs();
    if(!silent)toast("Saved");
  }catch(e){if(!silent)toast("Save error","error");}
}
async function checkCurrentFile(){
  if(activeTabIdx<0||!cm)return;
  await saveFile(true);
  var path=openTabs[activeTabIdx].path;
  var result=await checkFileErrors(path,false);
  if(!result)return;
  errorLines.forEach(function(line){
    if(cm&&cm.getLineHandle(line-1))
      cm.removeLineClass(cm.getLineHandle(line-1),"background","cm-error-line");
  });
  errorLines=[];
  var badge=document.getElementById("editor-err-badge");
  if(!result.errors.length){badge.innerText="0 ✓";badge.className="badge ok";}
  else{
    badge.innerText=result.errors.length+" err";badge.className="badge err";
    result.errors.forEach(function(e){
      if(e.line&&cm){var h=cm.getLineHandle(e.line-1);if(h){cm.addLineClass(h,"background","cm-error-line");errorLines.push(e.line);}}
    });
  }
}
async function checkFileErrors(path,showAlert){
  try{
    var r=await fetch("/api/check-file/"+encodeURIComponent(PROJECT)+"?path="+encodeURIComponent(path));
    var d=await r.json();
    if(!r.ok)return{errors:[]};
    if(showAlert){if(!d.errors.length)toast("No errors");else toast(d.errors.length+" error(s)","error");}
    return d;
  }catch(e){return{errors:[]};}
}
async function scanAllErrors(){
  document.getElementById("scanBtn").innerText="⏳";
  document.getElementById("errInfo").innerText="Scanning...";
  document.getElementById("err-list").innerHTML="";
  try{
    var r=await fetch("/api/scan-errors/"+encodeURIComponent(PROJECT));
    var d=await r.json();
    if(!r.ok){document.getElementById("errInfo").innerText="Scan failed";return;}
    var total=0,bad=0;
    var box=document.getElementById("err-list");
    (d.results||[]).forEach(function(f){
      if(f.errors&&f.errors.length){
        total+=f.errors.length;bad++;
        var fh=document.createElement("div");
        fh.style.cssText="color:#fbbf24;font-weight:700;margin-top:12px;font-size:13px";
        fh.innerText="📄 "+f.path+" — "+f.errors.length+" error(s)";
        box.appendChild(fh);
        f.errors.forEach(function(e){
          var item=document.createElement("div");
          item.className="err-item";
          item.innerHTML='<div style="color:#fbbf24;font-weight:700">Line '+e.line+', Col '+(e.col||1)+'</div><div>'+esc(e.message)+'</div>'+(e.code?'<div style="background:#450a0a;padding:4px;margin-top:4px;border-radius:4px;font-size:11px">'+esc(e.code)+'</div>':'');
          item.onclick=function(){jumpToError(f.path,e.line);};
          box.appendChild(item);
        });
      }
    });
    var badge=document.getElementById("errBadgeNav");
    if(total===0){badge.innerText="0";badge.className="badge ok";document.getElementById("errInfo").innerText="✓ No errors in "+d.scanned+" files";}
    else{badge.innerText=total;badge.className="badge err";document.getElementById("errInfo").innerText=bad+" file(s) • "+total+" error(s)";}
  }catch(e){document.getElementById("errInfo").innerText="Error: "+e;}
  document.getElementById("scanBtn").innerText="🔍";
}
async function jumpToError(path,line){
  await openFile(path);
  setTimeout(function(){
    if(cm&&line){cm.setCursor({line:line-1,ch:0});cm.focus();
      var coords=cm.charCoords({line:line-1,ch:0},"local");
      cm.scrollTo(null,coords.top-80);}
  },400);
}
async function showHistory(){
  if(activeTabIdx<0)return;
  var path=openTabs[activeTabIdx].path;
  try{
    var r=await fetch("/api/history/"+encodeURIComponent(PROJECT)+"?path="+encodeURIComponent(path));
    var d=await r.json();
    var html='<h3>🕒 History: '+esc(path.split("/").pop())+'</h3>';
    if(!d.versions||!d.versions.length) html+='<div class="empty">No versions yet</div>';
    else{
      d.versions.forEach(function(v){
        html+='<div class="file-item file" onclick="restoreHistory(\''+esc(path)+'\',\''+esc(v.file)+'\')"><span>📄</span><span class="name">'+esc(v.mtime)+'<br><small style="color:#94a3b8">'+esc(v.size)+'</small></span></div>';
      });
    }
    html+='<button class="btn" style="width:100%;margin-top:10px;padding:12px" onclick="closeModal()">Close</button>';
    showModal(html);
  }catch(e){toast("Error","error");}
}
async function restoreHistory(path,version){
  if(!confirm("Restore this version?"))return;
  try{
    var r=await fetch("/api/history-restore",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({project:PROJECT,path:path,version:version})});
    var d=await r.json();
    if(r.ok){toast("Restored");closeModal();if(cm)cm.setValue((await (await fetch("/api/file-content/"+encodeURIComponent(PROJECT)+"?path="+encodeURIComponent(path))).json()).content);}
    else toast(d.error||"Fail","error");
  }catch(e){toast("Error","error");}
}

// ============ TERMINAL ============
function clearTerminal(){document.getElementById("terminal-output").innerText="$ Terminal cleared\n";}
function termKey(e){
  if(e.key==="Enter")runCmd();
  else if(e.key==="ArrowUp"){e.preventDefault();if(cmdHistory.length&&histIdx<cmdHistory.length-1){histIdx++;document.getElementById("cmd").value=cmdHistory[cmdHistory.length-1-histIdx];}}
  else if(e.key==="ArrowDown"){e.preventDefault();if(histIdx>0){histIdx--;document.getElementById("cmd").value=cmdHistory[cmdHistory.length-1-histIdx];}else{histIdx=-1;document.getElementById("cmd").value="";}}
}
async function runCmd(){
  var cmd=document.getElementById("cmd").value.trim();
  if(!cmd)return;
  cmdHistory.push(cmd);histIdx=-1;
  var out=document.getElementById("terminal-output");
  out.innerText+="\n$ "+cmd+"\n";
  document.getElementById("cmd").value="";
  out.scrollTop=out.scrollHeight;
  try{
    var r=await fetch("/api/run-command",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({project:PROJECT,cmd:cmd})});
    var d=await r.json();
    if(d.stdout)out.innerText+=d.stdout;
    if(d.stderr)out.innerText+="\n[stderr]\n"+d.stderr;
    if(d.error)out.innerText+="\n[error] "+d.error;
    out.innerText+="\n[exit "+(d.returncode!=null?d.returncode:"?")+"]\n";
    out.scrollTop=out.scrollHeight;
  }catch(e){out.innerText+="\n[error] "+e+"\n";}
}
async function saveCurrentCmd(){
  var cmd=prompt("Command to save:");if(!cmd)return;
  try{
    await fetch("/api/saved-commands",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({cmd:cmd})});
    toast("Saved");
  }catch(e){toast("Error","error");}
}
async function showSavedCommands(){
  try{
    var r=await fetch("/api/saved-commands");var d=await r.json();
    var html='<h3>⭐ Saved Commands</h3>';
    if(!d.items||!d.items.length) html+='<div class="empty">No saved commands</div>';
    else{
      d.items.forEach(function(c){
        html+='<div class="file-item file"><span>⚡</span><span class="name" style="font-family:monospace">'+esc(c)+'</span><span class="meta" onclick="runSavedCmd(\''+esc(c).replace(/'/g,"\\'")+'\')">▶</span></div>';
      });
    }
    html+='<button class="btn" style="width:100%;margin-top:10px;padding:12px" onclick="closeModal()">Close</button>';
    showModal(html);
  }catch(e){toast("Error","error");}
}
function runSavedCmd(cmd){
  closeModal();switchPanel("terminal",document.querySelector('[data-panel="terminal"]'));
  document.getElementById("cmd").value=cmd;runCmd();
}

// ============ RUN CODE ============
async function runCurrent(){
  if(activeTabIdx<0){toast("Open a file first","error");return;}
  if(cm)await saveFile(true);
  document.querySelectorAll(".panel").forEach(function(p){p.classList.remove("active");});
  document.getElementById("panel-output").classList.add("active");
  var path=openTabs[activeTabIdx].path;
  var outBox=document.getElementById("output-box");
  outBox.innerText="Running "+path+"...\n\n";
  try{
    var r=await fetch("/api/run-code",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({project:PROJECT,path:path})});
    var d=await r.json();
    document.getElementById("run-info").innerHTML="<b>File:</b> "+esc(path)+" | <b>Lang:</b> "+esc(d.language||"?")+" | <b>Exit:</b> "+(d.returncode!=null?d.returncode:"?");
    var text="";
    if(d.command)text+="$ "+d.command+"\n\n";
    if(d.stdout)text+=d.stdout;
    if(d.stderr)text+="\n[stderr]\n"+d.stderr;
    if(d.error)text+="\n[error] "+d.error;
    outBox.innerText=text||"(no output)";
  }catch(e){outBox.innerText="[error] "+e;}
}

// ============ PREVIEW ============
function setDevice(d,el){
  currentDevice=d;
  document.querySelectorAll(".device-frames button").forEach(function(b){b.classList.remove("active");});
  if(el)el.classList.add("active");
  var f=document.getElementById("previewFrame");
  f.className="preview-frame"+(d==="tablet"?" tablet":d==="desktop"?" desktop":"");
}
function togglePreviewMode(){
  previewMode=previewMode==="android"?"html":"android";
  document.getElementById("prevModeBtn").innerText=previewMode==="android"?"HTML":"Android";
  refreshPreview();
}
async function refreshPreview(){
  var box=document.getElementById("previewContent");
  box.innerHTML='<p style="text-align:center;color:#64748b;padding:30px">Loading...</p>';
  try{
    if(previewMode==="html"){
      var candidates=["index.html","app/src/main/assets/index.html","public/index.html"];
      for(var i=0;i<candidates.length;i++){
        var r=await fetch("/api/file-content/"+encodeURIComponent(PROJECT)+"?path="+encodeURIComponent(candidates[i]));
        if(r.ok){
          var d=await r.json();
          box.innerHTML='<iframe style="width:100%;height:440px;border:0;background:#fff" srcdoc="'+d.content.replace(/"/g,"&quot;")+'"></iframe>';
          return;
        }
      }
      box.innerHTML='<p style="text-align:center;color:#64748b;padding:40px">No index.html found</p>';
      return;
    }
    var candidates=["app/src/main/res/layout/activity_main.xml","res/layout/activity_main.xml"];
    var content=null;
    for(var j=0;j<candidates.length;j++){
      var r2=await fetch("/api/file-content/"+encodeURIComponent(PROJECT)+"?path="+encodeURIComponent(candidates[j]));
      if(r2.ok){var d2=await r2.json();content=d2.content;break;}
    }
    if(!content&&activeTabIdx>=0&&openTabs[activeTabIdx].path.endsWith(".xml"))
      content=cm?cm.getValue():openTabs[activeTabIdx].content;
    if(!content){box.innerHTML='<p style="text-align:center;color:#64748b;padding:40px">No layout found</p>';return;}
    box.innerHTML=renderAndroidXml(content);
  }catch(e){box.innerHTML='<p style="color:#f87171">Error</p>';}
}
function renderAndroidXml(xmlStr){
  try{
    var parser=new DOMParser();
    var doc=parser.parseFromString(xmlStr,"text/xml");
    var root=doc.documentElement;
    if(!root||root.tagName==="parsererror")return '<p style="color:#f87171">Invalid XML</p>';
    return renderNode(root);
  }catch(e){return '<p style="color:#f87171">Parse error</p>';}
}
function renderNode(node){
  if(node.nodeType!==1)return "";
  var tag=node.tagName.replace(/^.*:/,"");
  var attrs={};
  if(node.attributes){
    for(var i=0;i<node.attributes.length;i++){
      var a=node.attributes[i];
      attrs[a.name.replace(/^android:/,"").replace(/^app:/,"")]=a.value;
    }
  }
  var children="";
  for(var j=0;j<node.childNodes.length;j++)children+=renderNode(node.childNodes[j]);
  if(tag==="TextView")return '<div style="margin:6px 0;color:#fff">'+esc(attrs.text||attrs.hint||"Text")+'</div>';
  if(tag==="Button")return '<button style="width:100%;padding:12px;margin:8px 0;border:0;border-radius:10px;background:#3b82f6;color:#fff">'+esc(attrs.text||"Button")+'</button>';
  if(tag==="EditText")return '<input style="width:100%;padding:12px;margin:8px 0;border-radius:10px;border:1px solid #334155;background:#1e293b;color:#fff" placeholder="'+esc(attrs.hint||"")+'">';
  if(tag==="ListView")return '<div style="background:#1e293b;border-radius:8px;padding:8px;color:#cbd5e1">List: item 1, item 2, item 3...</div>';
  if(tag==="ImageView")return '<div style="background:#1e293b;padding:30px;text-align:center;border-radius:8px;color:#94a3b8">🖼 Image</div>';
  return '<div>'+children+'</div>';
}
function toggleSplitPreview(){
  var sp=document.getElementById("splitPane");
  sp.classList.toggle("show");
  if(sp.classList.contains("show"))updateSplitPreview();
}
async function updateSplitPreview(){
  var sp=document.getElementById("splitPane");
  if(!sp.classList.contains("show"))return;
  if(!cm){sp.innerHTML="No editor";return;}
  var val=cm.getValue();
  if(val.trim().startsWith("<?xml")||val.trim().startsWith("<LinearLayout")){
    sp.innerHTML='<div style="transform:scale(.55);transform-origin:top left;width:180%">'+renderAndroidXml(val)+'</div>';
  }else if(val.trim().startsWith("<!DOCTYPE")||val.trim().toLowerCase().startsWith("<html")){
    sp.innerHTML='<iframe style="width:100%;height:100%;border:0;background:#fff" srcdoc="'+val.replace(/"/g,"&quot;")+'"></iframe>';
  }else{
    sp.innerHTML='<pre style="color:#cbd5e1;font-size:11px;white-space:pre-wrap">'+esc(val.slice(0,3000))+'</pre>';
  }
}

// ============ BUILD ============
function formatTime(sec){sec=Math.floor(sec);if(sec<60)return sec+"s";returnMath.floor(sec/60)+"m "+(sec%60)+"s";}
function startElapsedTimer(){
  if(elapsedTimer)clearInterval(elapsedTimer);
  elapsedTimer=setInterval(function(){
    var el=(Date.now()-buildStartTime)/1000;
    var elEl=document.getElementById("statElapsed");
    if(elEl)elEl.innerText=formatTime(el);
  },500);
}
function processBuildLine(line){
  var log=document.getElementById("buildLog");
  var cls="";
  if(line.indexOf("BUILD SUCCESSFUL")!==-1)cls="color:#4ade80";
  else if(line.indexOf("BUILD FAILED")!==-1||line.indexOf("error:")!==-1)cls="color:#f87171";
  else if(line.indexOf("> Task")!==-1)cls="color:#fbbf24";
  else if(line.indexOf("💡 Hint:")!==-1)cls="color:#fbbf24;font-weight:600";
  log.innerHTML+="\n<span style='"+cls+"'>"+esc(line)+"</span>";
  log.scrollTop=log.scrollHeight;
  var m=line.match(/^>\s+Task\s+(:[\w:]+)/);
  if(m){
    tasksSeen++;
    document.getElementById("currentTask").innerText="▶ "+m[1];
    var pct=Math.min(95,Math.round(tasksSeen/EST_TOTAL*100));
    document.getElementById("buildProgressBar").style.width=pct+"%";
    document.getElementById("buildProgressText").innerText=pct+"%";
  }
  if(line.indexOf("BUILD SUCCESSFUL")!==-1){
    document.getElementById("buildProgressBar").style.width="100%";
    document.getElementById("buildProgressText").innerText="100%";
    document.getElementById("currentTask").innerText="✅ Build complete";
  }
  if(line.indexOf("BUILD FAILED")!==-1)
    document.getElementById("currentTask").innerText="❌ Build failed";
}
async function pollBuild(){
  if(!buildId)return;
  try{
    var r=await fetch("/api/build-poll/"+buildId+"?since="+lastLineIdx);
    var d=await r.json();
    if(d.lines&&d.lines.length){d.lines.forEach(processBuildLine);lastLineIdx=d.total;}
    if(d.status==="done"){
      clearInterval(buildPollTimer);buildPollTimer=null;
      if(elapsedTimer){clearInterval(elapsedTimer);elapsedTimer=null;}
      if(d.success&&d.apk_path){
        document.getElementById("buildProgressBar").style.width="100%";
        document.getElementById("buildProgressText").innerText="100%";
        document.getElementById("currentTask").innerText="✅ Build successful";
        document.getElementById("buildStatusMsg").innerText="✓ APK ready!";
        document.getElementById("buildStatusMsg").style.color="#4ade80";
        document.getElementById("apk-box").style.display="block";
        document.getElementById("apkDownloadBtn").onclick=function(){location.href="/api/download-apk/"+encodeURIComponent(PROJECT);};
        toast("APK Ready!");
        try{if(Notification.permission==="granted")new Notification("Zihad IDE","✅ Build successful!");}catch(e){}
      }else{
        document.getElementById("currentTask").innerText="❌ Build failed";
        document.getElementById("buildStatusMsg").innerText="✗ Failed";
        document.getElementById("buildStatusMsg").style.color="#f87171";
        toast("Build failed","error");
      }
    }
  }catch(e){}
}
async function buildApk(){
  if(!confirm("Build APK?"))return;
  switchPanel("build",document.querySelector('[data-panel="build"]'));
  document.getElementById("buildLog").innerHTML="$ Starting build...";
  document.getElementById("buildProgressBar").style.width="0%";
  document.getElementById("buildProgressText").innerText="0%";
  document.getElementById("currentTask").innerHTML="Starting...";
  document.getElementById("buildStatusMsg").innerText="Starting...";
  document.getElementById("buildStatusMsg").style.color="#94a3b8";
  document.getElementById("apk-box").style.display="none";
  tasksSeen=0;lastLineIdx=0;EST_TOTAL=32;
  try{try{if(Notification.permission==="default")await Notification.requestPermission();}catch(e){}
    var r=await fetch("/api/build-start",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({project:PROJECT})});
    var d=await r.json();
    if(!r.ok){toast(d.error||"Error","error");return;}
    buildId=d.build_id;buildStartTime=Date.now();
    startElapsedTimer();
    if(buildPollTimer)clearInterval(buildPollTimer);
    buildPollTimer=setInterval(pollBuild,700);
    pollBuild();
  }catch(e){toast("Error: "+e,"error");}
}
async function adbInstall(){
  toast("Trying ADB install...");
  try{
    var r=await fetch("/api/adb-install",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({project:PROJECT})});
    var d=await r.json();
    if(r.ok&&d.success)toast("Installed via ADB!");
    else toast(d.error||"ADB failed","error");
  }catch(e){toast("ADB error","error");}
}
async function cleanBuild(deep){
  if(!confirm(deep?"Deep clean (also ~/.gradle transforms)?" : "Clean build dirs?"))return;
  try{
    var r=await fetch("/api/cache-clean",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({project:PROJECT,deep:deep})});
    var d=await r.json();
    if(r.ok)toast("Cleaned: "+(d.cleared||[]).join(", ")||"nothing");
    else toast(d.error||"Fail","error");
  }catch(e){toast("Error","error");}
}
async function exportZip(){toast("Creating ZIP...");location.href="/api/export-zip/"+encodeURIComponent(PROJECT);}

// ============ GIT ============
function gitLog(text,cls){
  var box=document.getElementById("gitOutput");
  box.innerHTML="<span style='color:"+(cls||"#cbd5e1")+"'>"+esc(text).replace(/\n/g,"<br>")+"</span>";
}
async function gitAction(a){
  try{
    if(a==="init"){
      gitLog("Initializing...");
      var r=await fetch("/api/git/init/"+encodeURIComponent(PROJECT),{method:"POST"});
      var d=await r.json();
      gitLog(d.out||d.err||"Init done",d.success?"#4ade80":"#f87171");
      if(!d.success)toast("Init failed","error");
      else toast("Git initialized");
      return;
    }
    if(a==="status"){
      var r=await fetch("/api/git/status/"+encodeURIComponent(PROJECT));
      var d=await r.json();
      document.getElementById("gitInfo").innerText="Branch: "+(d.branch||"?")+" | "+(d.init?"initialized":"not initialized");
      if(!d.init){gitLog("Repository not initialized. Tap Init.");return;}
      if(!d.files||!d.files.length){gitLog("✓ Working tree clean","#4ade80");return;}
      gitLog("Modified files:\n"+d.files.join("\n"));
      return;
    }
    if(a==="add"){
      var r=await fetch("/api/git/add/"+encodeURIComponent(PROJECT),{method:"POST"});
      var d=await r.json();
      gitLog(d.err||"Added","#4ade80");toast("Added");
      return;
    }
    if(a==="log"){
      var r=await fetch("/api/git/log/"+encodeURIComponent(PROJECT));
      var d=await r.json();
      gitLog(d.log.length?(d.log.join("\n")):"No commits");
      return;
    }
    if(a==="diff"){
      var r=await fetch("/api/git/diff/"+encodeURIComponent(PROJECT));
      var d=await r.json();
      gitLog(d.diff||"No changes");
      return;
    }
    if(a==="branches"){
      var r=await fetch("/api/git/branch/"+encodeURIComponent(PROJECT),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"list"})});
      var d=await r.json();
      gitLog("Branches:\n"+(d.branches||[]).join("\n"));
      return;
    }
  }catch(e){gitLog("Error: "+e,"#f87171");}
}
async function gitCommitPrompt(){
  var msg=prompt("Commit message:","Update");
  if(!msg)return;
  try{
    var r=await fetch("/api/git/commit/"+encodeURIComponent(PROJECT),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message:msg})});
    var d=await r.json();
    gitLog(d.out||d.err,d.success?"#4ade80":"#f87171");
    if(d.success)toast("Committed");
  }catch(e){toast("Error","error");}
}
async function gitRemote(action){
  try{
    var r=await fetch("/api/git/remote/"+encodeURIComponent(PROJECT),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:action})});
    var d=await r.json();
    gitLog((d.out||"")+"\n"+(d.err||""),d.success?"#4ade80":"#f87171");
  }catch(e){gitLog("Error: "+e,"#f87171");}
}
async function gitSetRemote(){
  var url=prompt("Remote URL (origin):","https://github.com/user/repo.git");
  if(!url)return;
  try{
    var r=await fetch("/api/git/remote/"+encodeURIComponent(PROJECT),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"set",url:url})});
    var d=await r.json();
    if(d.success)toast("Remote set");else toast(d.err||"Fail","error");
  }catch(e){toast("Error","error");}
}

// ============ LOGCAT ============
async function logcatStart(){
  try{
    var r=await fetch("/api/logcat/start",{method:"POST"});
    var d=await r.json();
    if(!r.ok){toast(d.error||"Fail","error");return;}
    logcatSid=d.session;logcatLines=[];logcatLastIdx=0;
    if(logcatTimer)clearInterval(logcatTimer);
    logcatTimer=setInterval(logcatPoll,700);
    toast("Logcat started");
  }catch(e){toast("Error","error");}
}
async function logcatPoll(){
  if(!logcatSid)return;
  try{
    var r=await fetch("/api/logcat/poll/"+logcatSid+"?since="+logcatLastIdx);
    var d=await r.json();
    if(d.lines&&d.lines.length){logcatLines=logcatLines.concat(d.lines);logcatLastIdx=d.total;renderLogcat();}
  }catch(e){}
}
function renderLogcat(){
  var box=document.getElementById("logcatBox");
  var filter=(document.getElementById("lcFilter").value)||"all";
  var filtered=logcatLines;
  if(filter==="error")filtered=logcatLines.filter(function(l){return l.indexOf(" E ")>=0||l.toLowerCase().indexOf("error")>=0;});
  else if(filter==="warn")filtered=logcatLines.filter(function(l){return l.indexOf(" E ")>=0||l.indexOf(" W ")>=0||l.toLowerCase().indexOf("error")>=0;});
  else if(filter==="info")filtered=logcatLines.filter(function(l){return l.indexOf(" I ")>=0||l.indexOf(" E ")>=0||l.indexOf(" W ")>=0;});
  box.innerHTML=filtered.slice(-500).map(function(l){
    var cls="";
    if(l.indexOf(" E ")>=0||l.toLowerCase().indexOf("error")>=0)cls="err";
    else if(l.indexOf(" W ")>=0)cls="warn";
    else if(l.indexOf(" I ")>=0)cls="info";
    return '<div class="logcat-line '+cls+'">'+esc(l)+'</div>';
  }).join("");
  box.scrollTop=box.scrollHeight;
}
async function logcatStop(){
  if(!logcatSid)return;
  if(logcatTimer)clearInterval(logcatTimer);logcatTimer=null;
  try{await fetch("/api/logcat/stop/"+logcatSid,{method:"POST"});}catch(e){}
  logcatSid=null;toast("Logcat stopped");
}
function logcatClear(){logcatLines=[];logcatLastIdx=0;renderLogcat();}

// ============ MORE MENU TOOLS ============
function showMoreMenu(){document.getElementById("moreModal").classList.add("show");document.querySelectorAll(".modal-overlay").forEach(function(m){if(m.id!=="moreModal")m.classList.remove("show");});}
function openPkgRename(){
  showModal('<h3>📦 Rename Package</h3><input id="oldPkg" placeholder="Old package"><input id="newPkg" placeholder="New package"><button class="btn btn-primary" style="width:100%;padding:12px;margin-top:8px" onclick="doPkgRename()">Update All</button><button class="btn" style="width:100%;margin-top:6px;padding:12px" onclick="closeModal()">Cancel</button>');
}
async function doPkgRename(){
  var oldP=document.getElementById("oldPkg").value.trim();
  var newP=document.getElementById("newPkg").value.trim();
  if(!oldP||!newP){toast("Fill both","error");return;}
  try{
    var r=await fetch("/api/rename-package",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({project:PROJECT,old:oldP,new:newP})});
    var d=await r.json();
    if(r.ok){toast("Updated "+d.updated+" files");closeModal();}
    else toast(d.error||"Fail","error");
  }catch(e){toast("Error","error");}
}
async function openStrings(){
  try{
    var r=await fetch("/api/strings/"+encodeURIComponent(PROJECT));var d=await r.json();
    var items=d.items||[];
    var html='<h3>🔤 Strings Editor</h3><div id="strList" style="max-height:300px;overflow-y:auto">';
    items.forEach(function(it,i){
      html+='<div style="display:flex;gap:6px;margin:4px 0"><input value="'+esc(it.name)+'" placeholder="key" style="flex:1" onchange="strUpdate('+i+',this.value,\'name\')"><input value="'+esc(it.value)+'" placeholder="value" style="flex:2" onchange="strUpdate('+i+',this.value,\'value\')"><button class="btn btn-danger" style="padding:6px" onclick="strDel('+i+')">×</button></div>';
    });
    html+='</div><button class="btn btn-success" style="width:100%;margin-top:8px;padding:10px" onclick="strAdd()">+ Add</button><button class="btn btn-primary" style="width:100%;margin-top:6px;padding:12px" onclick="strSave()">💾 Save</button><button class="btn" style="width:100%;margin-top:6px;padding:12px" onclick="closeModal()">Cancel</button>';
    window._strItems=items;
    showModal(html);
  }catch(e){toast("Error","error");}
}
function strUpdate(i,v,k){window._strItems[i][k]=v;}
function strDel(i){window._strItems.splice(i,1);openStringsAgain();}
function strAdd(){window._strItems.push({name:"new_string",value:""});openStringsAgain();}
function openStringsAgain(){
  var items=window._strItems;
  var html='<h3>🔤 Strings Editor</h3><div id="strList" style="max-height:300px;overflow-y:auto">';
  items.forEach(function(it,i){
    html+='<div style="display:flex;gap:6px;margin:4px 0"><input value="'+esc(it.name)+'" placeholder="key" style="flex:1" onchange="strUpdate('+i+',this.value,\'name\')"><input value="'+esc(it.value)+'" placeholder="value" style="flex:2" onchange="strUpdate('+i+',this.value,\'value\')"><button class="btn btn-danger" style="padding:6px" onclick="strDel('+i+')">×</button></div>';
  });
  html+='</div><button class="btn btn-success" style="width:100%;margin-top:8px;padding:10px" onclick="strAdd()">+ Add</button><button class="btn btn-primary" style="width:100%;margin-top:6px;padding:12px" onclick="strSave()">💾 Save</button><button class="btn" style="width:100%;margin-top:6px;padding:12px" onclick="closeModal()">Cancel</button>';
  showModal(html);
}
async function strSave(){
  try{
    var r=await fetch("/api/strings/"+encodeURIComponent(PROJECT),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({items:window._strItems})});
    var d=await r.json();
    if(r.ok){toast("Saved "+d.count);closeModal();}else toast(d.error||"Fail","error");
  }catch(e){toast("Error","error");}
}
async function openThemeBuilder(){
  try{
    var r=await fetch("/api/theme/"+encodeURIComponent(PROJECT));var d=await r.json();
    var colors=d.colors||[];
    window._themeColors=colors;
    renderThemeModal();
  }catch(e){toast("Error","error");}
}
function renderThemeModal(){
  var html='<h3>🎨 Theme Builder</h3><div style="max-height:300px;overflow-y:auto">';
  window._themeColors.forEach(function(c,i){
    html+='<div style="display:flex;gap:6px;margin:4px 0;align-items:center"><input value="'+esc(c.name)+'" placeholder="name" style="flex:1" onchange="thmUpdate('+i+',this.value,\'name\')"><input type="color" value="'+esc(c.value)+'" style="width:50px;height:40px;padding:2px" onchange="thmUpdate('+i+',this.value,\'value\')"><input value="'+esc(c.value)+'" style="flex:1" onchange="thmUpdate('+i+',this.value,\'value\')"><button class="btn btn-danger" style="padding:6px" onclick="thmDel('+i+')">×</button></div>';
  });
  html+='</div><button class="btn btn-success" style="width:100%;margin-top:8px;padding:10px" onclick="thmAdd()">+ Color</button><button class="btn btn-primary" style="width:100%;margin-top:6px;padding:12px" onclick="thmSave()">💾 Save</button><button class="btn" style="width:100%;margin-top:6px;padding:12px" onclick="closeModal()">Cancel</button>';
  showModal(html);
}
function thmUpdate(i,v,k){window._themeColors[i][k]=v;}
function thmDel(i){window._themeColors.splice(i,1);renderThemeModal();}
function thmAdd(){window._themeColors.push({name:"new_color",value:"#3b82f6"});renderThemeModal();}
async function thmSave(){
  try{
    var r=await fetch("/api/theme/"+encodeURIComponent(PROJECT),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({colors:window._themeColors})});
    var d=await r.json();
    if(r.ok){toast("Saved");closeModal();}else toast(d.error||"Fail","error");
  }catch(e){toast("Error","error");}
}
async function openManifest(){
  try{
    var r=await fetch("/api/manifest/"+encodeURIComponent(PROJECT));var d=await r.json();
    var html='<h3>📋 Manifest Editor</h3>';
    html+='<div style="font-size:12px;color:#94a3b8;margin-bottom:6px">Permissions:</div>';
    html+='<div style="margin-bottom:10px">'+(d.permissions||[]).map(function(p){return '<div style="font-family:monospace;font-size:11px;color:#93c5fd">• '+esc(p)+'</div>';}).join("")+'</div>';
    html+='<div style="font-size:12px;color:#94a3b8;margin-bottom:6px">Activities:</div>';
    html+='<div style="margin-bottom:10px">'+(d.activities||[]).map(function(p){return '<div style="font-family:monospace;font-size:11px;color:#fbbf24">• '+esc(p)+'</div>';}).join("")+'</div>';
    html+='<textarea id="manifestRaw" style="height:280px;font-family:monospace;font-size:11px">'+esc(d.raw||"")+'</textarea>';
    html+='<button class="btn btn-primary" style="width:100%;margin-top:8px;padding:12px" onclick="saveManifest()">💾 Save</button><button class="btn" style="width:100%;margin-top:6px;padding:12px" onclick="closeModal()">Cancel</button>';
    showModal(html);
  }catch(e){toast("Error","error");}
}
async function saveManifest(){
  var raw=document.getElementById("manifestRaw").value;
  try{
    var r=await fetch("/api/manifest/"+encodeURIComponent(PROJECT),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({raw:raw})});
    var d=await r.json();
    if(r.ok){toast("Saved");closeModal();}else toast(d.error||"Fail","error");
  }catch(e){toast("Error","error");}
}
function openIconGen(){
  showModal('<h3>🖼 Icon Generator</h3><p style="font-size:12px;color:#94a3b8">Upload a square PNG. Auto-generates all mipmap sizes.</p><input type="file" id="iconFile" accept="image/*" style="padding:8px;background:transparent;color:#fff"><button class="btn btn-primary" style="width:100%;margin-top:8px;padding:12px" onclick="doIconGen()">🚀 Generate</button><button class="btn" style="width:100%;margin-top:6px;padding:12px" onclick="closeModal()">Cancel</button>');
}
async function doIconGen(){
  var f=document.getElementById("iconFile").files[0];
  if(!f){toast("Select file","error");return;}
  var fd=new FormData();fd.append("file",f);
  toast("Uploading...");
  try{
    var r=await fetch("/api/icon-generate/"+encodeURIComponent(PROJECT),{method:"POST",body:fd});
    var d=await r.json();
    if(r.ok){toast("Icons generated!");closeModal();}
    else toast(d.error||"Fail","error");
  }catch(e){toast("Error","error");}
}
async function openEnvMgr(){
  try{
    var r=await fetch("/api/env/"+encodeURIComponent(PROJECT));var d=await r.json();
    window._envItems=d.items||[];
    renderEnvModal();
  }catch(e){toast("Error","error");}
}
function renderEnvModal(){
  var html='<h3>🔑 ENV Manager</h3><p style="font-size:11px;color:#94a3b8">Stored securely. Also written to .env</p>';
  window._envItems.forEach(function(it,i){
    html+='<div style="display:flex;gap:6px;margin:4px 0"><input value="'+esc(it.key)+'" placeholder="KEY" style="flex:1" onchange="envUpdate('+i+',this.value,\'key\')"><input value="'+esc(it.value)+'" placeholder="value" style="flex:2" onchange="envUpdate('+i+',this.value,\'value\')"><button class="btn btn-danger" style="padding:6px" onclick="envDel('+i+')">×</button></div>';
  });
  html+='<button class="btn btn-success" style="width:100%;margin-top:8px;padding:10px" onclick="envAdd()">+ Add</button><button class="btn btn-primary" style="width:100%;margin-top:6px;padding:12px" onclick="envSave()">💾 Save</button><button class="btn" style="width:100%;margin-top:6px;padding:12px" onclick="closeModal()">Close</button>';
  showModal(html);
}
function envUpdate(i,v,k){window._envItems[i][k]=v;}
function envDel(i){window._envItems.splice(i,1);renderEnvModal();}
function envAdd(){window._envItems.push({key:"NEW_KEY",value:""});renderEnvModal();}
async function envSave(){
  try{
    var r=await fetch("/api/env/"+encodeURIComponent(PROJECT),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({items:window._envItems})});
    var d=await r.json();
    if(r.ok){toast("Saved");closeModal();}else toast(d.error||"Fail","error");
  }catch(e){toast("Error","error");}
}
function openBulkRename(){
  showModal('<h3>✏️ Bulk Rename</h3><input id="bulkPattern" placeholder="Regex pattern e.g. old_(.*)"><input id="bulkReplace" placeholder="Replace e.g. new_\\1"><input id="bulkExt" placeholder="Extension filter (optional) e.g. .java"><button class="btn btn-primary" style="width:100%;margin-top:8px;padding:12px" onclick="doBulkRename()">🚀 Rename</button><button class="btn" style="width:100%;margin-top:6px;padding:12px" onclick="closeModal()">Cancel</button>');
}
async function doBulkRename(){
  var p=document.getElementById("bulkPattern").value;
  var r=document.getElementById("bulkReplace").value;
  var e=document.getElementById("bulkExt").value;
  if(!p){toast("Pattern required","error");return;}
  if(!confirm("This will rename matching files. Continue?"))return;
  try{
    var res=await fetch("/api/bulk-rename",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({project:PROJECT,pattern:p,replace:r,ext:e})});
    var d=await res.json();
    if(res.ok){toast("Renamed "+d.renamed+" files");closeModal();loadFiles(currentPath);}
    else toast(d.error||"Fail","error");
  }catch(err){toast("Error","error");}
}
function openFirebase(){
  showModal('<h3>🔥 Firebase Inject</h3><p style="font-size:12px;color:#94a3b8">Paste google-services.json content:</p><textarea id="fbJson" style="height:220px;font-family:monospace;font-size:11px" placeholder=\'{"project_info":{...}}\'></textarea><button class="btn btn-primary" style="width:100%;margin-top:8px;padding:12px" onclick="doFirebase()">🚀 Inject</button><button class="btn" style="width:100%;margin-top:6px;padding:12px" onclick="closeModal()">Cancel</button>');
}
async function doFirebase(){
  var j=document.getElementById("fbJson").value;
  try{
    var r=await fetch("/api/firebase-inject",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({project:PROJECT,json:j})});
    var d=await r.json();
    if(r.ok){toast("Firebase injected!");closeModal();}
    else toast(d.error||"Fail","error");
  }catch(e){toast("Error","error");}
}
async function bumpVersion(){
  if(!confirm("Bump versionCode +1?"))return;
  try{
    var r=await fetch("/api/version-bump/"+encodeURIComponent(PROJECT),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({versionCode:true,versionName:false})});
    var d=await r.json();
    if(r.ok)toast("Version bumped");else toast(d.error||"Fail","error");
  }catch(e){toast("Error","error");}
}
function openKeystore(){
  showModal('<h3>🔐 Keystore Config</h3><input id="ksFile" placeholder="Keystore file path (e.g. /sdcard/release.jks)"><input id="ksPass" placeholder="Store password" type="password"><input id="ksAlias" placeholder="Key alias"><input id="ksKeyPass" placeholder="Key password" type="password"><button class="btn btn-primary" style="width:100%;margin-top:8px;padding:12px" onclick="saveKs()">💾 Save</button><button class="btn" style="width:100%;margin-top:6px;padding:12px" onclick="closeModal()">Cancel</button>');
  fetch("/api/keystore").then(function(r){return r.json();}).then(function(d){
    if(d.storeFile)document.getElementById("ksFile").value=d.storeFile;
    if(d.keyAlias)document.getElementById("ksAlias").value=d.keyAlias;
  });
}
async function saveKs(){
  var data={
    storeFile:document.getElementById("ksFile").value,
    storePassword:document.getElementById("ksPass").value,
    keyAlias:document.getElementById("ksAlias").value||"release",
    keyPassword:document.getElementById("ksKeyPass").value
  };
  try{
    var r=await fetch("/api/keystore",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});
    if(r.ok){toast("Saved");closeModal();}
  }catch(e){toast("Error","error");}
}
async function signRelease(){
  if(!confirm("Build + sign release APK? (may take a while)"))return;
  toast("Building release...");
  try{
    var r=await fetch("/api/sign-release/"+encodeURIComponent(PROJECT),{method:"POST"});
    var d=await r.json();
    if(r.ok){toast("Signed!");location.href=d.download;}
    else toast(d.error||"Fail","error");
  }catch(e){toast("Error","error");}
}
function openRestore(){
  showModal('<h3>📥 Restore Backup</h3><p style="font-size:12px;color:#94a3b8">Select a ZIP backup file.</p><input type="file" id="restoreFile" accept=".zip" style="padding:8px;background:transparent;color:#fff"><button class="btn btn-primary" style="width:100%;margin-top:8px;padding:12px" onclick="doRestore()">🚀 Restore</button><button class="btn" style="width:100%;margin-top:6px;padding:12px" onclick="closeModal()">Cancel</button>');
}
async function doRestore(){
  var f=document.getElementById("restoreFile").files[0];
  if(!f)return;
  var fd=new FormData();fd.append("file",f);
  try{
    var r=await fetch("/api/restore",{method:"POST",body:fd});
    var d=await r.json();
    if(r.ok){toast("Restored!");closeModal();}
    else toast(d.error||"Fail","error");
  }catch(e){toast("Error","error");}
}
function showShortcuts(){
  showModal('<h3>⌨️ Keyboard Shortcuts</h3><div style="font-size:13px;line-height:1.9;color:#cbd5e1"><b>Ctrl+S</b> — Save<br><b>Ctrl+B</b> — Build APK<br><b>Ctrl+Shift+P</b> — Command Palette<br><b>Ctrl+F</b> — Find<br><b>Ctrl+/</b> — Toggle comment<br><b>Ctrl+Z</b> — Undo<br><b>Ctrl+Y</b> — Redo</div><button class="btn" style="width:100%;margin-top:10px;padding:12px" onclick="closeModal()">Close</button>');
}

// ============ COMMAND PALETTE ============
var PALETTE_CMDS=[
  {name:"🔨 Build APK",run:buildApk},
  {name:"▶ Run Current File",run:runCurrent},
  {name:"🔍 Scan All Errors",run:scanAllErrors},
  {name:"📦 Export ZIP",run:exportZip},
  {name:"📲 ADB Install",run:adbInstall},
  {name:"🧹 Clean Build",run:function(){cleanBuild(false);}},
  {name:"🧹 Deep Clean (all)",run:function(){cleanBuild(true);}},
  {name:"🔀 Git Status",run:function(){gitAction("status");switchPanel("git",document.querySelector('[data-panel="git"]'));}},
  {name:"💾 Git Commit",run:function(){switchPanel("git",document.querySelector('[data-panel="git"]'));gitCommitPrompt();}},
  {name:"📜 Logcat Start",run:function(){switchPanel("logcat",document.querySelector('[data-panel="logcat"]'));logcatStart();}},
  {name:"📦 Rename Package",run:openPkgRename},
  {name:"🔤 Strings Editor",run:openStrings},
  {name:"🎨 Theme Builder",run:openThemeBuilder},
  {name:"📋 Manifest Editor",run:openManifest},
  {name:"🖼 Icon Generator",run:openIconGen},
  {name:"🔑 ENV Manager",run:openEnvMgr},
  {name:"✏️ Bulk Rename",run:openBulkRename},
  {name:"🔥 Firebase Inject",run:openFirebase},
  {name:"🔢 Bump Version",run:bumpVersion},
  {name:"🔐 Keystore Config",run:openKeystore},
  {name:"✅ Sign Release",run:signRelease},
  {name:"🕒 Recent Files",run:showRecent},
  {name:"⌨️ Show Shortcuts",run:showShortcuts},
  {name:"📱 Preview: Phone",run:function(){switchPanel("preview",document.querySelector('[data-panel="preview"]'));}},
  {name:"📱 Preview: Toggle HTML/Android",run:togglePreviewMode},
  {name:"🖥 Toggle Split Preview",run:toggleSplitPreview},
  {name:"⚙️ Settings",run:openSettings},
  {name:"🌓 Toggle UI Language",run:function(){setLang((localStorage.getItem("uiLang")==="bn")?"en":"bn");}},
];
var paletteFiltered=PALETTE_CMDS.slice();
var paletteIdx=0;
function openCommandPalette(){
  document.getElementById("cmdPalette").classList.add("show");
  document.getElementById("cmdPaletteInput").value="";
  paletteFiltered=PALETTE_CMDS.slice();
  paletteIdx=0;
  renderPalette();
  setTimeout(function(){document.getElementById("cmdPaletteInput").focus();},50);
}
function renderPalette(){
  var ul=document.getElementById("cmdPaletteList");
  ul.innerHTML="";
  paletteFiltered.slice(0,12).forEach(function(c,i){
    var li=document.createElement("li");
    li.textContent=c.name;
    if(i===paletteIdx)li.classList.add("active");
    li.onclick=function(){closePalette();c.run();};
    ul.appendChild(li);
  });
}
function filterPalette(){
  var q=document.getElementById("cmdPaletteInput").value.toLowerCase();
  paletteFiltered=PALETTE_CMDS.filter(function(c){return c.name.toLowerCase().indexOf(q)!==-1;});
  paletteIdx=0;renderPalette();
}
function paletteKey(e){
  if(e.key==="Escape"){closePalette();}
  else if(e.key==="ArrowDown"){e.preventDefault();if(paletteIdx<paletteFiltered.length-1){paletteIdx++;renderPalette();}}
  else if(e.key==="ArrowUp"){e.preventDefault();if(paletteIdx>0){paletteIdx--;renderPalette();}}
  else if(e.key==="Enter"){e.preventDefault();var c=paletteFiltered[paletteIdx];if(c){closePalette();c.run();}}
}
function closePalette(){document.getElementById("cmdPalette").classList.remove("show");}

// ============ SETTINGS ============
function openSettings(){
  document.getElementById("fontSize").value=localStorage.getItem("fontSize")||13;
  document.getElementById("autoSave").value=localStorage.getItem("autoSave")||"off";
  document.getElementById("cmTheme").value=localStorage.getItem("cmTheme")||"dracula";
  document.getElementById("uiLang").value=localStorage.getItem("uiLang")||"en";
  document.getElementById("settingsModal").classList.add("show");
}
function applyFontSize(v){
  localStorage.setItem("fontSize",v);
  if(cm)cm.getWrapperElement().style.fontSize=v+"px";
}
function changeTheme(t){localStorage.setItem("cmTheme",t);if(cm)cm.setOption("theme",t);}
function setLang(l){
  localStorage.setItem("uiLang",l);
  var items=document.querySelectorAll(".nav-item");
  items.forEach(function(it){
    var p=it.dataset.panel;
    var label=it.querySelector("span:last-child");
    if(p&&label){
      var key={explorer:"files",preview:"preview",errors:"errors",terminal:"term",build:"build",git:"git",logcat:"log"}[p];
      if(key) label.textContent=(key==="errors"?"":"")+T(key);
    }
  });
  toast("Language: "+l);
}

// ============ KEYBOARD SHORTCUTS ============
document.addEventListener("keydown",function(e){
  if((e.ctrlKey||e.metaKey)&&e.shiftKey&&e.key.toLowerCase()==="p"){e.preventDefault();openCommandPalette();}
  else if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="s"){e.preventDefault();if(cm)saveFile(false);}
  else if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="b"){e.preventDefault();buildApk();}
  else if(e.key==="Escape"){closePalette();}
});
document.getElementById("cmdPaletteInput").addEventListener("blur",function(){setTimeout(closePalette,200);});

// ============ INIT ============
if(localStorage.getItem("uiLang")) setLang(localStorage.getItem("uiLang"));
loadFiles("");
setTimeout(function(){try{scanAllErrors();}catch(e){}},1500);
</script>
</body>
</html>
'''

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    print("")
    print("============================================")
    print("⚡ ZIHAD MOBILE IDE v10.0 — FULL EDITION")
    print("============================================")
    print("Projects  :", PROJECTS_DIR)
    print("APKs      :", APKS_DIR)
    print("History   :", HISTORY_DIR)
    print("Backups   :", BACKUP_DIR)
    print("Signed    :", SIGNED_DIR)
    print("Server    : http://127.0.0.1:%d" % PORT)
    print("============================================")
    print("Features: Templates(6), Git, Logcat, Icon,")
    print("Strings, Theme, Manifest, ENV, History,")
    print("BulkRename, Extract, Firebase, Signing,")
    print("Command Palette, i18n(bn/en), PWA, Split")
    print("============================================")
    print("")
    app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)
