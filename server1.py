# ============================================================
# ZIHAD MOBILE IDE v12.0 — ULTIMATE EDITION
# PART 1/3 : Imports + Config + Helpers + Templates + Home
# ============================================================
from flask import Flask, jsonify, request, send_file, Response
from pathlib import Path
import json, re, subprocess, shutil, os, threading, time, uuid, zipfile, io, sys, base64, hashlib
from datetime import datetime
from werkzeug.utils import secure_filename

try:
    import pty, signal, select, termios, struct, fcntl
    PTY_AVAILABLE = True
except ImportError:
    PTY_AVAILABLE = False

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024

# ---------------- CONFIG ----------------
BASE_DIR       = Path.home() / "Projects" / "ZihadIDE"
PROJECTS_DIR   = BASE_DIR / "projects"
APKS_DIR       = BASE_DIR / "apks"
HISTORY_DIR    = BASE_DIR / "history"
BACKUP_DIR     = BASE_DIR / "backups"
SIGNED_DIR     = BASE_DIR / "signed"
PLUGINS_DIR    = BASE_DIR / "plugins"
KANBAN_DIR     = BASE_DIR / "kanban"
NOTES_DIR      = BASE_DIR / "notes"

for d in [PROJECTS_DIR, APKS_DIR, HISTORY_DIR, BACKUP_DIR,
          SIGNED_DIR, PLUGINS_DIR, KANBAN_DIR, NOTES_DIR]:
    d.mkdir(parents=True, exist_ok=True)

SAVED_COMMANDS_FILE = BASE_DIR / "saved_commands.json"
RECENT_FILES_FILE   = BASE_DIR / "recent_files.json"
KEYSTORE_FILE       = BASE_DIR / "keystore.json"
ENV_FILE            = BASE_DIR / "env_vault.json"
NOTIF_FILE          = BASE_DIR / "notifications.json"
THEMES_FILE         = BASE_DIR / "custom_themes.json"
ALIAS_FILE          = BASE_DIR / "aliases.json"
MACROS_FILE         = BASE_DIR / "macros.json"
BUILD_HISTORY       = BASE_DIR / "build_history.json"
ERROR_FREQ_FILE     = BASE_DIR / "error_freq.json"
BOOKMARKS_FILE      = BASE_DIR / "bookmarks.json"
SETTINGS_FILE       = BASE_DIR / "settings.json"
APK_HISTORY_FILE    = BASE_DIR / "apk_history.json"
SNIPPETS_FILE       = BASE_DIR / "snippets.json"

PORT = 3095
TERMUX_PREFIX = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
BUILDS = {}
LOGCAT_PROCS = {}
PTY_SESSIONS = {}
AUTO_BUILD_LOCK = {}
AUTO_BUILD_DEBOUNCE = 4

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
    "Duplicate resources": "Multiple res files with same name",
    "library": "Missing library dependency",
    "Could not connect": "Check internet / proxy",
    "Timeout": "Retry with better internet",
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
    key = f"{project_name}__{str(file_path).replace('/', '_').replace(chr(92), '_')}"
    hist_dir = HISTORY_DIR / key
    hist_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    try: (hist_dir / f"{ts}.bak").write_text(content, encoding="utf-8")
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

def expand_alias(cmd):
    aliases = load_json(ALIAS_FILE, {"items": {}}).get("items", {})
    parts = cmd.split(None, 1)
    if parts and parts[0] in aliases:
        rest = parts[1] if len(parts) > 1 else ""
        return aliases[parts[0]] + (" " + rest if rest else "")
    return cmd

def _push_notif(project, title, body, kind="info"):
    notifs = load_json(NOTIF_FILE, {"items": []}).get("items", [])
    notifs.insert(0, {
        "id": str(uuid.uuid4())[:8],
        "project": project, "title": title, "body": body,
        "kind": kind, "ts": time.time(), "read": False
    })
    notifs = notifs[:200]
    save_json(NOTIF_FILE, {"items": notifs})

# ============================================================
# PROJECT CREATION WITH ALL TEMPLATES
# ============================================================
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
# HOME PAGE
# ============================================================
HOME_HTML = r'''<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>Zihad Mobile IDE v12</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
<style>
:root{--bg:#070b14;--card:rgba(17,24,39,.85);--border:rgba(55,65,81,.6);--primary:#3b82f6;--text:#f1f5f9;--muted:#94a3b8;--radius:18px}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;min-height:100vh;background-image:radial-gradient(ellipse at 20% 20%,rgba(59,130,246,.12) 0%,transparent 50%),radial-gradient(ellipse at 80% 80%,rgba(139,92,246,.1) 0%,transparent 50%)}
header{padding:16px 20px;background:rgba(15,23,42,.9);backdrop-filter:blur(20px);border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:50;gap:8px;flex-wrap:wrap}
header h1{font-size:1.15rem;font-weight:700;background:linear-gradient(135deg,#60a5fa,#a78bfa);-webkit-background-clip:text;-webkit-text-fill-color:transparent;display:flex;align-items:center;gap:8px}
header h1 i{color:#60a5fa;-webkit-text-fill-color:initial}
.container{padding:20px;max-width:720px;margin:0 auto}
.card{background:var(--card);backdrop-filter:blur(16px);border:1px solid var(--border);border-radius:var(--radius);padding:20px;margin-bottom:18px;box-shadow:0 8px 32px rgba(0,0,0,.3)}
h2{font-size:1.05rem;margin-bottom:12px;color:#e2e8f0;display:flex;align-items:center;gap:8px}
h2 i{color:#60a5fa}
.status-dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#22c55e;margin-right:8px;box-shadow:0 0 10px #22c55e}
button{border:0;border-radius:12px;padding:11px 16px;margin:4px;font-weight:600;font-size:13px;cursor:pointer;color:#fff;display:inline-flex;align-items:center;gap:6px}
button:active{transform:scale(.96)}
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
.toast{background:rgba(15,23,42,.95);border:1px solid var(--border);color:#fff;padding:12px 20px;border-radius:14px;font-size:13px;display:flex;align-items:center;gap:8px}
.toast.success{border-color:rgba(34,197,94,.5)}.toast.error{border-color:rgba(239,68,68,.5)}
.fab{position:fixed;bottom:28px;right:24px;width:58px;height:58px;border-radius:50%;background:linear-gradient(135deg,#3b82f6,#8b5cf6);display:flex;align-items:center;justify-content:center;font-size:24px;color:#fff;border:0;z-index:40;box-shadow:0 8px 30px rgba(139,92,246,.6)}
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
  <h1><i class="fa-solid fa-bolt"></i> Zihad IDE v12</h1>
  <div style="display:flex;gap:2px;flex-wrap:wrap">
    <button class="btn-ghost" onclick="toggleTheme()" id="themeBtn"><i class="fa-solid fa-moon"></i></button>
    <button class="btn-ghost" onclick="location.href='/api/backup'"><i class="fa-solid fa-floppy-disk"></i></button>
    <button class="btn-ghost" style="position:relative;overflow:hidden"><i class="fa-solid fa-download"></i><input type="file" style="position:absolute;inset:0;opacity:0;cursor:pointer;width:100%" onchange="restoreBackup(this)"></button>
    <button class="btn-ghost" onclick="showApks()"><i class="fa-solid fa-box-archive"></i></button>
    <button class="btn-success" onclick="showCreate()"><i class="fa-solid fa-plus"></i> New</button>
  </div>
</header>
<div class="container">
  <div class="card">
    <h2><span class="status-dot"></span>System Status</h2>
    <p id="status" style="color:var(--muted);font-size:13px">Checking...</p>
  </div>
  <div class="card hidden" id="createBox">
    <h2><i class="fa-solid fa-mobile-screen"></i> New Android Project</h2>
    <input id="appName" placeholder="App Name">
    <input id="packageName" placeholder="com.zihad.myapp">
    <select id="language"><option value="java">Java</option><option value="kotlin">Kotlin</option></select>
    <p style="font-size:13px;color:var(--muted);margin:10px 0 6px">Template</p>
    <div class="template-grid">
      <div class="template-card active" data-t="empty" onclick="selectTemplate(this)"><span>📄</span>Empty</div>
      <div class="template-card" data-t="login" onclick="selectTemplate(this)"><span>🔐</span>Login</div>
      <div class="template-card" data-t="list" onclick="selectTemplate(this)"><span>📋</span>List</div>
      <div class="template-card" data-t="splash" onclick="selectTemplate(this)"><span>✨</span>Splash</div>
      <div class="template-card" data-t="bottom_nav" onclick="selectTemplate(this)"><span>🧭</span>Bottom Nav</div>
      <div class="template-card" data-t="empty" onclick="selectTemplate(this)"><span>⚡</span>Basic</div>
    </div>
    <div style="display:flex;gap:8px;margin-top:14px">
      <button class="btn-success" style="flex:1" onclick="createProject()"><i class="fa-solid fa-rocket"></i> Create</button>
      <button class="btn-ghost" onclick="hideCreate()">Cancel</button>
    </div>
    <div id="message" style="display:none;padding:12px;border-radius:12px;margin-top:12px"></div>
  </div>
  <div class="card hidden" id="apksBox">
    <h2><i class="fa-solid fa-box-archive"></i> Built APKs</h2>
    <div id="apksList">Loading...</div>
    <button class="btn-ghost" style="width:100%;margin-top:10px" onclick="hideApks()">Close</button>
  </div>
  <div class="card">
    <h2><i class="fa-solid fa-folder-tree"></i> Projects</h2>
    <div id="projects">Loading...</div>
  </div>
</div>
<button class="fab" onclick="showCreate()"><i class="fa-solid fa-plus"></i></button>
<div class="toast-container" id="toasts"></div>
<script>
var selectedTemplate="empty";
if(localStorage.getItem("theme")==="light")document.body.classList.add("light");
document.getElementById("themeBtn").innerHTML=document.body.classList.contains("light")?'<i class="fa-solid fa-sun"></i>':'<i class="fa-solid fa-moon"></i>';
function toggleTheme(){document.body.classList.toggle("light");localStorage.setItem("theme",document.body.classList.contains("light")?"light":"dark");document.getElementById("themeBtn").innerHTML=document.body.classList.contains("light")?'<i class="fa-solid fa-sun"></i>':'<i class="fa-solid fa-moon"></i>';}
function selectTemplate(el){document.querySelectorAll(".template-card").forEach(function(c){c.classList.remove("active")});el.classList.add("active");selectedTemplate=el.dataset.t}
function showCreate(){document.getElementById("createBox").classList.remove("hidden");document.getElementById("apksBox").classList.add("hidden")}
function hideCreate(){document.getElementById("createBox").classList.add("hidden")}
function showApks(){document.getElementById("apksBox").classList.remove("hidden");document.getElementById("createBox").classList.add("hidden");loadApks()}
function hideApks(){document.getElementById("apksBox").classList.add("hidden")}
function toast(msg,type){type=type||"success";var c=document.getElementById("toasts");var t=document.createElement("div");t.className="toast "+type;t.innerHTML=(type==="error"?'<i class="fa-solid fa-circle-xmark"></i>':'<i class="fa-solid fa-circle-check"></i>')+msg;c.appendChild(t);setTimeout(function(){t.remove()},3000)}
function esc(t){var d=document.createElement("div");d.innerText=t;return d.innerHTML}
async function status(){try{var r=await fetch("/api/status");var d=await r.json();document.getElementById("status").innerText="Port "+d.port+"  •  "+d.projects+" projects  •  "+d.language_count+" languages  •  v"+d.version}catch(e){document.getElementById("status").innerText="Offline"}}
async function loadProjects(){try{var r=await fetch("/api/projects");var d=await r.json();var box=document.getElementById("projects");if(!d.projects.length){box.innerHTML='<p style="color:#94a3b8;text-align:center;padding:20px">No projects yet</p>';return}box.innerHTML="";d.projects.forEach(function(p){var div=document.createElement("div");div.className="project";div.innerHTML='<div class="project-info"><b><i class="fa-solid fa-mobile-screen-button"></i> '+esc(p.name)+'</b><span class="badge">'+esc(p.language||"?")+'</span><br><small style="color:#94a3b8">'+esc(p.package||"")+'</small></div><div><button class="btn-primary" onclick="location.href=\'/project/'+encodeURIComponent(p.name)+'\'"><i class="fa-solid fa-folder-open"></i> Open</button><button class="btn-danger" onclick="deleteProject(\''+esc(p.name)+'\')"><i class="fa-solid fa-trash"></i></button></div>';box.appendChild(div)})}catch(e){document.getElementById("projects").innerText="Error"}}
async function createProject(){var n=document.getElementById("appName").value.trim();var p=document.getElementById("packageName").value.trim();var l=document.getElementById("language").value;if(!n||!p){msg("Name & Package required",1);return}try{var r=await fetch("/api/projects",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:n,package:p,language:l,template:selectedTemplate})});var d=await r.json();if(!r.ok){msg(d.error||"Failed",1);return}msg("Created!",0);toast("Project created");document.getElementById("appName").value="";document.getElementById("packageName").value="";hideCreate();loadProjects();status()}catch(e){msg("Error",1)}}
async function deleteProject(name){if(!confirm("Delete "+name+"?"))return;try{var r=await fetch("/api/projects/"+encodeURIComponent(name),{method:"DELETE"});if(r.ok){toast("Deleted");loadProjects();status()}else toast("Failed","error")}catch(e){toast("Error","error")}}
async function loadApks(){try{var r=await fetch("/api/apks");var d=await r.json();var box=document.getElementById("apksList");if(!d.apks||!d.apks.length){box.innerHTML='<p style="color:#94a3b8;text-align:center">No APKs</p>';return}box.innerHTML="";d.apks.forEach(function(a){var div=document.createElement("div");div.className="apk-item";div.innerHTML='<div><b><i class="fa-solid fa-box-archive"></i> '+esc(a.name)+'</b><br><small style="color:#94a3b8">'+esc(a.size)+' • '+esc(a.mtime)+'</small></div><div><button class="btn-success" onclick="location.href=\'/api/download-saved-apk/'+encodeURIComponent(a.name)+'\'"><i class="fa-solid fa-download"></i></button><button class="btn-danger" onclick="deleteApk(\''+esc(a.name)+'\')"><i class="fa-solid fa-trash"></i></button></div>';box.appendChild(div)})}catch(e){document.getElementById("apksList").innerText="Error"}}
async function deleteApk(name){if(!confirm("Delete?"))return;try{var r=await fetch("/api/apks/"+encodeURIComponent(name),{method:"DELETE"});if(r.ok){toast("Deleted");loadApks()}else toast("Failed","error")}catch(e){toast("Error","error")}}
function msg(t,e){var m=document.getElementById("message");m.style.display="block";m.innerText=t;m.style.background=e?"rgba(127,29,29,.55)":"rgba(20,83,45,.55)"}
async function restoreBackup(input){if(!input.files[0])return;if(!confirm("Restore backup? Existing projects may be overwritten."))return;var fd=new FormData();fd.append("file",input.files[0]);try{var r=await fetch("/api/restore",{method:"POST",body:fd});var d=await r.json();if(r.ok){toast("Restored!");loadProjects();status()}else toast(d.error||"Failed","error")}catch(e){toast("Error","error")}input.value=""}
status();loadProjects();
</script>
</body></html>
'''

# ============================================================
# END OF PART 1 — Paste PART 2 BELOW THIS LINE
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
                    "language_count": len(langs), "version": "12.0"})

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

@app.route("/api/folder-size/<path:name>")
def folder_size(name):
    project = safe_project(name)
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    sub = request.args.get("path", "")
    target = safe_subpath(project, sub)
    if target is None or not target.exists():
        return jsonify({"error": "Invalid"}), 400
    try:
        total = 0; count = 0
        if target.is_file():
            total = target.stat().st_size; count = 1
        else:
            for p in target.rglob("*"):
                if p.is_file():
                    try: total += p.stat().st_size; count += 1
                    except: continue
        return jsonify({"bytes": total, "human": human_size(total), "files": count})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/all-folder-sizes/<path:name>")
def all_folder_sizes(name):
    project = safe_project(name)
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    sub = request.args.get("path", "")
    target = safe_subpath(project, sub)
    if target is None or not target.is_dir():
        return jsonify({"error": "Invalid"}), 400
    result = {}
    for p in target.iterdir():
        try:
            if p.is_file():
                result[p.name] = human_size(p.stat().st_size)
            else:
                total = 0
                for f in p.rglob("*"):
                    if f.is_file():
                        try: total += f.stat().st_size
                        except: continue
                result[p.name] = human_size(total)
        except: continue
    return jsonify({"sizes": result})

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
        # Trigger auto-build if enabled (in background)
        try:
            proj_settings = load_json(SETTINGS_FILE, {}).get(name, {})
            if proj_settings.get("autoBuild"):
                threading.Thread(target=trigger_auto_build, args=(name,), daemon=True).start()
        except: pass
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

@app.route("/api/firebase-inject", methods=["POST"])
def firebase_inject():
    data = request.get_json(silent=True) or {}
    project = safe_project(data.get("project", ""))
    if project is None or not project.exists():
        return jsonify({"error": "Invalid"}), 400
    json_str = data.get("json", "").strip()
    if not json_str:
        return jsonify({"error": "google-services.json content required"}), 400
    try: parsed = json.loads(json_str)
    except: return jsonify({"error": "Invalid JSON"}), 400
    write_file(project / "app" / "google-services.json", json.dumps(parsed, indent=2))
    app_gradle = project / "app" / "build.gradle"
    if app_gradle.exists():
        txt = app_gradle.read_text(encoding="utf-8")
        if "com.google.gms.google-services" not in txt:
            txt = txt.replace('plugins {\n    id "com.android.application"\n}',
                              'plugins {\n    id "com.android.application"\n    id "com.google.gms.google-services"\n}')
            app_gradle.write_text(txt, encoding="utf-8")
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
    cmd = expand_alias(cmd)
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

# ---------------- PRESET COMMANDS ----------------
PRESET_COMMANDS = [
    {"name": "Update System", "cmd": "pkg update -y && pkg upgrade -y", "icon": "fa-sync"},
    {"name": "Install Git", "cmd": "pkg install -y git", "icon": "fa-code-branch"},
    {"name": "Install Python", "cmd": "pkg install -y python", "icon": "fa-python"},
    {"name": "Install Node.js", "cmd": "pkg install -y nodejs", "icon": "fa-node-js"},
    {"name": "Install Nano", "cmd": "pkg install -y nano", "icon": "fa-pen"},
    {"name": "Install Vim", "cmd": "pkg install -y vim", "icon": "fa-terminal"},
    {"name": "Install OpenSSH", "cmd": "pkg install -y openssh", "icon": "fa-key"},
    {"name": "Install Clang", "cmd": "pkg install -y clang", "icon": "fa-code"},
    {"name": "Install Java (17)", "cmd": "pkg install -y openjdk-17", "icon": "fa-java"},
    {"name": "Install Gradle", "cmd": "pkg install -y gradle", "icon": "fa-cubes"},
    {"name": "Install AAPT2", "cmd": "pkg install -y aapt2", "icon": "fa-android"},
    {"name": "Install Android tools", "cmd": "pkg install -y android-tools", "icon": "fa-mobile-alt"},
    {"name": "Install ImageMagick", "cmd": "pkg install -y imagemagick", "icon": "fa-image"},
    {"name": "Install sqlite", "cmd": "pkg install -y sqlite", "icon": "fa-database"},
    {"name": "Install curl", "cmd": "pkg install -y curl", "icon": "fa-download"},
    {"name": "Install wget", "cmd": "pkg install -y wget", "icon": "fa-cloud-download-alt"},
    {"name": "Upgrade pip", "cmd": "pip install --upgrade pip", "icon": "fa-arrow-up"},
    {"name": "List packages", "cmd": "pkg list-installed", "icon": "fa-list"},
    {"name": "Disk usage", "cmd": "df -h", "icon": "fa-hdd"},
    {"name": "Show PATH", "cmd": "echo $PATH", "icon": "fa-road"},
    {"name": "Network test", "cmd": "ping -c 3 google.com", "icon": "fa-wifi"},
    {"name": "Local IP", "cmd": "ifconfig 2>/dev/null || ip addr", "icon": "fa-network-wired"},
    {"name": "Gradle version", "cmd": "gradle -v", "icon": "fa-cog"},
    {"name": "Java version", "cmd": "java -version", "icon": "fa-java"},
    {"name": "Node version", "cmd": "node -v", "icon": "fa-node-js"},
    {"name": "Python version", "cmd": "python --version", "icon": "fa-python"},
    {"name": "Git status", "cmd": "git status", "icon": "fa-code-branch"},
    {"name": "Clear cache", "cmd": "rm -rf ~/.cache/*", "icon": "fa-broom"},
    {"name": "Kill all python", "cmd": "pkill -f python", "icon": "fa-skull"},
    {"name": "Show top", "cmd": "top -b -n 1 | head -20", "icon": "fa-chart-line"},
]

@app.route("/api/preset-commands")
def preset_commands():
    return jsonify({"commands": PRESET_COMMANDS})

# ---------------- SYSTEM INFO ----------------
@app.route("/api/system-info")
def system_info():
    info = {}
    try:
        with open("/proc/meminfo") as f:
            m = f.read()
            for line in m.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    info[k.strip()] = v.strip()
    except: pass
    try:
        du = shutil.disk_usage(str(BASE_DIR))
        info["disk_total"] = human_size(du.total)
        info["disk_used"] = human_size(du.used)
        info["disk_free"] = human_size(du.free)
        info["disk_percent"] = round(du.used / du.total * 100, 1)
    except: pass
    try:
        with open("/proc/uptime") as f:
            up = float(f.read().split()[0])
            info["uptime"] = f"{int(up//3600)}h {int((up%3600)//60)}m"
    except: pass
    import platform
    info["python"] = platform.python_version()
    info["machine"] = platform.machine()
    return jsonify(info)

@app.route("/api/proc-list")
def proc_list():
    procs = []
    try:
        r = subprocess.run(["ps", "-eo", "pid,user,comm,%cpu,%mem"],
                           capture_output=True, text=True, timeout=10)
        lines = r.stdout.splitlines()
        if lines:
            for l in lines[1:60]:
                procs.append(l)
    except: pass
    return jsonify({"procs": procs})

@app.route("/api/proc-kill", methods=["POST"])
def proc_kill():
    data = request.get_json(silent=True) or {}
    pid = str(data.get("pid", "")).strip()
    if not pid.isdigit(): return jsonify({"error": "Invalid PID"}), 400
    try:
        os.kill(int(pid), signal.SIGTERM)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------- REAL PTY ----------------
@app.route("/api/pty/start", methods=["POST"])
def pty_start():
    if not PTY_AVAILABLE:
        return jsonify({"error": "PTY not available"}), 500
    try:
        sid = str(uuid.uuid4())
        pid, fd = pty.fork()
        if pid == 0:
            os.environ["TERM"] = "xterm-256color"
            os.environ["PS1"] = "\\[\\e[1;34m\\]zihad\\[\\e[0m\\]:\\[\\e[1;32m\\]\\w\\[\\e[0m\\]$ "
            shell = "bash" if shutil.which("bash") else "sh"
            os.execvp(shell, [shell])
        else:
            PTY_SESSIONS[sid] = {"pid": pid, "fd": fd, "output": [], "started": time.time()}
            def reader():
                try:
                    while sid in PTY_SESSIONS:
                        try:
                            r, _, _ = select.select([fd], [], [], 0.5)
                            if r:
                                data = os.read(fd, 4096)
                                if not data: break
                                text = data.decode("utf-8", errors="replace")
                                PTY_SESSIONS[sid]["output"].append(text)
                                if len(PTY_SESSIONS[sid]["output"]) > 3000:
                                    PTY_SESSIONS[sid]["output"] = PTY_SESSIONS[sid]["output"][-2000:]
                        except OSError: break
                except: pass
            threading.Thread(target=reader, daemon=True).start()
            return jsonify({"success": True, "session": sid})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/pty/input/<sid>", methods=["POST"])
def pty_input(sid):
    S = PTY_SESSIONS.get(sid)
    if not S: return jsonify({"error": "Not found"}), 404
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    try:
        os.write(S["fd"], text.encode("utf-8"))
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/pty/output/<sid>")
def pty_output(sid):
    S = PTY_SESSIONS.get(sid)
    if not S: return jsonify({"error": "Not found"}), 404
    since = int(request.args.get("since", 0))
    lines = S["output"][since:]
    return jsonify({"output": "".join(lines), "total": len(S["output"])})

@app.route("/api/pty/stop/<sid>", methods=["POST"])
def pty_stop(sid):
    S = PTY_SESSIONS.pop(sid, None)
    if S:
        try: os.kill(S["pid"], signal.SIGTERM)
        except: pass
        try: os.close(S["fd"])
        except: pass
    return jsonify({"success": True})

# ---------------- BUILD ----------------
def build_worker(build_id, project, env):
    B = BUILDS[build_id]
    cmd = "gradle assembleDebug --no-daemon --console=plain --parallel"
    try:
        B["started"] = B.get("started", time.time())
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
        B["finished"] = time.time()
        B["duration"] = B["finished"] - B["started"]
        if B["success"] and B["apk_path"]:
            try:
                src = Path(B["apk_path"])
                dst = APKS_DIR / (project.name + "-" + src.name)
                shutil.copy2(src, dst)
                B["apk_saved"] = str(dst)
                B["apk_size"] = dst.stat().st_size
                _push_notif(project.name, "✅ Build successful",
                            f"APK ready ({human_size(B['apk_size'])})", "success")
                _record_build(project.name, True, B["duration"], B["apk_size"], 0)
            except: pass
        else:
            err_count = sum(1 for l in B["output"] if "error:" in l.lower())
            _push_notif(project.name, "❌ Build failed",
                        f"Check log ({err_count} errors)", "error")
            _record_build(project.name, False, B["duration"], 0, err_count)
            _record_error_patterns(project.name, B["output"])
    except Exception as e:
        B["output"].append("[build error] " + str(e))
        B["status"] = "done"
        B["success"] = False
        B["returncode"] = -1
        _push_notif(project.name, "❌ Build crashed", str(e), "error")

def _record_build(project, success, duration, apk_size, error_count):
    hist = load_json(BUILD_HISTORY, {})
    proj = hist.get(project, [])
    proj.insert(0, {
        "ts": time.time(), "success": success,
        "duration": round(duration, 2),
        "apk_size": apk_size, "errors": error_count
    })
    hist[project] = proj[:100]
    save_json(BUILD_HISTORY, hist)

def _record_error_patterns(project, lines):
    freq = load_json(ERROR_FREQ_FILE, {})
    proj = freq.get(project, {})
    for line in lines:
        m = re.search(r'(error|warning)[:\s]+(.+?)(?:$|")', line, re.IGNORECASE)
        if m:
            key = m.group(2).strip()[:80]
            if not key: continue
            proj[key] = proj.get(key, 0) + 1
    freq[project] = dict(sorted(proj.items(), key=lambda x: -x[1])[:50])
    save_json(ERROR_FREQ_FILE, freq)

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
                        "returncode": None, "success": None, "started": time.time()}
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
        "apk_path": B.get("apk_path"), "returncode": B.get("returncode"),
        "duration": B.get("duration"), "apk_size": B.get("apk_size")
    })

@app.route("/api/build-history/<path:name>")
def build_history(name):
    hist = load_json(BUILD_HISTORY, {})
    return jsonify({"history": hist.get(name, [])})

@app.route("/api/apk-size-graph/<path:name>")
def apk_size_graph(name):
    hist = load_json(BUILD_HISTORY, {}).get(name, [])
    points = [{"ts": h["ts"], "size": h["apk_size"]} for h in hist if h.get("apk_size")]
    return jsonify({"points": points})

@app.route("/api/error-frequency/<path:name>")
def error_frequency(name):
    freq = load_json(ERROR_FREQ_FILE, {})
    return jsonify({"freq": freq.get(name, {})})

@app.route("/api/build-chart/<path:name>")
def build_chart(name):
    hist = load_json(BUILD_HISTORY, {}).get(name, [])[:20]
    return jsonify({"chart": [
        {"ts": h["ts"], "duration": h["duration"], "success": h["success"]}
        for h in hist
    ]})

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
    if data.get("deep"):
        gcache = Path.home() / ".gradle" / "caches" / "transforms-3"
        if gcache.exists():
            try:
                shutil.rmtree(gcache)
                cleared.append("~/.gradle/transforms-3")
            except: pass
    return jsonify({"success": True, "cleared": cleared})

# ---------------- AUTO BUILD ----------------
def trigger_auto_build(project_name):
    proj_settings = load_json(SETTINGS_FILE, {}).get(project_name, {})
    if not proj_settings.get("autoBuild"): return
    last = AUTO_BUILD_LOCK.get(project_name, 0)
    if time.time() - last < AUTO_BUILD_DEBOUNCE: return
    AUTO_BUILD_LOCK[project_name] = time.time()
    project = safe_project(project_name)
    if not project: return
    env = os.environ.copy()
    sdk = Path.home() / "android-sdk"
    if sdk.exists():
        env["ANDROID_HOME"] = str(sdk)
        env["ANDROID_SDK_ROOT"] = str(sdk)
    env["PATH"] = str(sdk / "platform-tools") + ":" + TERMUX_PREFIX + "/bin:" + env.get("PATH", "")
    build_id = "auto-" + str(uuid.uuid4())[:8]
    BUILDS[build_id] = {
        "output": [], "status": "running", "apk_path": None,
        "returncode": None, "success": None, "auto": True,
        "project": project_name, "started": time.time()
    }
    _push_notif(project_name, "🔨 Auto-build started",
                "Watching for changes...", "info")
    threading.Thread(target=build_worker, args=(build_id, project, env), daemon=True).start()
    return build_id

# ---------------- SETTINGS ----------------
@app.route("/api/settings/<path:name>", methods=["GET", "POST"])
def settings_mgr(name):
    all_s = load_json(SETTINGS_FILE, {})
    if request.method == "GET":
        return jsonify(all_s.get(name, {
            "autoBuild": False, "notifications": True,
            "theme": "dracula", "gestures": True,
            "tabSize": 4, "fontSize": 13
        }))
    data = request.get_json(silent=True) or {}
    cur = all_s.get(name, {})
    cur.update(data)
    all_s[name] = cur
    save_json(SETTINGS_FILE, all_s)
    return jsonify({"success": True, "settings": cur})

# ---------------- NOTIFICATIONS ----------------
@app.route("/api/notifications")
def notif_list():
    since = float(request.args.get("since", 0))
    items = load_json(NOTIF_FILE, {"items": []}).get("items", [])
    unread = sum(1 for n in items if not n.get("read"))
    new_items = [n for n in items if n["ts"] > since]
    return jsonify({"items": items[:50], "new": new_items, "unread": unread})

@app.route("/api/notifications/read", methods=["POST"])
def notif_read():
    data = request.get_json(silent=True) or {}
    nid = data.get("id")
    notifs = load_json(NOTIF_FILE, {"items": []}).get("items", [])
    if nid:
        for n in notifs:
            if n["id"] == nid: n["read"] = True
    else:
        for n in notifs: n["read"] = True
    save_json(NOTIF_FILE, {"items": notifs})
    return jsonify({"success": True})

@app.route("/api/notifications/clear", methods=["POST"])
def notif_clear():
    save_json(NOTIF_FILE, {"items": []})
    return jsonify({"success": True})

@app.route("/api/notify", methods=["POST"])
def notif_push():
    data = request.get_json(silent=True) or {}
    _push_notif(data.get("project", ""), data.get("title", "Notice"),
                data.get("body", ""), data.get("kind", "info"))
    return jsonify({"success": True})

# ---------------- GIT ----------------
def git_run(project, args, timeout=60):
    try:
        r = subprocess.run(["git"] + args, cwd=str(project),
                           capture_output=True, text=True, timeout=timeout)
        return {"ok": r.returncode == 0, "out": r.stdout,
                "err": r.stderr, "code": r.returncode}
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

# ---------------- STRINGS / THEME / MANIFEST ----------------
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
            items = [{"name": s.get("name", ""), "value": s.text or ""}
                     for s in tree.getroot().findall("string")]
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
        try: parts[-1] = str(int(parts[-1]) + 1)
        except: parts.append("1")
        new_name = ".".join(parts)
        txt = txt.replace(m_name.group(0), f'versionName "{new_name}"')
    gradle_file.write_text(txt, encoding="utf-8")
    return jsonify({"success": True})

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

# ---------------- KEYSTORE ----------------
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
        gradle_file.write_text(txt, encoding="utf-8")
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

# ---------------- PLUGINS ----------------
@app.route("/api/plugins")
def list_plugins():
    plugins = []
    for p in PLUGINS_DIR.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            data["_file"] = p.name
            plugins.append(data)
        except: continue
    return jsonify({"plugins": plugins})

@app.route("/api/plugins", methods=["POST"])
def add_plugin():
    data = request.get_json(silent=True) or {}
    name = secure_filename(data.get("name", "plugin")) + ".json"
    plugin = {
        "name": data.get("name", "plugin"),
        "version": data.get("version", "1.0"),
        "author": data.get("author", "unknown"),
        "description": data.get("description", ""),
        "code": data.get("code", ""),
        "css": data.get("css", ""),
        "enabled": True, "created": time.time()
    }
    (PLUGINS_DIR / name).write_text(json.dumps(plugin, indent=2), encoding="utf-8")
    return jsonify({"success": True})

@app.route("/api/plugins/<path:name>", methods=["DELETE", "PATCH"])
def plugin_mgr(name):
    p = PLUGINS_DIR / secure_filename(name)
    if not p.exists(): return jsonify({"error": "Not found"}), 404
    if request.method == "DELETE":
        p.unlink()
        return jsonify({"success": True})
    data = request.get_json(silent=True) or {}
    try:
        plugin = json.loads(p.read_text(encoding="utf-8"))
        plugin.update(data)
        p.write_text(json.dumps(plugin, indent=2), encoding="utf-8")
        return jsonify({"success": True, "plugin": plugin})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------- CUSTOM THEMES ----------------
@app.route("/api/themes", methods=["GET", "POST"])
def custom_themes():
    themes = load_json(THEMES_FILE, {"items": []}).get("items", [])
    if request.method == "GET":
        return jsonify({"themes": themes})
    data = request.get_json(silent=True) or {}
    theme = {
        "id": str(uuid.uuid4())[:8],
        "name": data.get("name", "My Theme"),
        "colors": data.get("colors", {}),
        "created": time.time()
    }
    themes.append(theme)
    save_json(THEMES_FILE, {"items": themes})
    return jsonify({"success": True, "theme": theme})

@app.route("/api/themes/<tid>", methods=["DELETE"])
def delete_theme(tid):
    themes = load_json(THEMES_FILE, {"items": []}).get("items", [])
    themes = [t for t in themes if t["id"] != tid]
    save_json(THEMES_FILE, {"items": themes})
    return jsonify({"success": True})

# ---------------- ALIASES ----------------
@app.route("/api/aliases", methods=["GET", "POST", "DELETE"])
def aliases_mgr():
    aliases = load_json(ALIAS_FILE, {"items": {}}).get("items", {})
    if request.method == "GET":
        return jsonify({"aliases": aliases})
    data = request.get_json(silent=True) or {}
    if request.method == "POST":
        key = data.get("key", "").strip()
        cmd = data.get("cmd", "").strip()
        if not key or not cmd: return jsonify({"error": "Both required"}), 400
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_-]{0,30}$", key):
            return jsonify({"error": "Invalid alias name"}), 400
        aliases[key] = cmd
        save_json(ALIAS_FILE, {"items": aliases})
        return jsonify({"success": True, "aliases": aliases})
    key = data.get("key", "")
    aliases.pop(key, None)
    save_json(ALIAS_FILE, {"items": aliases})
    return jsonify({"success": True, "aliases": aliases})

# ---------------- MACROS ----------------
@app.route("/api/macros", methods=["GET", "POST", "DELETE"])
def macros_mgr():
    macros = load_json(MACROS_FILE, {"items": []}).get("items", [])
    if request.method == "GET":
        return jsonify({"macros": macros})
    data = request.get_json(silent=True) or {}
    if request.method == "POST":
        macro = {
            "id": str(uuid.uuid4())[:8],
            "name": data.get("name", "Macro"),
            "steps": data.get("steps", []),
            "created": time.time()
        }
        macros.append(macro)
        save_json(MACROS_FILE, {"items": macros})
        return jsonify({"success": True, "macro": macro})
    mid = data.get("id", "")
    macros = [m for m in macros if m["id"] != mid]
    save_json(MACROS_FILE, {"items": macros})
    return jsonify({"success": True})

@app.route("/api/macros/run/<mid>", methods=["POST"])
def run_macro(mid):
    macros = load_json(MACROS_FILE, {"items": []}).get("items", [])
    m = next((x for x in macros if x["id"] == mid), None)
    if not m: return jsonify({"error": "Not found"}), 404
    data = request.get_json(silent=True) or {}
    project = safe_project(data.get("project", ""))
    if not project: return jsonify({"error": "Invalid project"}), 400
    results = []
    for step in m["steps"]:
        stype = step.get("type", "")
        try:
            if stype == "cmd":
                cmd = expand_alias(step.get("value", ""))
                r = subprocess.run(cmd, shell=True, cwd=str(project),
                                   capture_output=True, text=True, timeout=120)
                results.append({"step": step, "out": r.stdout, "err": r.stderr, "code": r.returncode})
            elif stype == "build":
                results.append({"step": step, "out": "build triggered"})
                trigger_auto_build(project.name)
            else:
                results.append({"step": step, "out": "skipped"})
        except Exception as e:
            results.append({"step": step, "err": str(e)})
    return jsonify({"success": True, "results": results})

# ---------------- KANBAN ----------------
@app.route("/api/kanban/<path:name>", methods=["GET", "POST"])
def kanban_mgr(name):
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    f = KANBAN_DIR / f"{safe}.json"
    if request.method == "GET":
        data = load_json(f, {"columns": {"todo": [], "doing": [], "done": []}})
        return jsonify(data)
    data = request.get_json(silent=True) or {}
    save_json(f, data)
    return jsonify({"success": True})

@app.route("/api/kanban/<path:name>/add", methods=["POST"])
def kanban_add(name):
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    f = KANBAN_DIR / f"{safe}.json"
    data = load_json(f, {"columns": {"todo": [], "doing": [], "done": []}})
    body = request.get_json(silent=True) or {}
    col = body.get("column", "todo")
    if col not in data["columns"]:
        data["columns"][col] = []
    data["columns"][col].append({
        "id": str(uuid.uuid4())[:8],
        "text": body.get("text", ""),
        "priority": body.get("priority", "normal"),
        "ts": time.time()
    })
    save_json(f, data)
    return jsonify({"success": True, "data": data})

@app.route("/api/kanban/<path:name>/move", methods=["POST"])
def kanban_move(name):
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    f = KANBAN_DIR / f"{safe}.json"
    data = load_json(f, {"columns": {"todo": [], "doing": [], "done": []}})
    body = request.get_json(silent=True) or {}
    card_id = body.get("id")
    from_col = body.get("from")
    to_col = body.get("to")
    for i, c in enumerate(data["columns"].get(from_col, [])):
        if c["id"] == card_id:
            card = data["columns"][from_col].pop(i)
            data["columns"].setdefault(to_col, []).append(card)
            break
    save_json(f, data)
    return jsonify({"success": True, "data": data})

@app.route("/api/kanban/<path:name>/del", methods=["POST"])
def kanban_del(name):
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    f = KANBAN_DIR / f"{safe}.json"
    data = load_json(f, {"columns": {"todo": [], "doing": [], "done": []}})
    body = request.get_json(silent=True) or {}
    col = body.get("column")
    cid = body.get("id")
    if col in data["columns"]:
        data["columns"][col] = [c for c in data["columns"][col] if c["id"] != cid]
    save_json(f, data)
    return jsonify({"success": True, "data": data})

# ---------------- NOTES ----------------
@app.route("/api/notes/<path:name>", methods=["GET", "POST"])
def notes_mgr(name):
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    f = NOTES_DIR / f"{safe}.json"
    if request.method == "GET":
        return jsonify(load_json(f, {"content": "", "updated": 0}))
    data = request.get_json(silent=True) or {}
    save_json(f, {
        "content": data.get("content", ""),
        "updated": time.time()
    })
    return jsonify({"success": True})

# ---------------- BOOKMARKS ----------------
@app.route("/api/bookmarks/<path:name>", methods=["GET", "POST", "DELETE"])
def bookmarks_mgr(name):
    all_b = load_json(BOOKMARKS_FILE, {})
    items = all_b.get(name, [])
    if request.method == "GET":
        return jsonify({"bookmarks": items})
    data = request.get_json(silent=True) or {}
    if request.method == "POST":
        bm = {
            "id": str(uuid.uuid4())[:8],
            "path": data.get("path", ""),
            "line": data.get("line", 1),
            "label": data.get("label", ""),
            "ts": time.time()
        }
        items.append(bm)
        all_b[name] = items[:100]
        save_json(BOOKMARKS_FILE, all_b)
        return jsonify({"success": True, "bookmark": bm})
    bid = data.get("id", "")
    items = [b for b in items if b["id"] != bid]
    all_b[name] = items
    save_json(BOOKMARKS_FILE, all_b)
    return jsonify({"success": True})

# ---------------- SNIPPETS ----------------
@app.route("/api/snippets", methods=["GET", "POST", "DELETE"])
def snippets_mgr():
    items = load_json(SNIPPETS_FILE, {"items": []}).get("items", [])
    if request.method == "GET":
        return jsonify({"items": items})
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        items.append({
            "name": data.get("name", "snippet"),
            "lang": data.get("lang", "text"),
            "code": data.get("code", ""),
            "ts": time.time()
        })
        save_json(SNIPPETS_FILE, {"items": items})
        return jsonify({"success": True, "items": items})
    data = request.get_json(silent=True) or {}
    idx = data.get("index", -1)
    if 0 <= idx < len(items):
        items.pop(idx)
        save_json(SNIPPETS_FILE, {"items": items})
    return jsonify({"success": True, "items": items})

# ---------------- DEV TOOLS ----------------
@app.route("/api/devtool/hash", methods=["POST"])
def devtool_hash():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    algo = data.get("algo", "sha256")
    try:
        h = hashlib.new(algo, text.encode("utf-8")).hexdigest()
        return jsonify({"result": h})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/devtool/base64", methods=["POST"])
def devtool_base64():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    mode = data.get("mode", "encode")
    try:
        if mode == "encode":
            return jsonify({"result": base64.b64encode(text.encode()).decode()})
        else:
            return jsonify({"result": base64.b64decode(text).decode("utf-8", errors="replace")})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/devtool/uuid")
def devtool_uuid():
    return jsonify({"uuid": str(uuid.uuid4())})

@app.route("/api/devtool/lorem")
def devtool_lorem():
    n = int(request.args.get("n", 3))
    import random
    words = "lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt ut labore et dolore magna aliqua".split()
    paras = []
    for _ in range(min(n, 20)):
        paras.append(" ".join(random.choice(words) for _ in range(50)).capitalize() + ".")
    return jsonify({"text": "\n\n".join(paras)})

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

# ---------------- EXPORT ----------------
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
const CACHE='zihad-ide-v12';
self.addEventListener('install',e=>self.skipWaiting());
self.addEventListener('activate',e=>e.waitUntil(clients.claim()));
self.addEventListener('fetch',e=>{
  if(e.request.method!=='GET')return;
  e.respondWith(fetch(e.request).catch(()=>caches.match(e.request)));
});
"""
    return Response(sw, mimetype="application/javascript")

# ============================================================
# END OF PART 2 — Paste PART 3 BELOW THIS LINE
# ============================================================

# ============================================================
# PART 3/3 : IDE_HTML (Full UI) + Main Block
# ============================================================

IDE_HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta name="theme-color" content="#3b82f6">
<link rel="manifest" href="/manifest.json">
<title>__NAME__ - Zihad IDE v12</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/theme/dracula.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/theme/material-darker.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/theme/monokai.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/dialog/dialog.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/fold/foldgutter.min.css">
<style>
:root{--bg:#070b14;--card:#111827;--border:#1f2937;--primary:#3b82f6;--text:#e2e8f0;--muted:#94a3b8;--success:#22c55e;--danger:#ef4444;--radius:14px;--bottom-h:64px;--header-h:52px}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
html,body{height:100%;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:14px;overflow:hidden}
body{background-image:radial-gradient(ellipse at top left,#0f172a 0%,#070b14 60%);-webkit-font-smoothing:antialiased}
header{padding:6px 10px;min-height:var(--header-h);background:rgba(15,23,42,.95);backdrop-filter:blur(16px);border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;gap:5px;position:relative;z-index:30;flex-wrap:wrap}
header h2{font-size:12px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;min-width:60px;display:flex;align-items:center;gap:5px}
header h2 i{color:#60a5fa}
.btn{border:0;border-radius:9px;padding:6px 9px;font-weight:600;font-size:11px;color:#fff;cursor:pointer;background:#374151;display:inline-flex;align-items:center;justify-content:center;gap:4px;transition:transform .15s}
.btn:active{transform:scale(.94)}
.btn i{pointer-events:none}
.btn-primary{background:linear-gradient(135deg,#3b82f6,#2563eb)}
.btn-success{background:linear-gradient(135deg,#22c55e,#16a34a)}
.btn-danger{background:linear-gradient(135deg,#ef4444,#dc2626)}
.btn-orange{background:linear-gradient(135deg,#f59e0b,#d97706)}
.btn-purple{background:linear-gradient(135deg,#8b5cf6,#7c3aed)}
.btn-pink{background:linear-gradient(135deg,#ec4899,#db2777)}
.badge{display:inline-block;padding:2px 7px;border-radius:20px;font-size:10px;font-weight:700}
.badge.ok{background:rgba(34,197,94,.2);color:#4ade80}
.badge.err{background:rgba(239,68,68,.25);color:#fca5a5}
.badge.info{background:rgba(59,130,246,.2);color:#93c5fd}
.notif-dot{position:relative}
.notif-dot::after{content:attr(data-count);position:absolute;top:-2px;right:-2px;background:#ef4444;color:#fff;font-size:9px;font-weight:700;border-radius:50%;min-width:15px;height:15px;display:flex;align-items:center;justify-content:center;padding:0 3px;border:1.5px solid #0f172a}
.notif-dot[data-count="0"]::after{display:none}
.bottom-nav{position:fixed;bottom:0;left:0;right:0;height:var(--bottom-h);background:rgba(15,23,42,.97);backdrop-filter:blur(16px);border-top:1px solid var(--border);display:flex;z-index:40;padding-bottom:env(safe-area-inset-bottom);overflow-x:auto}
.nav-item{flex:1;min-width:56px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;font-size:9px;color:var(--muted);cursor:pointer;padding:4px 2px;position:relative;transition:color .15s}
.nav-item.active{color:#60a5fa}
.nav-item.active::before{content:"";position:absolute;top:0;left:22%;right:22%;height:3px;background:linear-gradient(90deg,transparent,#3b82f6,transparent);border-radius:3px}
.nav-item i{font-size:18px}
.main-area{height:calc(100vh - var(--header-h) - var(--bottom-h));overflow:hidden}
.panel{display:none;height:100%;overflow-y:auto;padding:10px;padding-bottom:22px;-webkit-overflow-scrolling:touch}
.panel.active{display:block}
.breadcrumb{background:rgba(8,15,28,.7);padding:8px 11px;border-radius:10px;margin-bottom:8px;font-size:12px;word-break:break-all}
.breadcrumb span{color:#60a5fa;cursor:pointer}
.file-item{background:var(--card);padding:10px;margin:4px 0;border-radius:11px;border:1px solid var(--border);cursor:pointer;display:flex;align-items:center;gap:8px;transition:transform .12s;position:relative;overflow:hidden}
.file-item:active{transform:scale(.98);background:#1f2937}
.file-item .icon-wrap{width:36px;height:36px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0;color:#fff}
.file-item.folder .icon-wrap{background:linear-gradient(135deg,#f59e0b,#d97706)}
.file-item.file .icon-wrap{background:linear-gradient(135deg,#3b82f6,#2563eb)}
.file-item.file.code .icon-wrap{background:linear-gradient(135deg,#8b5cf6,#7c3aed)}
.file-item.file.image .icon-wrap{background:linear-gradient(135deg,#22c55e,#16a34a)}
.file-item.file.video .icon-wrap{background:linear-gradient(135deg,#ec4899,#db2777)}
.file-item.file.audio .icon-wrap{background:linear-gradient(135deg,#f97316,#ea580c)}
.file-item.file.doc .icon-wrap{background:linear-gradient(135deg,#06b6d4,#0891b2)}
.file-item.file.zip .icon-wrap{background:linear-gradient(135deg,#a3a3a3,#525252)}
.file-item .name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px;color:#e2e8f0}
.file-item.folder .name{color:#fbbf24;font-weight:600}
.file-item .name mark{background:rgba(59,130,246,.4);color:#93c5fd;padding:0 2px;border-radius:3px;font-weight:700}
.file-item .size-badge{background:rgba(139,92,246,.2);color:#c4b5fd;padding:2px 7px;border-radius:6px;font-size:10px;font-weight:700;flex-shrink:0}
.file-item .meta{font-size:10px;color:var(--muted);white-space:nowrap}
.toolbar{display:flex;gap:5px;margin-bottom:8px;flex-wrap:wrap}
.sort-bar{display:flex;gap:5px;margin-bottom:8px}
.sort-bar select{padding:7px 9px;border-radius:8px;border:1px solid var(--border);background:#0b1220;color:#fff;font-size:12px;flex:1}
.search-box{display:flex;gap:6px;margin-bottom:8px}
.search-box input{flex:1;padding:10px 12px;border-radius:10px;border:1px solid var(--border);background:#0b1220;color:#fff;font-size:13px;outline:none}
#editor-box{position:fixed;inset:0;background:var(--bg);z-index:100;display:none;flex-direction:column}
#editor-header{padding:6px 9px;background:rgba(15,23,42,.95);border-bottom:1px solid var(--border);display:flex;align-items:center;gap:5px;flex-wrap:wrap}
.tab-bar-editor{display:flex;overflow-x:auto;background:#0b1220;border-bottom:1px solid var(--border)}
.editor-tab{padding:8px 12px;font-size:12px;white-space:nowrap;cursor:pointer;border-bottom:2px solid transparent;color:var(--muted);display:flex;align-items:center;gap:6px}
.editor-tab.active{color:#60a5fa;border-bottom-color:#3b82f6;background:rgba(59,130,246,.08)}
.editor-tab .close-tab{opacity:.55;font-size:14px;padding:0 2px;line-height:1}
#editor-toolbar{padding:4px 7px;background:#0b1220;border-bottom:1px solid var(--border);display:flex;gap:3px;flex-wrap:wrap;overflow-x:auto}
#editor-toolbar button{background:#1f2937;color:#e2e8f0;border:0;border-radius:6px;padding:5px 9px;font-size:11px;font-weight:600;cursor:pointer;white-space:nowrap;display:flex;align-items:center;gap:3px}
#editor-toolbar button:active{background:#374151}
#editor-container{flex:1;overflow:hidden;position:relative}
.CodeMirror{height:100%!important;font-size:13px;font-family:'JetBrains Mono',Consolas,monospace}
.cm-error-line{background:rgba(239,68,68,.18)!important}
.split-toggle{position:absolute;top:8px;right:8px;z-index:101;padding:5px 9px;font-size:10px;background:#1f2937;color:#94a3b8;border:0;border-radius:6px;cursor:pointer}
.split-pane{position:absolute;right:0;top:0;bottom:0;width:45%;background:#0f172a;border-left:1px solid var(--border);overflow:auto;padding:10px;display:none}
.split-pane.show{display:block}
.output-box{background:#000;color:#4ade80;padding:11px;border-radius:11px;min-height:180px;white-space:pre-wrap;font-family:monospace;font-size:12px;border:1px solid #1f2937;max-height:calc(100vh - 260px);overflow-y:auto}
#terminal-output{background:#000;color:#4ade80;padding:11px;border-radius:11px;min-height:180px;max-height:calc(100vh - 400px);overflow-y:auto;font-size:12px;white-space:pre-wrap;font-family:monospace;border:1px solid #1f2937;margin-bottom:8px}
#cmd-input{display:flex;gap:5px}
#cmd-input input{flex:1;padding:10px;background:#0b1220;color:#e2e8f0;border:1px solid #374151;border-radius:9px;font-family:monospace;font-size:13px;outline:none}
#cmd-input button{padding:10px 14px;background:var(--success);color:#fff;border:0;border-radius:9px;font-weight:700}
.terminal-presets{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:5px;margin-bottom:10px;max-height:180px;overflow-y:auto;padding:2px}
.terminal-presets button{background:linear-gradient(135deg,#1e293b,#0f172a);border:1px solid #334155;color:#cbd5e1;padding:7px 9px;font-size:11px;border-radius:10px;text-align:left;display:flex;align-items:center;gap:5px;cursor:pointer;font-weight:600}
.terminal-presets button:hover{background:#334155;color:#60a5fa}
.terminal-presets button i{color:#60a5fa;font-size:12px;width:14px}
.pty-term{background:#000;color:#d1fae5;padding:10px;font-family:'JetBrains Mono',monospace;font-size:12px;border-radius:11px;border:1px solid #1f2937;height:calc(100vh - 340px);overflow-y:auto;white-space:pre-wrap;word-break:break-all}
.pty-input{display:flex;gap:5px;margin-top:8px}
.pty-input input{flex:1;background:#0b1220;border:1px solid #374151;border-radius:9px;padding:10px;color:#fff;font-family:monospace;font-size:13px;outline:none}
.system-card{background:linear-gradient(135deg,#1e1b4b,#0f172a);border:1px solid #312e81;border-radius:14px;padding:12px;margin-bottom:12px}
.system-card h4{color:#a5b4fc;font-size:11px;margin-bottom:6px;text-transform:uppercase;letter-spacing:.5px;display:flex;align-items:center;gap:5px}
.stat-row{display:flex;justify-content:space-between;font-size:11px;padding:3px 0;border-bottom:1px solid rgba(99,102,241,.15)}
.stat-row:last-child{border-bottom:0}
.stat-row b{color:#c7d2fe;font-weight:600}
.err-item{background:rgba(127,29,29,.5);color:#fecaca;padding:11px;border-radius:9px;margin:5px 0;cursor:pointer;border-left:4px solid #ef4444;font-family:monospace;font-size:12px}
.info-bar{background:rgba(8,15,28,.7);padding:9px;border-radius:9px;margin-bottom:9px;font-size:12px;border:1px solid var(--border)}
.build-panel{background:#0b1220;border:1px solid #1f2937;border-radius:13px;padding:14px;margin-bottom:12px}
.progress-wrap{background:#1f2937;border-radius:20px;height:26px;overflow:hidden;position:relative;margin:10px 0}
.progress-bar{height:100%;background:linear-gradient(90deg,#3b82f6,#8b5cf6);transition:width .4s;width:0%}
.progress-text{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;color:#fff}
.toast-container{position:fixed;bottom:calc(var(--bottom-h)+16px);left:50%;transform:translateX(-50%);z-index:999;display:flex;flex-direction:column;gap:7px;pointer-events:none}
.toast{background:rgba(15,23,42,.96);border:1px solid var(--border);color:#fff;padding:10px 16px;border-radius:11px;font-size:13px;display:flex;align-items:center;gap:8px;animation:slideUp .3s}
@keyframes slideUp{from{transform:translateY(20px);opacity:0}}
.toast.success{border-color:rgba(34,197,94,.45)}
.toast.error{border-color:rgba(239,68,68,.45)}
.toast.info{border-color:rgba(59,130,246,.45)}
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:200;display:none;align-items:flex-end;justify-content:center;backdrop-filter:blur(4px)}
.modal-overlay.show{display:flex}
.modal{background:#111827;border-radius:20px 20px 0 0;padding:20px;width:100%;max-width:560px;max-height:88vh;overflow-y:auto;animation:slideUp .25s;border:1px solid var(--border);border-bottom:0}
.modal h3{font-size:15px;margin-bottom:10px;color:#60a5fa;display:flex;align-items:center;gap:7px}
.modal input,.modal textarea,.modal select{width:100%;padding:10px 12px;margin:5px 0;border-radius:10px;border:1px solid #374151;background:#0b1220;color:#fff;font-size:13px;outline:none}
.modal textarea{font-family:monospace;min-height:110px;resize:vertical}
.empty{color:var(--muted);text-align:center;padding:25px;font-style:italic}
.preview-frame{background:#0f172a;border-radius:24px;border:6px solid #1e293b;width:min(320px,90vw);margin:0 auto;overflow:hidden;min-height:480px;position:relative;transition:width .2s}
.preview-frame.tablet{width:min(520px,95vw);min-height:380px}
.preview-frame.desktop{width:min(90vw,900px);min-height:400px}
.preview-content{padding:14px;min-height:440px;color:#fff}
.device-frames{display:flex;gap:5px;margin-bottom:10px;justify-content:center;flex-wrap:wrap}
.device-frames button{background:#1f2937;color:#94a3b8;padding:6px 11px;font-size:11px}
.device-frames button.active{background:#3b82f6;color:#fff}
.cmd-palette{position:fixed;top:18%;left:50%;transform:translateX(-50%);width:min(500px,92vw);background:#0b1220;border:1px solid #1f2937;border-radius:14px;z-index:500;display:none;box-shadow:0 20px 60px rgba(0,0,0,.7);overflow:hidden}
.cmd-palette.show{display:block}
.cmd-palette input{width:100%;padding:14px 16px;background:transparent;border:0;color:#fff;font-size:15px;outline:none;border-bottom:1px solid #1f2937}
.cmd-palette ul{list-style:none;max-height:340px;overflow-y:auto}
.cmd-palette li{padding:11px 16px;cursor:pointer;font-size:13px;color:#cbd5e1;border-bottom:1px solid #111827;display:flex;align-items:center;gap:8px}
.cmd-palette li:hover,.cmd-palette li.active{background:#1f2937;color:#60a5fa}
.cmd-palette li i{width:18px;color:#8b5cf6}
.more-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(100px,1fr));gap:8px;margin:8px 0}
.more-item{background:linear-gradient(135deg,#1e293b,#0f172a);border:1px solid #334155;border-radius:11px;padding:12px 8px;text-align:center;cursor:pointer;font-size:11px;color:#cbd5e1;transition:.15s;font-weight:600}
.more-item:active{transform:scale(.95)}
.more-item:hover{background:linear-gradient(135deg,#334155,#1e293b);color:#60a5fa}
.more-item i{font-size:22px;display:block;margin-bottom:5px;color:#8b5cf6}
.devtool-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:8px;margin:8px 0}
.devtool-item{background:linear-gradient(135deg,#1e293b,#0f172a);border:1px solid #334155;border-radius:12px;padding:12px 10px;text-align:center;cursor:pointer;font-size:11px;color:#cbd5e1;transition:.15s;font-weight:600}
.devtool-item:hover{background:linear-gradient(135deg,#334155,#1e293b);color:#60a5fa;transform:translateY(-2px)}
.devtool-item i{font-size:22px;display:block;margin-bottom:5px;color:#8b5cf6}
.logcat-line{font-family:monospace;font-size:11px;padding:2px 4px;border-bottom:1px solid #0f172a;word-break:break-all}
.logcat-line.err{color:#f87171}
.logcat-line.warn{color:#fbbf24}
.logcat-line.info{color:#60a5fa}
.git-item{background:#0b1220;border:1px solid #1f2937;border-radius:8px;padding:8px 10px;margin:3px 0;font-family:monospace;font-size:11px}
.kanban-board{display:grid;grid-template-columns:1fr;gap:10px}
@media(min-width:600px){.kanban-board{grid-template-columns:repeat(3,1fr)}}
.kanban-col{background:#0b1220;border:1px solid #1f2937;border-radius:12px;padding:10px;min-height:150px}
.kanban-col h4{font-size:12px;color:#60a5fa;margin-bottom:8px;display:flex;justify-content:space-between;align-items:center}
.kanban-card{background:#1e293b;padding:8px 10px;border-radius:8px;margin-bottom:6px;font-size:12px;cursor:pointer;border-left:3px solid #3b82f6;position:relative}
.kanban-card.p-high{border-left-color:#ef4444}
.kanban-card.p-low{border-left-color:#22c55e}
.kanban-card .del{position:absolute;top:5px;right:5px;color:#ef4444;opacity:.6;font-size:11px}
.notif-item{background:#0b1220;border:1px solid #1f2937;border-radius:10px;padding:10px;margin-bottom:6px;border-left:3px solid #3b82f6;font-size:12px}
.notif-item.success{border-left-color:#22c55e}
.notif-item.error{border-left-color:#ef4444}
.notif-item .time{font-size:10px;color:#64748b;margin-top:3px}
.notif-item .ttl{color:#e2e8f0;font-weight:600;margin-bottom:2px}
.notif-item .bdy{color:#94a3b8;font-size:11px}
.chart-bar{background:#1f2937;border-radius:3px;overflow:hidden}
.chart-wrap{display:flex;gap:3px;align-items:flex-end;height:100px;padding:6px;background:#0b1220;border-radius:10px;border:1px solid #1f2937}
.chart-col{flex:1;background:linear-gradient(180deg,#3b82f6,#8b5cf6);border-radius:3px 3px 0 0;min-height:4px;transition:height .3s;position:relative}
.chart-col.ok{background:linear-gradient(180deg,#22c55e,#16a34a)}
.chart-col.fail{background:linear-gradient(180deg,#ef4444,#dc2626)}
.plugin-item{background:#0b1220;border:1px solid #1f2937;border-radius:10px;padding:10px;margin-bottom:6px}
.plugin-item h5{font-size:12px;color:#60a5fa;margin-bottom:3px}
.plugin-item p{font-size:11px;color:#94a3b8;margin-bottom:6px}
.fab-2026{position:fixed;bottom:calc(var(--bottom-h) + 16px);right:16px;width:52px;height:52px;border-radius:50%;background:linear-gradient(135deg,#6366f1,#8b5cf6);box-shadow:0 8px 30px rgba(139,92,246,.6);display:flex;align-items:center;justify-content:center;color:#fff;font-size:20px;z-index:45;border:0;cursor:pointer;transition:transform .2s}
.fab-2026:active{transform:scale(.9) rotate(90deg)}
@media(min-width:720px){
  .main-area{max-width:1100px;margin:0 auto}
  .file-item{padding:13px}
  .terminal-presets{grid-template-columns:repeat(auto-fill,minmax(170px,1fr));max-height:280px}
  .pty-term{height:calc(100vh - 300px)}
  header h2{font-size:14px}
}
@media(max-width:380px){
  .btn{padding:5px 7px;font-size:10px}
  header h2{font-size:11px}
  .bottom-nav .nav-item{font-size:8px}
}
</style>
</head>
<body>
<header>
  <h2><i class="fa-solid fa-bolt"></i> __NAME__</h2>
  <div style="display:flex;gap:3px;flex-wrap:wrap">
    <button class="btn btn-orange" onclick="scanAllErrors()" id="scanBtn" title="Scan"><i class="fa-solid fa-magnifying-glass"></i></button>
    <button class="btn btn-purple" onclick="runCurrent()" id="runBtn" style="display:none" title="Run"><i class="fa-solid fa-play"></i></button>
    <button class="btn btn-primary" onclick="buildApk()" title="Build"><i class="fa-solid fa-hammer"></i></button>
    <button class="btn notif-dot" id="notifBtn" data-count="0" onclick="showNotifications()" title="Notifications"><i class="fa-solid fa-bell"></i></button>
    <button class="btn" onclick="exportZip()" title="Export"><i class="fa-solid fa-file-zipper"></i></button>
    <button class="btn" onclick="showMoreMenu()" title="More"><i class="fa-solid fa-ellipsis"></i></button>
    <button class="btn" onclick="openCommandPalette()" title="Cmd"><i class="fa-solid fa-bolt"></i></button>
    <button class="btn" onclick="openSettings()" title="Settings"><i class="fa-solid fa-gear"></i></button>
    <button class="btn" onclick="location.href='/'" title="Home"><i class="fa-solid fa-house"></i></button>
  </div>
</header>

<div class="main-area">
  <!-- FILES -->
  <div class="panel active" id="panel-explorer">
    <div class="toolbar">
      <button class="btn btn-success" onclick="newFile()"><i class="fa-solid fa-file-circle-plus"></i> File</button>
      <button class="btn btn-orange" onclick="newFolder()"><i class="fa-solid fa-folder-plus"></i> Folder</button>
      <button class="btn upload-btn" style="position:relative;overflow:hidden"><i class="fa-solid fa-upload"></i> Upload<input type="file" style="position:absolute;inset:0;opacity:0;cursor:pointer;width:100%" onchange="doUpload(this)"></button>
      <button class="btn upload-btn" style="position:relative;overflow:hidden"><i class="fa-solid fa-file-zipper"></i> Zip<input type="file" accept=".zip" style="position:absolute;inset:0;opacity:0;cursor:pointer;width:100%" onchange="doExtract(this)"></button>
      <button class="btn" onclick="loadFiles(currentPath)"><i class="fa-solid fa-rotate"></i></button>
      <button class="btn" onclick="showRecent()"><i class="fa-solid fa-clock-rotate-left"></i></button>
    </div>
    <div class="sort-bar">
      <select id="sortBy" onchange="loadFiles(currentPath)">
        <option value="name">Name</option>
        <option value="size">Size</option>
        <option value="date">Date</option>
      </select>
    </div>
    <div class="search-box">
      <input id="searchInput" placeholder="Search files..." oninput="filterFiles(this.value)">
      <button class="btn" onclick="clearSearch()"><i class="fa-solid fa-xmark"></i></button>
    </div>
    <div class="breadcrumb" id="breadcrumb">Loading...</div>
    <div id="file-list"><div class="empty"><i class="fa-solid fa-spinner fa-spin"></i> Loading...</div></div>
  </div>

  <!-- PREVIEW -->
  <div class="panel" id="panel-preview">
    <div class="info-bar"><i class="fa-solid fa-eye"></i> Live Layout / HTML Preview</div>
    <div class="device-frames">
      <button class="active" onclick="setDevice('phone',this)"><i class="fa-solid fa-mobile"></i></button>
      <button onclick="setDevice('tablet',this)"><i class="fa-solid fa-tablet"></i></button>
      <button onclick="setDevice('desktop',this)"><i class="fa-solid fa-desktop"></i></button>
      <button onclick="refreshPreview()"><i class="fa-solid fa-rotate"></i></button>
      <button onclick="togglePreviewMode()" id="prevModeBtn">HTML</button>
    </div>
    <div class="preview-frame" id="previewFrame">
      <div class="preview-content" id="previewContent">
        <p style="text-align:center;color:#64748b;padding:40px 20px"><i class="fa-solid fa-mobile-screen"></i><br>Tap <i class="fa-solid fa-rotate"></i> to load</p>
      </div>
    </div>
  </div>

  <!-- ERRORS -->
  <div class="panel" id="panel-errors">
    <div class="info-bar" id="errInfo"><i class="fa-solid fa-bug"></i> Press scan to check</div>
    <div id="err-list"></div>
  </div>

  <!-- TERMINAL -->
  <div class="panel" id="panel-terminal">
    <div class="system-card" id="sysCard">
      <h4><i class="fa-solid fa-microchip"></i> System Monitor</h4>
      <div id="sysInfo">Loading...</div>
    </div>
    <div style="display:flex;justify-content:space-between;margin-bottom:7px;gap:5px;flex-wrap:wrap">
      <span style="font-size:12px;color:var(--muted)"><i class="fa-solid fa-terminal"></i> Terminal</span>
      <div style="display:flex;gap:3px">
        <button class="btn" style="padding:4px 9px;font-size:11px" onclick="startPTY()"><i class="fa-solid fa-terminal"></i> PTY</button>
        <button class="btn" style="padding:4px 9px;font-size:11px" onclick="showSavedCommands()"><i class="fa-solid fa-star"></i></button>
        <button class="btn" style="padding:4px 9px;font-size:11px" onclick="showAliases()"><i class="fa-solid fa-tag"></i></button>
        <button class="btn" style="padding:4px 9px;font-size:11px" onclick="clearTerminal()"><i class="fa-solid fa-broom"></i></button>
      </div>
    </div>
    <div class="terminal-presets" id="presetBox"></div>
    <div id="terminal-output">$ Zihad IDE Terminal — Ready
</div>
    <div id="cmd-input">
      <input id="cmd" placeholder="ls, pkg install git, python..." onkeydown="termKey(event)">
      <button onclick="runCmd()"><i class="fa-solid fa-paper-plane"></i></button>
    </div>
    <div id="ptyBox" style="display:none;margin-top:10px">
      <div class="pty-term" id="ptyOutput"></div>
      <div class="pty-input">
        <input id="ptyInput" placeholder="Interactive input..." onkeydown="ptyKey(event)">
        <button class="btn btn-success" onclick="ptySend()"><i class="fa-solid fa-arrow-right"></i></button>
        <button class="btn btn-danger" onclick="stopPTY()"><i class="fa-solid fa-stop"></i></button>
      </div>
    </div>
  </div>

  <!-- OUTPUT -->
  <div class="panel" id="panel-output">
    <div class="info-bar" id="run-info"><i class="fa-solid fa-play"></i> No code executed yet</div>
    <div class="output-box" id="output-box">Output will appear here...</div>
  </div>

  <!-- BUILD -->
  <div class="panel" id="panel-build">
    <div class="build-panel">
      <h3 style="margin:0 0 8px;font-size:14px;color:#60a5fa;display:flex;align-items:center;gap:6px"><i class="fa-solid fa-hammer"></i> APK Build</h3>
      <div class="progress-wrap">
        <div class="progress-bar" id="buildProgressBar"></div>
        <div class="progress-text" id="buildProgressText">0%</div>
      </div>
      <div id="currentTask" style="font-family:monospace;font-size:11px;color:#fbbf24;margin:8px 0"><i class="fa-solid fa-hourglass"></i> Press build to start</div>
      <div id="buildStatusMsg" style="text-align:center;font-size:12px;color:var(--muted)">Ready</div>
      <div style="display:flex;align-items:center;gap:6px;margin-top:8px;font-size:12px">
        <label style="display:flex;align-items:center;gap:5px;cursor:pointer">
          <input type="checkbox" id="autoBuildChk" onchange="toggleAutoBuild(this.checked)" style="width:auto;margin:0">
          <i class="fa-solid fa-robot"></i> Auto-build on save
        </label>
      </div>
      <div id="apk-box" style="display:none;margin-top:10px">
        <button class="btn btn-success" id="apkDownloadBtn" style="width:100%;padding:12px;margin-bottom:6px"><i class="fa-solid fa-download"></i> Download APK</button>
        <div style="display:flex;gap:5px">
          <button class="btn btn-primary" style="flex:1;padding:11px" onclick="adbInstall()"><i class="fa-solid fa-mobile-button"></i> ADB Install</button>
          <button class="btn btn-danger" style="flex:1;padding:11px" onclick="cleanBuild()"><i class="fa-solid fa-broom"></i> Clean</button>
        </div>
      </div>
    </div>
    <div class="info-bar"><i class="fa-solid fa-list-check"></i> Live Build Log</div>
    <div class="output-box" id="buildLog">$ Waiting...</div>
  </div>

  <!-- GIT -->
  <div class="panel" id="panel-git">
    <div class="info-bar" id="gitInfo"><i class="fa-brands fa-git-alt"></i> Git</div>
    <div class="toolbar">
      <button class="btn btn-success" onclick="gitAction('init')"><i class="fa-solid fa-wrench"></i> Init</button>
      <button class="btn btn-primary" onclick="gitAction('add')"><i class="fa-solid fa-plus"></i> Add</button>
      <button class="btn btn-purple" onclick="gitCommitPrompt()"><i class="fa-solid fa-floppy-disk"></i> Commit</button>
      <button class="btn" onclick="gitAction('log')"><i class="fa-solid fa-list-ul"></i></button>
      <button class="btn" onclick="gitAction('diff')"><i class="fa-solid fa-code-compare"></i></button>
      <button class="btn" onclick="gitAction('branches')"><i class="fa-solid fa-code-branch"></i></button>
    </div>
    <div class="toolbar">
      <button class="btn btn-success" onclick="gitRemote('push')"><i class="fa-solid fa-cloud-arrow-up"></i> Push</button>
      <button class="btn btn-orange" onclick="gitRemote('pull')"><i class="fa-solid fa-cloud-arrow-down"></i> Pull</button>
      <button class="btn" onclick="gitSetRemote()"><i class="fa-solid fa-link"></i></button>
    </div>
    <div id="gitOutput" class="output-box" style="min-height:150px;max-height:calc(100vh - 340px)"></div>
  </div>

  <!-- LOGCAT -->
  <div class="panel" id="panel-logcat">
    <div class="toolbar">
      <button class="btn btn-success" onclick="logcatStart()" id="lcStartBtn"><i class="fa-solid fa-play"></i> Start</button>
      <button class="btn btn-danger" onclick="logcatStop()"><i class="fa-solid fa-stop"></i></button>
      <button class="btn" onclick="logcatClear()"><i class="fa-solid fa-trash"></i></button>
      <select id="lcFilter" onchange="renderLogcat()" style="padding:7px 9px;border-radius:8px;border:1px solid var(--border);background:#0b1220;color:#fff;font-size:12px;flex:1">
        <option value="all">All</option>
        <option value="error">Errors</option>
        <option value="warn">Warn+</option>
        <option value="info">Info+</option>
      </select>
    </div>
    <div id="logcatBox" style="background:#000;border:1px solid #1f2937;border-radius:11px;max-height:calc(100vh - 260px);overflow-y:auto;padding:6px">Not started</div>
  </div>

  <!-- KANBAN -->
  <div class="panel" id="panel-kanban">
    <div class="info-bar"><i class="fa-solid fa-list-check"></i> Project Kanban Board</div>
    <div style="display:flex;gap:6px;margin-bottom:10px">
      <input id="kanbanInput" placeholder="New task..." style="flex:1;padding:10px;border-radius:10px;border:1px solid var(--border);background:#0b1220;color:#fff;font-size:13px;outline:none">
      <select id="kanbanPriority" style="padding:10px;border-radius:10px;border:1px solid var(--border);background:#0b1220;color:#fff;font-size:12px">
        <option value="normal">Normal</option>
        <option value="high">High</option>
        <option value="low">Low</option>
      </select>
      <button class="btn btn-success" onclick="kanbanAdd()"><i class="fa-solid fa-plus"></i></button>
    </div>
    <div class="kanban-board" id="kanbanBoard">Loading...</div>
  </div>

  <!-- NOTES -->
  <div class="panel" id="panel-notes">
    <div class="info-bar"><i class="fa-solid fa-note-sticky"></i> Project Notes</div>
    <textarea id="notesArea" placeholder="Your notes here..." style="width:100%;height:calc(100vh - 260px);background:#0b1220;color:#e2e8f0;border:1px solid var(--border);border-radius:12px;padding:12px;font-family:monospace;font-size:13px;resize:none;outline:none"></textarea>
    <button class="btn btn-primary" style="width:100%;margin-top:8px;padding:11px" onclick="saveNotes()"><i class="fa-solid fa-floppy-disk"></i> Save Notes</button>
  </div>

  <!-- ANALYTICS -->
  <div class="panel" id="panel-analytics">
    <div class="info-bar"><i class="fa-solid fa-chart-line"></i> Build Analytics</div>
    <div style="margin-bottom:14px">
      <h4 style="font-size:12px;color:#60a5fa;margin-bottom:6px"><i class="fa-solid fa-clock"></i> Build Time (last 20)</h4>
      <div class="chart-wrap" id="buildTimeChart"></div>
    </div>
    <div style="margin-bottom:14px">
      <h4 style="font-size:12px;color:#60a5fa;margin-bottom:6px"><i class="fa-solid fa-box-archive"></i> APK Size (KB)</h4>
      <div class="chart-wrap" id="apkSizeChart"></div>
    </div>
    <div style="margin-bottom:14px">
      <h4 style="font-size:12px;color:#60a5fa;margin-bottom:6px"><i class="fa-solid fa-triangle-exclamation"></i> Top Errors</h4>
      <div id="errFreqList" style="background:#0b1220;border:1px solid #1f2937;border-radius:10px;padding:10px;max-height:300px;overflow-y:auto"></div>
    </div>
  </div>
</div>

<nav class="bottom-nav">
  <div class="nav-item active" data-panel="explorer" onclick="switchPanel('explorer',this)"><i class="fa-solid fa-folder-tree"></i><span>Files</span></div>
  <div class="nav-item" data-panel="preview" onclick="switchPanel('preview',this)"><i class="fa-solid fa-mobile-screen"></i><span>Preview</span></div>
  <div class="nav-item" data-panel="errors" onclick="switchPanel('errors',this)"><i class="fa-solid fa-bug"></i><span>Errors</span></div>
  <div class="nav-item" data-panel="terminal" onclick="switchPanel('terminal',this)"><i class="fa-solid fa-terminal"></i><span>Term</span></div>
  <div class="nav-item" data-panel="build" onclick="switchPanel('build',this)"><i class="fa-solid fa-hammer"></i><span>Build</span></div>
  <div class="nav-item" data-panel="git" onclick="switchPanel('git',this)"><i class="fa-brands fa-git-alt"></i><span>Git</span></div>
  <div class="nav-item" data-panel="logcat" onclick="switchPanel('logcat',this)"><i class="fa-solid fa-list-ul"></i><span>Log</span></div>
  <div class="nav-item" data-panel="kanban" onclick="switchPanel('kanban',this)"><i class="fa-solid fa-list-check"></i><span>Todo</span></div>
  <div class="nav-item" data-panel="notes" onclick="switchPanel('notes',this)"><i class="fa-solid fa-note-sticky"></i><span>Notes</span></div>
  <div class="nav-item" data-panel="analytics" onclick="switchPanel('analytics',this)"><i class="fa-solid fa-chart-line"></i><span>Stats</span></div>
</nav>

<button class="fab-2026" onclick="openCommandPalette()"><i class="fa-solid fa-bolt"></i></button>

<!-- EDITOR -->
<div id="editor-box">
  <div id="editor-header">
    <span style="font-size:12px;color:#93c5fd;font-family:monospace;flex:1;overflow:hidden;text-overflow:ellipsis" id="editor-filename">file</span>
    <span id="editor-err-badge" class="badge ok">0</span>
    <button class="btn btn-success" onclick="saveFile(false)"><i class="fa-solid fa-floppy-disk"></i></button>
    <button class="btn btn-orange" onclick="checkCurrentFile()"><i class="fa-solid fa-magnifying-glass"></i></button>
    <button class="btn btn-purple" onclick="runCurrent()"><i class="fa-solid fa-play"></i></button>
    <button class="btn" onclick="toggleSplitPreview()"><i class="fa-solid fa-columns"></i></button>
    <button class="btn" onclick="showHistory()"><i class="fa-solid fa-clock-rotate-left"></i></button>
    <button class="btn" onclick="addBookmark()"><i class="fa-regular fa-bookmark"></i></button>
    <button class="btn" onclick="closeEditor()"><i class="fa-solid fa-xmark"></i></button>
  </div>
  <div class="tab-bar-editor" id="editorTabs"></div>
  <div id="editor-toolbar">
    <button onclick="doSelectAll()"><i class="fa-solid fa-object-group"></i>Select</button>
    <button onclick="doCut()"><i class="fa-solid fa-scissors"></i>Cut</button>
    <button onclick="doCopy()"><i class="fa-solid fa-copy"></i>Copy</button>
    <button onclick="doPaste()"><i class="fa-solid fa-paste"></i>Paste</button>
    <button onclick="doUndo()"><i class="fa-solid fa-rotate-left"></i></button>
    <button onclick="doRedo()"><i class="fa-solid fa-rotate-right"></i></button>
    <button onclick="doFind()"><i class="fa-solid fa-magnifying-glass"></i></button>
    <button onclick="doIndent()"><i class="fa-solid fa-indent"></i></button>
    <button onclick="formatCode()"><i class="fa-solid fa-wand-magic-sparkles"></i></button>
  </div>
  <div id="editor-container">
    <textarea id="editor"></textarea>
    <button class="split-toggle" onclick="toggleSplitPreview()">Split</button>
    <div class="split-pane" id="splitPane"></div>
  </div>
</div>

<!-- SETTINGS MODAL -->
<div class="modal-overlay" id="settingsModal" onclick="if(event.target===this)this.classList.remove('show')">
  <div class="modal">
    <h3><i class="fa-solid fa-gear"></i> Settings</h3>
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
      <option value="en">English</option>
      <option value="bn">বাংলা</option>
    </select>
    <div style="display:flex;gap:6px;margin-top:10px">
      <button class="btn btn-pink" style="flex:1;padding:11px" onclick="openCustomThemes()"><i class="fa-solid fa-palette"></i> Custom Themes</button>
      <button class="btn btn-purple" style="flex:1;padding:11px" onclick="openPlugins()"><i class="fa-solid fa-puzzle-piece"></i> Plugins</button>
    </div>
    <button class="btn btn-primary" style="width:100%;margin-top:10px;padding:12px" onclick="document.getElementById('settingsModal').classList.remove('show')">Done</button>
  </div>
</div>

<!-- MORE MODAL -->
<div class="modal-overlay" id="moreModal" onclick="if(event.target===this)this.classList.remove('show')">
  <div class="modal">
    <h3><i class="fa-solid fa-ellipsis"></i> More Tools</h3>
    <div class="more-grid">
      <div class="more-item" onclick="closeModal();openPkgRename()"><i class="fa-solid fa-box"></i>Rename Pkg</div>
      <div class="more-item" onclick="closeModal();openStrings()"><i class="fa-solid fa-language"></i>Strings</div>
      <div class="more-item" onclick="closeModal();openThemeBuilder()"><i class="fa-solid fa-brush"></i>Theme</div>
      <div class="more-item" onclick="closeModal();openManifest()"><i class="fa-solid fa-file-code"></i>Manifest</div>
      <div class="more-item" onclick="closeModal();openIconGen()"><i class="fa-solid fa-image"></i>Icon</div>
      <div class="more-item" onclick="closeModal();openEnvMgr()"><i class="fa-solid fa-key"></i>ENV</div>
      <div class="more-item" onclick="closeModal();openBulkRename()"><i class="fa-solid fa-i-cursor"></i>Bulk</div>
      <div class="more-item" onclick="closeModal();openFirebase()"><i class="fa-solid fa-fire"></i>Firebase</div>
      <div class="more-item" onclick="closeModal();bumpVersion()"><i class="fa-solid fa-hashtag"></i>Bump Ver</div>
      <div class="more-item" onclick="closeModal();openKeystore()"><i class="fa-solid fa-lock"></i>Keystore</div>
      <div class="more-item" onclick="closeModal();signRelease()"><i class="fa-solid fa-certificate"></i>Sign Rel</div>
      <div class="more-item" onclick="closeModal();openDevTools()"><i class="fa-solid fa-toolbox"></i>DevTools</div>
      <div class="more-item" onclick="closeModal();openSnippets()"><i class="fa-solid fa-scissors"></i>Snippets</div>
      <div class="more-item" onclick="closeModal();openMacros()"><i class="fa-solid fa-record-vinyl"></i>Macros</div>
      <div class="more-item" onclick="closeModal();showBookmarks()"><i class="fa-regular fa-bookmark"></i>Marks</div>
      <div class="more-item" onclick="closeModal();cleanBuild(true)"><i class="fa-solid fa-broom"></i>Clean</div>
      <div class="more-item" onclick="closeModal();showRecent()"><i class="fa-solid fa-clock-rotate-left"></i>Recent</div>
      <div class="more-item" onclick="closeModal();showShortcuts()"><i class="fa-solid fa-keyboard"></i>Keys</div>
      <div class="more-item" onclick="closeModal();location.href='/api/backup'"><i class="fa-solid fa-floppy-disk"></i>Backup</div>
      <div class="more-item" onclick="closeModal();openRestore()"><i class="fa-solid fa-download"></i>Restore</div>
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
var tasksSeen=0,EST_TOTAL=32,buildId=null,lastLineIdx=0;
var cmdHistory=[],histIdx=-1;
var autoSaveTimer=null;
var allFilesCache=[],folderSizes={};
var previewMode="android",currentDevice="phone";
var logcatSid=null,logcatTimer=null,logcatLines=[],logcatLastIdx=0;
var ptySid=null,ptyLastIdx=0,ptyTimer=null;
var PRESETS=[];
var notifLastSeen=0,notifPollTimer=null;
var autoBuildPollTimer=null;

// ============ UTILS ============
function toast(msg,type){type=type||"success";var c=document.getElementById("toasts");var t=document.createElement("div");t.className="toast "+type;var icon=type==="error"?'<i class="fa-solid fa-circle-xmark"></i>':type==="info"?'<i class="fa-solid fa-circle-info"></i>':'<i class="fa-solid fa-circle-check"></i>';t.innerHTML=icon+"<span>"+msg+"</span>";c.appendChild(t);setTimeout(function(){t.remove()},3000);}
function esc(t){var d=document.createElement("div");d.innerText=t;return d.innerHTML;}
function switchPanel(id,el){
  document.querySelectorAll(".nav-item").forEach(function(n){n.classList.remove("active");});
  document.querySelectorAll(".panel").forEach(function(p){p.classList.remove("active");});
  if(el) el.classList.add("active");
  else{var n=document.querySelector('[data-panel="'+id+'"]');if(n)n.classList.add("active");}
  var panel=document.getElementById("panel-"+id);
  if(panel) panel.classList.add("active");
  if(id==="preview")refreshPreview();
  if(id==="git")gitAction("status");
  if(id==="kanban")loadKanban();
  if(id==="notes")loadNotes();
  if(id==="analytics")loadAnalytics();
}
function getMode(filename){
  var ext=filename.split(".").pop().toLowerCase();
  var map={py:"python",c:"text/x-csrc",cpp:"text/x-c++src",cc:"text/x-c++src",
    java:"text/x-java",kt:"text/x-kotlin",js:"javascript",xml:"xml",html:"htmlmixed",
    css:"css",json:"application/json",md:"markdown",sh:"text/x-sh",gradle:"text/x-java"};
  return map[ext]||"null";
}
function showModal(html){document.getElementById("genericModalContent").innerHTML=html;document.getElementById("genericModal").classList.add("show");}
function closeModal(){document.getElementById("genericModal").classList.remove("show");}
function fileCategory(name){
  var ext=name.split(".").pop().toLowerCase();
  if(["java","kt","py","js","ts","c","cpp","cc","h","go","rs","rb","php","pl","sh","gradle"].indexOf(ext)>=0)return "code";
  if(["png","jpg","jpeg","gif","webp","svg","bmp"].indexOf(ext)>=0)return "image";
  if(["mp4","mov","avi","mkv","webm"].indexOf(ext)>=0)return "video";
  if(["mp3","wav","ogg","flac","m4a"].indexOf(ext)>=0)return "audio";
  if(["xml","json","html","css","md","txt","properties","yaml","yml"].indexOf(ext)>=0)return "doc";
  if(["zip","tar","gz","rar","7z","apk","jar"].indexOf(ext)>=0)return "zip";
  return "";
}
function fileIcon(name,isFolder){
  if(isFolder) return "fa-folder";
  var ext=name.split(".").pop().toLowerCase();
  var map={java:"fa-java",kt:"fa-k",py:"fa-python",js:"fa-node-js",ts:"fa-code",
    c:"fa-code",cpp:"fa-code",h:"fa-code",go:"fa-code",rs:"fa-cog",rb:"fa-gem",
    php:"fa-php",sh:"fa-terminal",gradle:"fa-cubes",
    xml:"fa-file-code",json:"fa-file-code",html:"fa-html5",css:"fa-css3-alt",
    md:"fa-markdown",txt:"fa-file-lines",properties:"fa-sliders",
    png:"fa-image",jpg:"fa-image",jpeg:"fa-image",gif:"fa-image",svg:"fa-bezier-curve",
    mp4:"fa-video",mov:"fa-video",mp3:"fa-music",wav:"fa-music",
    zip:"fa-file-zipper",tar:"fa-file-zipper",apk:"fa-android",jar:"fa-mug-hot",
    sql:"fa-database",db:"fa-database"};
  return map[ext]||"fa-file";
}
function highlight(name,q){
  if(!q)return esc(name);
  var idx=name.toLowerCase().indexOf(q.toLowerCase());
  if(idx<0)return esc(name);
  return esc(name.slice(0,idx))+"<mark>"+esc(name.slice(idx,idx+q.length))+"</mark>"+esc(name.slice(idx+q.length));
}

// ============ FILES ============
async function loadFiles(path){
  currentPath=path||"";
  var box=document.getElementById("file-list");
  var bc=document.getElementById("breadcrumb");
  box.innerHTML='<div class="empty"><i class="fa-solid fa-spinner fa-spin"></i> Loading...</div>';
  try{
    var sort=(document.getElementById("sortBy")&&document.getElementById("sortBy").value)||"name";
    var r=await fetch("/api/project-files/"+encodeURIComponent(PROJECT)+"?path="+encodeURIComponent(currentPath)+"&sort="+sort);
    var d=await r.json();
    if(!r.ok){box.innerHTML='<div class="empty" style="color:#f87171">'+(d.error||r.status)+'</div>';return;}
    var parts=currentPath?currentPath.split("/"):[];
    var bcHtml='<span onclick="loadFiles(\'\')"><i class="fa-solid fa-folder"></i> '+esc(PROJECT)+'</span>';
    var acc="";
    parts.forEach(function(p){acc+=(acc?"/":"")+p;bcHtml+=' / <span onclick="loadFiles(\''+acc+'\')">'+esc(p)+'</span>';});
    bc.innerHTML=bcHtml;
    allFilesCache=d.files||[];
    if(!allFilesCache.length){box.innerHTML='<div class="empty"><i class="fa-solid fa-folder-open"></i> Empty folder</div>';return;}
    await renderFileList(allFilesCache);
  }catch(e){box.innerHTML='<div class="empty" style="color:#f87171">'+e.message+'</div>';}
}
async function renderFileList(files){
  var box=document.getElementById("file-list");
  box.innerHTML="";
  try{
    var r=await fetch("/api/all-folder-sizes/"+encodeURIComponent(PROJECT)+"?path="+encodeURIComponent(currentPath));
    if(r.ok){var d=await r.json();folderSizes=d.sizes||{};}
  }catch(e){}
  if(currentPath){
    var parts=currentPath.split("/");var up=parts.slice(0,-1).join("/");
    var d=document.createElement("div");d.className="file-item folder";
    d.innerHTML='<div class="icon-wrap"><i class="fa-solid fa-arrow-up"></i></div><span class="name">.. up</span>';
    d.onclick=function(){loadFiles(up);};box.appendChild(d);
  }
  var q=(document.getElementById("searchInput")&&document.getElementById("searchInput").value)||"";
  files.forEach(function(f){
    var div=document.createElement("div");
    var cat=f.type==="file"?fileCategory(f.name):"";
    div.className="file-item "+(f.type==="directory"?"folder":"file "+cat);
    var icon=fileIcon(f.name,f.type==="directory");
    var sizeText="";
    if(f.type==="directory")sizeText=folderSizes[f.name]||"...";
    else sizeText=f.size_h||"";
    div.innerHTML='<div class="icon-wrap"><i class="fa-solid '+icon+'"></i></div>'+
      '<span class="name">'+highlight(f.name,q)+'</span>'+
      '<span class="size-badge">'+esc(sizeText)+'</span>'+
      '<span class="meta">'+esc(f.mtime?f.mtime.slice(5,16):"")+'</span>';
    div.onclick=function(){if(f.type==="directory")loadFiles(f.path);else openFile(f.path);};
    div.oncontextmenu=function(e){e.preventDefault();showItemMenu(f);};
    var pressTimer;
    div.addEventListener("touchstart",function(){pressTimer=setTimeout(function(){showItemMenu(f);},600);});
    div.addEventListener("touchend",function(){clearTimeout(pressTimer);});
    div.addEventListener("touchmove",function(){clearTimeout(pressTimer);});
    box.appendChild(div);
  });
}
function filterFiles(q){
  q=(q||"").trim();
  if(!q){renderFileList(allFilesCache);return;}
  if(q.length>=2){
    fetch("/api/search/"+encodeURIComponent(PROJECT)+"?q="+encodeURIComponent(q))
      .then(function(r){return r.json();}).then(function(d){
        var box=document.getElementById("file-list");box.innerHTML="";
        if(!d.results||!d.results.length){box.innerHTML='<div class="empty"><i class="fa-solid fa-magnifying-glass"></i><br>No results</div>';return;}
        d.results.forEach(function(f){
          var div=document.createElement("div");
          var cat=fileCategory(f.name);
          div.className="file-item file "+cat;
          div.innerHTML='<div class="icon-wrap"><i class="fa-solid '+fileIcon(f.name,false)+'"></i></div><span class="name">'+highlight(f.path,q)+'</span>';
          div.onclick=function(){openFile(f.path);};box.appendChild(div);
        });
      });
  }else{
    var filtered=allFilesCache.filter(function(f){return f.name.toLowerCase().indexOf(q.toLowerCase())!==-1;});
    renderFileList(filtered);
  }
}
function clearSearch(){document.getElementById("searchInput").value="";renderFileList(allFilesCache);}
function showItemMenu(f){
  var c=prompt("Action for: "+f.name+"\n1=Open  2=Rename  3=Delete  4=Copy  5=Check  6=Bookmark");
  if(c==="1"){if(f.type==="directory")loadFiles(f.path);else openFile(f.path);}
  else if(c==="2"){var nn=prompt("New name:",f.name);if(nn&&nn!==f.name)fileOp("rename",f.path,nn);}
  else if(c==="3"){if(confirm("Delete "+f.name+"?"))fileOp("delete",f.path);}
  else if(c==="4"){var nn=prompt("Copy as:",f.name+"_copy");if(nn)fileOp("copy",f.path,nn);}
  else if(c==="5"&&f.type==="file")checkFileErrors(f.path,true);
  else if(c==="6"){fetch("/api/bookmarks/"+encodeURIComponent(PROJECT),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({path:f.path,line:1,label:f.name})}).then(function(){toast("Bookmarked");});}
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
    if(newName)body.newName=newName;
    if(content!==undefined)body.content=content;
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
    var html='<h3><i class="fa-solid fa-clock-rotate-left"></i> Recent Files</h3>';
    if(!d.items||!d.items.length)html+='<div class="empty">No recent files</div>';
    else{
      html+='<div style="max-height:400px;overflow-y:auto">';
      d.items.forEach(function(it){
        html+='<div class="file-item file" onclick="closeModal();location.href=\'/project/'+encodeURIComponent(it.project)+'\'"><div class="icon-wrap"><i class="fa-solid fa-file"></i></div><span class="name">'+esc(it.project)+' / '+esc(it.path)+'<br><small style="color:#94a3b8">'+esc(it.mtime)+'</small></span></div>';
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
    document.getElementById("runBtn").style.display=runnable.indexOf(ext)>=0?"inline-flex":"none";
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
      clearTimeout(autoSaveTimer);autoSaveTimer=setTimeout(function(){saveFile(true);},2500);
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
async function doCut(){if(!cm)return;var s=cm.getSelection();if(!s){toast("Select first");return;}try{await navigator.clipboard.writeText(s);cm.replaceSelection("");toast("Cut");}catch(e){toast("Failed","error");}}
async function doCopy(){if(!cm)return;var s=cm.getSelection();if(!s){toast("Select first");return;}try{await navigator.clipboard.writeText(s);toast("Copied");}catch(e){var ta=document.createElement("textarea");ta.value=s;document.body.appendChild(ta);ta.select();document.execCommand("copy");document.body.removeChild(ta);toast("Copied");}}
async function doPaste(){if(!cm)return;try{var t=await navigator.clipboard.readText();cm.replaceSelection(t);}catch(e){toast("Paste blocked","error");}}
function doUndo(){if(cm)cm.undo();}
function doRedo(){if(cm)cm.redo();}
function doFind(){if(cm)cm.execCommand("find");}
function doIndent(){if(!cm)return;var s=cm.getSelection();if(!s){cm.execCommand("indentMore");return;}cm.replaceSelection(s.split("\n").map(function(l){return "    "+l;}).join("\n"));}
function formatCode(){
  if(!cm)return;
  var lines=cm.getValue().split("\n");var indent=0;
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
  document.getElementById("scanBtn").innerHTML='<i class="fa-solid fa-spinner fa-spin"></i>';
  document.getElementById("errInfo").innerHTML='<i class="fa-solid fa-spinner fa-spin"></i> Scanning...';
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
        fh.innerHTML='<i class="fa-solid fa-file-code"></i> '+esc(f.path)+' — '+f.errors.length+' error(s)';
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
    if(total===0){document.getElementById("errInfo").innerHTML='<i class="fa-solid fa-circle-check" style="color:#4ade80"></i> No errors in '+d.scanned+' files';}
    else{document.getElementById("errInfo").innerHTML='<i class="fa-solid fa-triangle-exclamation" style="color:#f87171"></i> '+bad+' file(s) • '+total+' error(s)';}
  }catch(e){document.getElementById("errInfo").innerText="Error: "+e;}
  document.getElementById("scanBtn").innerHTML='<i class="fa-solid fa-magnifying-glass"></i>';
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
    var html='<h3><i class="fa-solid fa-clock-rotate-left"></i> History: '+esc(path.split("/").pop())+'</h3>';
    if(!d.versions||!d.versions.length)html+='<div class="empty">No versions yet</div>';
    else d.versions.forEach(function(v){
      html+='<div class="file-item file" onclick="restoreHistory(\''+esc(path)+'\',\''+esc(v.file)+'\')"><div class="icon-wrap"><i class="fa-solid fa-clock"></i></div><span class="name">'+esc(v.mtime)+'<br><small style="color:#94a3b8">'+esc(v.size)+'</small></span></div>';
    });
    html+='<button class="btn" style="width:100%;margin-top:10px;padding:12px" onclick="closeModal()">Close</button>';
    showModal(html);
  }catch(e){toast("Error","error");}
}
async function restoreHistory(path,version){
  if(!confirm("Restore this version?"))return;
  try{
    var r=await fetch("/api/history-restore",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({project:PROJECT,path:path,version:version})});
    var d=await r.json();
    if(r.ok){toast("Restored");closeModal();if(cm){var rr=await fetch("/api/file-content/"+encodeURIComponent(PROJECT)+"?path="+encodeURIComponent(path));var dd=await rr.json();cm.setValue(dd.content);}}
    else toast(d.error||"Fail","error");
  }catch(e){toast("Error","error");}
}
async function addBookmark(){
  if(activeTabIdx<0)return;
  var path=openTabs[activeTabIdx].path;
  var line=cm?cm.getCursor().line+1:1;
  var label=prompt("Bookmark label:",path.split("/").pop());
  if(!label)return;
  try{
    await fetch("/api/bookmarks/"+encodeURIComponent(PROJECT),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({path:path,line:line,label:label})});
    toast("Bookmarked");
  }catch(e){toast("Error","error");}
}
async function showBookmarks(){
  try{
    var r=await fetch("/api/bookmarks/"+encodeURIComponent(PROJECT));
    var d=await r.json();
    var html='<h3><i class="fa-regular fa-bookmark"></i> Bookmarks</h3>';
    if(!d.bookmarks||!d.bookmarks.length)html+='<div class="empty">No bookmarks</div>';
    else d.bookmarks.forEach(function(b){
      html+='<div class="file-item file"><div class="icon-wrap"><i class="fa-solid fa-bookmark"></i></div><span class="name" onclick="closeModal();openFile(\''+esc(b.path)+'\')">'+esc(b.label)+'<br><small style="color:#94a3b8">'+esc(b.path)+':'+b.line+'</small></span><button class="btn btn-danger" style="padding:4px 8px" onclick="delBookmark(\''+b.id+'\')"><i class="fa-solid fa-trash"></i></button></div>';
    });
    html+='<button class="btn" style="width:100%;margin-top:10px;padding:12px" onclick="closeModal()">Close</button>';
    showModal(html);
  }catch(e){toast("Error","error");}
}
async function delBookmark(id){
  try{
    await fetch("/api/bookmarks/"+encodeURIComponent(PROJECT),{method:"DELETE",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:id})});
    showBookmarks();
  }catch(e){}
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
    var r=await fetch("/api/run-command",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({project:PROJECT,cmd:cmd})});
    var d=await r.json();
    if(d.stdout)out.innerText+=d.stdout;
    if(d.stderr)out.innerText+="\n[stderr]\n"+d.stderr;
    if(d.error)out.innerText+="\n[error] "+d.error;
    out.innerText+="\n[exit "+(d.returncode!=null?d.returncode:"?")+"]\n";
    out.scrollTop=out.scrollHeight;
  }catch(e){out.innerText+="\n[error] "+e+"\n";}
}
async function loadPresets(){
  try{
    var r=await fetch("/api/preset-commands");var d=await r.json();
    PRESETS=d.commands||[];
    var box=document.getElementById("presetBox");
    box.innerHTML="";
    PRESETS.forEach(function(c){
      var b=document.createElement("button");
      b.innerHTML='<i class="fa-solid '+c.icon+'"></i><span>'+esc(c.name)+'</span>';
      b.onclick=function(){document.getElementById("cmd").value=c.cmd;runCmd();};
      box.appendChild(b);
    });
  }catch(e){}
}
async function showSavedCommands(){
  try{
    var r=await fetch("/api/saved-commands");var d=await r.json();
    var html='<h3><i class="fa-solid fa-star"></i> Saved Commands</h3>';
    if(!d.items||!d.items.length)html+='<div class="empty">No saved commands</div>';
    else d.items.forEach(function(c){
      html+='<div class="file-item file"><div class="icon-wrap"><i class="fa-solid fa-bolt"></i></div><span class="name" style="font-family:monospace">'+esc(c)+'</span><button class="btn btn-success" style="padding:5px 9px" onclick="closeModal();switchPanel(\'terminal\');document.getElementById(\'cmd\').value=\''+esc(c).replace(/'/g,"\\'")+'\';runCmd()"><i class="fa-solid fa-play"></i></button><button class="btn btn-danger" style="padding:5px 9px" onclick="delSavedCmd(\''+esc(c).replace(/'/g,"\\'")+'\')"><i class="fa-solid fa-trash"></i></button></div>';
    });
    html+='<button class="btn btn-success" style="width:100%;margin-top:8px;padding:11px" onclick="saveCurrentCmd()">+ Save Current</button><button class="btn" style="width:100%;margin-top:6px;padding:11px" onclick="closeModal()">Close</button>';
    showModal(html);
  }catch(e){toast("Error","error");}
}
async function saveCurrentCmd(){
  var cmd=prompt("Command to save:");if(!cmd)return;
  try{await fetch("/api/saved-commands",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({cmd:cmd})});toast("Saved");}catch(e){toast("Error","error");}
}
async function delSavedCmd(cmd){
  try{await fetch("/api/saved-commands",{method:"DELETE",headers:{"Content-Type":"application/json"},body:JSON.stringify({cmd:cmd})});showSavedCommands();}catch(e){}
}
async function showAliases(){
  try{
    var r=await fetch("/api/aliases");var d=await r.json();
    var html='<h3><i class="fa-solid fa-tag"></i> Command Aliases</h3>';
    Object.keys(d.aliases||{}).forEach(function(k){
      html+='<div class="file-item file"><div class="icon-wrap"><i class="fa-solid fa-tag"></i></div><span class="name"><b>'+esc(k)+'</b> → <code style="color:#4ade80">'+esc(d.aliases[k])+'</code></span><button class="btn btn-danger" style="padding:5px 9px" onclick="delAlias(\''+esc(k)+'\')"><i class="fa-solid fa-trash"></i></button></div>';
    });
    html+='<input id="aliasKey" placeholder="alias name (e.g. upd)" style="margin-top:10px"><input id="aliasCmd" placeholder="command (e.g. pkg update -y)"><button class="btn btn-success" style="width:100%;padding:11px" onclick="addAlias()">+ Add Alias</button><button class="btn" style="width:100%;margin-top:6px;padding:11px" onclick="closeModal()">Close</button>';
    showModal(html);
  }catch(e){toast("Error","error");}
}
async function addAlias(){
  var k=document.getElementById("aliasKey").value.trim();
  var c=document.getElementById("aliasCmd").value.trim();
  if(!k||!c){toast("Fill both","error");return;}
  try{
    var r=await fetch("/api/aliases",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({key:k,cmd:c})});
    var d=await r.json();
    if(r.ok){toast("Added");showAliases();}else toast(d.error||"Fail","error");
  }catch(e){toast("Error","error");}
}
async function delAlias(k){
  try{await fetch("/api/aliases",{method:"DELETE",headers:{"Content-Type":"application/json"},body:JSON.stringify({key:k})});showAliases();}catch(e){}
}

// ============ PTY ============
async function startPTY(){
  if(ptySid){toast("PTY already running");return;}
  try{
    var r=await fetch("/api/pty/start",{method:"POST"});
    var d=await r.json();
    if(!r.ok){toast(d.error||"PTY failed","error");return;}
    ptySid=d.session;ptyLastIdx=0;
    document.getElementById("ptyBox").style.display="block";
    document.getElementById("terminal-output").style.display="none";
    document.getElementById("cmd-input").style.display="none";
    if(ptyTimer)clearInterval(ptyTimer);
    ptyTimer=setInterval(ptyPoll,300);
    toast("PTY started");
  }catch(e){toast("Error: "+e,"error");}
}
async function ptyPoll(){
  if(!ptySid)return;
  try{
    var r=await fetch("/api/pty/output/"+ptySid+"?since="+ptyLastIdx);
    var d=await r.json();
    if(d.output){
      var out=document.getElementById("ptyOutput");
      out.textContent+=d.output;
      out.scrollTop=out.scrollHeight;
      ptyLastIdx=d.total;
    }
  }catch(e){}
}
async function ptySend(){
  if(!ptySid)return;
  var inp=document.getElementById("ptyInput");
  var text=inp.value+"\n";
  inp.value="";
  try{await fetch("/api/pty/input/"+ptySid,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:text})});}catch(e){}
}
function ptyKey(e){if(e.key==="Enter"){e.preventDefault();ptySend();}}
async function stopPTY(){
  if(!ptySid)return;
  if(ptyTimer)clearInterval(ptyTimer);ptyTimer=null;
  try{await fetch("/api/pty/stop/"+ptySid,{method:"POST"});}catch(e){}
  ptySid=null;
  document.getElementById("ptyBox").style.display="none";
  document.getElementById("terminal-output").style.display="block";
  document.getElementById("cmd-input").style.display="flex";
  toast("PTY stopped");
}

// ============ SYSTEM INFO ============
async function loadSystemInfo(){
  try{
    var r=await fetch("/api/system-info");var d=await r.json();
    var mem=d.MemTotal?(parseInt(d.MemTotal)/1024/1024).toFixed(1)+" GB":"?";
    var avail=d.MemAvailable?(parseInt(d.MemAvailable)/1024/1024).toFixed(1)+" GB":"?";
    var pct=d.MemTotal?Math.round((1-parseInt(d.MemAvailable)/parseInt(d.MemTotal))*100):0;
    document.getElementById("sysInfo").innerHTML=
      '<div class="stat-row"><span><i class="fa-solid fa-memory"></i> RAM</span><b>'+avail+' / '+mem+' ('+pct+'%)</b></div>'+
      '<div class="stat-row"><span><i class="fa-solid fa-hdd"></i> Disk</span><b>'+(d.disk_free||"?")+' / '+(d.disk_total||"?")+'</b></div>'+
      '<div class="stat-row"><span><i class="fa-solid fa-clock"></i> Uptime</span><b>'+(d.uptime||"?")+'</b></div>'+
      '<div class="stat-row"><span><i class="fa-brands fa-python"></i> Python</span><b>'+(d.python||"?")+'</b></div>'+
      '<div class="stat-row"><span><i class="fa-solid fa-microchip"></i> Arch</span><b>'+(d.machine||"?")+'</b></div>';
  }catch(e){document.getElementById("sysInfo").innerText="Unavailable";}
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
    var r=await fetch("/api/run-code",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({project:PROJECT,path:path})});
    var d=await r.json();
    document.getElementById("run-info").innerHTML='<i class="fa-solid fa-play"></i> <b>'+esc(path)+'</b> | '+esc(d.language||"?")+' | exit '+(d.returncode!=null?d.returncode:"?");
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
  box.innerHTML='<p style="text-align:center;color:#64748b;padding:30px"><i class="fa-solid fa-spinner fa-spin"></i></p>';
  try{
    if(previewMode==="html"){
      var candidates=["index.html","app/src/main/assets/index.html","public/index.html"];
      for(var i=0;i<candidates.length;i++){
        var r=await fetch("/api/file-content/"+encodeURIComponent(PROJECT)+"?path="+encodeURIComponent(candidates[i]));
        if(r.ok){var d=await r.json();box.innerHTML='<iframe style="width:100%;height:440px;border:0;background:#fff;border-radius:8px" srcdoc="'+d.content.replace(/"/g,"&quot;")+'"></iframe>';return;}
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
  if(tag==="ListView")return '<div style="background:#1e293b;border-radius:8px;padding:8px;color:#cbd5e1">List: item 1, item 2...</div>';
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
function formatTime(sec){sec=Math.floor(sec);if(sec<60)return sec+"s";return Math.floor(sec/60)+"m "+(sec%60)+"s";}
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
  if(line.indexOf("BUILD SUCCESSFUL")>=0)cls="color:#4ade80";
  else if(line.indexOf("BUILD FAILED")>=0||line.indexOf("error:")>=0)cls="color:#f87171";
  else if(line.indexOf("> Task")>=0)cls="color:#fbbf24";
  else if(line.indexOf("💡 Hint:")>=0)cls="color:#fbbf24;font-weight:600";
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
  if(line.indexOf("BUILD SUCCESSFUL")>=0){
    document.getElementById("buildProgressBar").style.width="100%";
    document.getElementById("buildProgressText").innerText="100%";
    document.getElementById("currentTask").innerHTML='<i class="fa-solid fa-circle-check" style="color:#4ade80"></i> Build complete';
  }
  if(line.indexOf("BUILD FAILED")>=0)
    document.getElementById("currentTask").innerHTML='<i class="fa-solid fa-circle-xmark" style="color:#f87171"></i> Build failed';
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
        document.getElementById("currentTask").innerHTML='<i class="fa-solid fa-circle-check" style="color:#4ade80"></i> Build successful';
        document.getElementById("buildStatusMsg").innerHTML='✓ APK ready!';
        document.getElementById("buildStatusMsg").style.color="#4ade80";
        document.getElementById("apk-box").style.display="block";
        document.getElementById("apkDownloadBtn").onclick=function(){location.href="/api/download-apk/"+encodeURIComponent(PROJECT);};
        toast("APK Ready!");
        try{if(Notification.permission==="granted")new Notification("Zihad IDE","✅ Build successful!");}catch(e){}
      }else{
        document.getElementById("currentTask").innerHTML='<i class="fa-solid fa-circle-xmark" style="color:#f87171"></i> Build failed';
        document.getElementById("buildStatusMsg").innerText="✗ Failed";
        document.getElementById("buildStatusMsg").style.color="#f87171";
        toast("Build failed","error");
      }
    }
  }catch(e){}
}
async function buildApk(){
  if(!confirm("Build APK?"))return;
  switchPanel("build");
  document.getElementById("buildLog").innerHTML="$ Starting build...";
  document.getElementById("buildProgressBar").style.width="0%";
  document.getElementById("buildProgressText").innerText="0%";
  document.getElementById("currentTask").innerHTML='<i class="fa-solid fa-spinner fa-spin"></i> Starting...';
  document.getElementById("buildStatusMsg").innerText="Starting...";
  document.getElementById("buildStatusMsg").style.color="#94a3b8";
  document.getElementById("apk-box").style.display="none";
  tasksSeen=0;lastLineIdx=0;EST_TOTAL=32;
  try{
    try{if(Notification.permission==="default")await Notification.requestPermission();}catch(e){}
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
async function toggleAutoBuild(on){
  try{
    await fetch("/api/settings/"+encodeURIComponent(PROJECT),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({autoBuild:on})});
    toast(on?"Auto-build ON":"Auto-build OFF");
  }catch(e){}
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
  if(!confirm(deep?"Deep clean (also ~/.gradle)?" : "Clean build dirs?"))return;
  try{
    var r=await fetch("/api/cache-clean",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({project:PROJECT,deep:deep})});
    var d=await r.json();
    if(r.ok)toast("Cleaned: "+((d.cleared||[]).join(", ")||"nothing"));
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
      if(!d.success)toast("Init failed","error");else toast("Git initialized");
      return;
    }
    if(a==="status"){
      var r=await fetch("/api/git/status/"+encodeURIComponent(PROJECT));
      var d=await r.json();
      document.getElementById("gitInfo").innerHTML='<i class="fa-brands fa-git-alt"></i> Branch: '+(d.branch||"?")+' | '+(d.init?"initialized":"not initialized");
      if(!d.init){gitLog("Repository not initialized. Tap Init.");return;}
      if(!d.files||!d.files.length){gitLog("✓ Working tree clean","#4ade80");return;}
      gitLog("Modified:\n"+d.files.join("\n"));
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
      gitLog(d.log.length?d.log.join("\n"):"No commits");
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

// ============ NOTIFICATIONS ============
async function pollNotifications(){
  try{
    var r=await fetch("/api/notifications?since="+notifLastSeen);
    var d=await r.json();
    if(d.new&&d.new.length){
      d.new.forEach(function(n){
        if(n.ts>notifLastSeen){
          notifLastSeen=n.ts;
          if(n.kind==="error")toast(n.title+" — "+n.body,"error");
          else if(n.kind==="success")toast(n.title+" — "+n.body,"success");
        }
      });
    }
    var btn=document.getElementById("notifBtn");
    btn.dataset.count=d.unread||0;
  }catch(e){}
}
async function showNotifications(){
  try{
    var r=await fetch("/api/notifications");var d=await r.json();
    var html='<h3><i class="fa-solid fa-bell"></i> Notifications</h3>';
    if(!d.items||!d.items.length)html+='<div class="empty">No notifications</div>';
    else{
      html+='<div style="max-height:400px;overflow-y:auto">';
      d.items.forEach(function(n){
        var when=new Date(n.ts*1000).toLocaleString();
        html+='<div class="notif-item '+(n.kind||"info")+'"><div class="ttl">'+esc(n.title)+'</div><div class="bdy">'+esc(n.body)+'</div><div class="time">'+when+'</div></div>';
      });
      html+='</div>';
    }
    html+='<div style="display:flex;gap:6px;margin-top:8px"><button class="btn btn-primary" style="flex:1;padding:11px" onclick="markNotifsRead()">Mark Read</button><button class="btn btn-danger" style="flex:1;padding:11px" onclick="clearNotifs()">Clear</button><button class="btn" style="padding:11px" onclick="closeModal()">Close</button></div>';
    showModal(html);
    fetch("/api/notifications/read",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({})}).then(function(){pollNotifications();});
  }catch(e){toast("Error","error");}
}
async function markNotifsRead(){try{await fetch("/api/notifications/read",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({})});closeModal();pollNotifications();}catch(e){}}
async function clearNotifs(){try{await fetch("/api/notifications/clear",{method:"POST"});closeModal();pollNotifications();}catch(e){}}

// ============ KANBAN ============
async function loadKanban(){
  try{
    var r=await fetch("/api/kanban/"+encodeURIComponent(PROJECT));
    var d=await r.json();
    var board=document.getElementById("kanbanBoard");
    var cols=[{id:"todo",name:"📋 Todo"},{id:"doing",name:"⚙️ Doing"},{id:"done",name:"✅ Done"}];
    board.innerHTML="";
    cols.forEach(function(col){
      var cards=d.columns&&d.columns[col.id]?d.columns[col.id]:[];
      var html='<div class="kanban-col"><h4>'+col.name+' <span class="badge info">'+cards.length+'</span></h4>';
      cards.forEach(function(c){
        var priClass=c.priority==="high"?"p-high":c.priority==="low"?"p-low":"";
        var nextCol=col.id==="todo"?"doing":col.id==="doing"?"done":"todo";
        html+='<div class="kanban-card '+priClass+'">'+esc(c.text)+
          '<span class="del" onclick="kanbanDel(\''+col.id+'\',\''+c.id+'\')"><i class="fa-solid fa-xmark"></i></span>'+
          '<div style="margin-top:5px;font-size:10px"><a onclick="kanbanMove(\''+col.id+'\',\''+nextCol+'\',\''+c.id+'\')" style="color:#60a5fa;cursor:pointer"><i class="fa-solid fa-arrow-right"></i> '+nextCol+'</a></div>'+
          '</div>';
      });
      html+='</div>';
      board.insertAdjacentHTML("beforeend",html);
    });
  }catch(e){document.getElementById("kanbanBoard").innerText="Error";}
}
async function kanbanAdd(){
  var text=document.getElementById("kanbanInput").value.trim();
  var priority=document.getElementById("kanbanPriority").value;
  if(!text)return;
  try{
    var r=await fetch("/api/kanban/"+encodeURIComponent(PROJECT)+"/add",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:text,column:"todo",priority:priority})});
    document.getElementById("kanbanInput").value="";
    loadKanban();
  }catch(e){}
}
async function kanbanMove(from,to,id){
  try{
    var r=await fetch("/api/kanban/"+encodeURIComponent(PROJECT)+"/move",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({from:from,to:to,id:id})});
    loadKanban();
  }catch(e){}
}
async function kanbanDel(col,id){
  if(!confirm("Delete?"))return;
  try{
    var r=await fetch("/api/kanban/"+encodeURIComponent(PROJECT)+"/del",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({column:col,id:id})});
    loadKanban();
  }catch(e){}
}

// ============ NOTES ============
async function loadNotes(){
  try{
    var r=await fetch("/api/notes/"+encodeURIComponent(PROJECT));
    var d=await r.json();
    document.getElementById("notesArea").value=d.content||"";
  }catch(e){}
}
async function saveNotes(){
  var content=document.getElementById("notesArea").value;
  try{
    await fetch("/api/notes/"+encodeURIComponent(PROJECT),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({content:content})});
    toast("Notes saved");
  }catch(e){toast("Error","error");}
}

// ============ ANALYTICS ============
async function loadAnalytics(){
  try{
    var r=await fetch("/api/build-chart/"+encodeURIComponent(PROJECT));
    var d=await r.json();
    var chart=d.chart||[];
    var maxDur=Math.max.apply(null,chart.map(function(x){return x.duration||0;}))||1;
    var html="";
    chart.slice(0,20).reverse().forEach(function(x){
      var h=Math.max(4,Math.round((x.duration/maxDur)*90));
      var cls=x.success?"ok":"fail";
      html+='<div class="chart-col '+cls+'" style="height:'+h+'px" title="'+x.duration.toFixed(1)+'s"></div>';
    });
    document.getElementById("buildTimeChart").innerHTML=html||'<div class="empty" style="width:100%">No builds yet</div>';
  }catch(e){}
  try{
    var r2=await fetch("/api/apk-size-graph/"+encodeURIComponent(PROJECT));
    var d2=await r2.json();
    var pts=d2.points||[];
    var maxSize=Math.max.apply(null,pts.map(function(x){return x.size||0;}))||1;
    var html2="";
    pts.slice(0,20).reverse().forEach(function(x){
      var h=Math.max(4,Math.round((x.size/maxSize)*90));
      html2+='<div class="chart-col" style="height:'+h+'px" title="'+Math.round(x.size/1024)+' KB"></div>';
    });
    document.getElementById("apkSizeChart").innerHTML=html2||'<div class="empty" style="width:100%">No data</div>';
  }catch(e){}
  try{
    var r3=await fetch("/api/error-frequency/"+encodeURIComponent(PROJECT));
    var d3=await r3.json();
    var freq=d3.freq||{};
    var keys=Object.keys(freq).sort(function(a,b){return freq[b]-freq[a];}).slice(0,20);
    var html3="";
    if(!keys.length)html3='<div class="empty">No errors recorded</div>';
    keys.forEach(function(k){
      var pct=Math.min(100,Math.round((freq[k]/Math.max.apply(null,Object.values(freq)))*100));
      html3+='<div style="margin-bottom:8px"><div style="font-size:11px;font-family:monospace;color:#fca5a5;margin-bottom:3px">'+esc(k.slice(0,80))+' <span style="color:#94a3b8">× '+freq[k]+'</span></div><div class="chart-bar" style="height:6px"><div style="width:'+pct+'%;height:100%;background:linear-gradient(90deg,#ef4444,#dc2626);border-radius:3px"></div></div></div>';
    });
    document.getElementById("errFreqList").innerHTML=html3;
  }catch(e){}
}

// ============ MORE MENU TOOLS ============
function showMoreMenu(){document.getElementById("moreModal").classList.add("show");}
function openPkgRename(){
  showModal('<h3><i class="fa-solid fa-box"></i> Rename Package</h3><input id="oldPkg" placeholder="Old package"><input id="newPkg" placeholder="New package"><button class="btn btn-primary" style="width:100%;padding:12px;margin-top:8px" onclick="doPkgRename()">Update All</button><button class="btn" style="width:100%;margin-top:6px;padding:12px" onclick="closeModal()">Cancel</button>');
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
    window._strItems=d.items||[];
    renderStringsModal();
  }catch(e){toast("Error","error");}
}
function renderStringsModal(){
  var items=window._strItems;
  var html='<h3><i class="fa-solid fa-language"></i> Strings Editor</h3><div style="max-height:300px;overflow-y:auto">';
  items.forEach(function(it,i){
    html+='<div style="display:flex;gap:6px;margin:4px 0"><input value="'+esc(it.name)+'" placeholder="key" style="flex:1" onchange="strUpdate('+i+',this.value,\'name\')"><input value="'+esc(it.value)+'" placeholder="value" style="flex:2" onchange="strUpdate('+i+',this.value,\'value\')"><button class="btn btn-danger" style="padding:6px" onclick="strDel('+i+')"><i class="fa-solid fa-trash"></i></button></div>';
  });
  html+='</div><button class="btn btn-success" style="width:100%;margin-top:8px;padding:10px" onclick="strAdd()">+ Add</button><button class="btn btn-primary" style="width:100%;margin-top:6px;padding:12px" onclick="strSave()">💾 Save</button><button class="btn" style="width:100%;margin-top:6px;padding:12px" onclick="closeModal()">Cancel</button>';
  showModal(html);
}
function strUpdate(i,v,k){window._strItems[i][k]=v;}
function strDel(i){window._strItems.splice(i,1);renderStringsModal();}
function strAdd(){window._strItems.push({name:"new_string",value:""});renderStringsModal();}
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
    window._themeColors=d.colors||[];
    renderThemeModal();
  }catch(e){toast("Error","error");}
}
function renderThemeModal(){
  var html='<h3><i class="fa-solid fa-brush"></i> Theme Builder</h3><div style="max-height:300px;overflow-y:auto">';
  window._themeColors.forEach(function(c,i){
    html+='<div style="display:flex;gap:6px;margin:4px 0;align-items:center"><input value="'+esc(c.name)+'" placeholder="name" style="flex:1" onchange="thmUpdate('+i+',this.value,\'name\')"><input type="color" value="'+esc(c.value)+'" style="width:50px;height:40px;padding:2px" onchange="thmUpdate('+i+',this.value,\'value\')"><input value="'+esc(c.value)+'" style="flex:1" onchange="thmUpdate('+i+',this.value,\'value\')"><button class="btn btn-danger" style="padding:6px" onclick="thmDel('+i+')"><i class="fa-solid fa-trash"></i></button></div>';
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
    var html='<h3><i class="fa-solid fa-file-code"></i> Manifest Editor</h3>';
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
  showModal('<h3><i class="fa-solid fa-image"></i> Icon Generator</h3><p style="font-size:12px;color:#94a3b8">Upload square PNG. Auto-generates all mipmaps.</p><input type="file" id="iconFile" accept="image/*" style="padding:8px;background:transparent;color:#fff"><button class="btn btn-primary" style="width:100%;margin-top:8px;padding:12px" onclick="doIconGen()">🚀 Generate</button><button class="btn" style="width:100%;margin-top:6px;padding:12px" onclick="closeModal()">Cancel</button>');
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
  var html='<h3><i class="fa-solid fa-key"></i> ENV Manager</h3><p style="font-size:11px;color:#94a3b8">Written to .env file</p>';
  window._envItems.forEach(function(it,i){
    html+='<div style="display:flex;gap:6px;margin:4px 0"><input value="'+esc(it.key)+'" placeholder="KEY" style="flex:1" onchange="envUpdate('+i+',this.value,\'key\')"><input value="'+esc(it.value)+'" placeholder="value" style="flex:2" onchange="envUpdate('+i+',this.value,\'value\')"><button class="btn btn-danger" style="padding:6px" onclick="envDel('+i+')"><i class="fa-solid fa-trash"></i></button></div>';
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
  showModal('<h3><i class="fa-solid fa-i-cursor"></i> Bulk Rename</h3><input id="bulkPattern" placeholder="Regex e.g. old_(.*)"><input id="bulkReplace" placeholder="Replace e.g. new_\\1"><input id="bulkExt" placeholder="Extension filter (optional)"><button class="btn btn-primary" style="width:100%;margin-top:8px;padding:12px" onclick="doBulkRename()">🚀 Rename</button><button class="btn" style="width:100%;margin-top:6px;padding:12px" onclick="closeModal()">Cancel</button>');
}
async function doBulkRename(){
  var p=document.getElementById("bulkPattern").value;
  var r=document.getElementById("bulkReplace").value;
  var e=document.getElementById("bulkExt").value;
  if(!p){toast("Pattern required","error");return;}
  if(!confirm("Rename matching files?"))return;
  try{
    var res=await fetch("/api/bulk-rename",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({project:PROJECT,pattern:p,replace:r,ext:e})});
    var d=await res.json();
    if(res.ok){toast("Renamed "+d.renamed);closeModal();loadFiles(currentPath);}
    else toast(d.error||"Fail","error");
  }catch(err){toast("Error","error");}
}
function openFirebase(){
  showModal('<h3><i class="fa-solid fa-fire"></i> Firebase Inject</h3><p style="font-size:12px;color:#94a3b8">Paste google-services.json:</p><textarea id="fbJson" style="height:220px;font-family:monospace;font-size:11px" placeholder=\'{"project_info":{...}}\'></textarea><button class="btn btn-primary" style="width:100%;margin-top:8px;padding:12px" onclick="doFirebase()">🚀 Inject</button><button class="btn" style="width:100%;margin-top:6px;padding:12px" onclick="closeModal()">Cancel</button>');
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
  showModal('<h3><i class="fa-solid fa-lock"></i> Keystore Config</h3><input id="ksFile" placeholder="Keystore file path"><input id="ksPass" placeholder="Store password" type="password"><input id="ksAlias" placeholder="Key alias"><input id="ksKeyPass" placeholder="Key password" type="password"><button class="btn btn-primary" style="width:100%;margin-top:8px;padding:12px" onclick="saveKs()">💾 Save</button><button class="btn" style="width:100%;margin-top:6px;padding:12px" onclick="closeModal()">Cancel</button>');
  fetch("/api/keystore").then(function(r){return r.json();}).then(function(d){
    if(d.storeFile)document.getElementById("ksFile").value=d.storeFile;
    if(d.keyAlias)document.getElementById("ksAlias").value=d.keyAlias;
  });
}
async function saveKs(){
  var data={storeFile:document.getElementById("ksFile").value,storePassword:document.getElementById("ksPass").value,keyAlias:document.getElementById("ksAlias").value||"release",keyPassword:document.getElementById("ksKeyPass").value};
  try{
    var r=await fetch("/api/keystore",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});
    if(r.ok){toast("Saved");closeModal();}
  }catch(e){toast("Error","error");}
}
async function signRelease(){
  if(!confirm("Build + sign release APK?"))return;
  toast("Building release...");
  try{
    var r=await fetch("/api/sign-release/"+encodeURIComponent(PROJECT),{method:"POST"});
    var d=await r.json();
    if(r.ok){toast("Signed!");location.href=d.download;}
    else toast(d.error||"Fail","error");
  }catch(e){toast("Error","error");}
}
function openRestore(){
  showModal('<h3><i class="fa-solid fa-download"></i> Restore Backup</h3><p style="font-size:12px;color:#94a3b8">Select a ZIP backup file.</p><input type="file" id="restoreFile" accept=".zip" style="padding:8px;background:transparent;color:#fff"><button class="btn btn-primary" style="width:100%;margin-top:8px;padding:12px" onclick="doRestore()">🚀 Restore</button><button class="btn" style="width:100%;margin-top:6px;padding:12px" onclick="closeModal()">Cancel</button>');
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
  showModal('<h3><i class="fa-solid fa-keyboard"></i> Shortcuts</h3><div style="font-size:13px;line-height:2;color:#cbd5e1"><b>Ctrl+S</b> Save<br><b>Ctrl+B</b> Build<br><b>Ctrl+Shift+P</b> Command Palette<br><b>Ctrl+F</b> Find<br><b>Ctrl+Z</b> Undo<br><b>Ctrl+Y</b> Redo<br></div><button class="btn" style="width:100%;margin-top:10px;padding:12px" onclick="closeModal()">Close</button>');
}

// ============ DEV TOOLS ============
function openDevTools(){
  var html='<h3><i class="fa-solid fa-toolbox"></i> Dev Tools</h3><div class="devtool-grid">';
  html+='<div class="devtool-item" onclick="toolHash()"><i class="fa-solid fa-fingerprint"></i>Hash</div>';
  html+='<div class="devtool-item" onclick="toolBase64()"><i class="fa-solid fa-code"></i>Base64</div>';
  html+='<div class="devtool-item" onclick="toolUUID()"><i class="fa-solid fa-id-card"></i>UUID</div>';
  html+='<div class="devtool-item" onclick="toolLorem()"><i class="fa-solid fa-paragraph"></i>Lorem</div>';
  html+='<div class="devtool-item" onclick="toolJSON()"><i class="fa-solid fa-brackets-curly"></i>JSON</div>';
  html+='<div class="devtool-item" onclick="toolColorPicker()"><i class="fa-solid fa-palette"></i>Color</div>';
  html+='<div class="devtool-item" onclick="showProcs()"><i class="fa-solid fa-list-check"></i>Processes</div>';
  html+='</div><div id="toolOutput" style="margin-top:10px"></div><button class="btn" style="width:100%;margin-top:10px;padding:12px" onclick="closeModal()">Close</button>';
  showModal(html);
}
async function toolHash(){
  var t=prompt("Text to hash:");if(!t)return;
  var r=await fetch("/api/devtool/hash",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:t,algo:"sha256"})});
  var d=await r.json();
  document.getElementById("toolOutput").innerHTML='<div style="font-family:monospace;font-size:11px;word-break:break-all;padding:10px;background:#000;border-radius:10px;color:#4ade80">SHA256:<br>'+esc(d.result||d.error)+'</div>';
}
async function toolBase64(){
  var t=prompt("Text:");if(!t)return;
  var r=await fetch("/api/devtool/base64",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:t,mode:"encode"})});
  var d=await r.json();
  document.getElementById("toolOutput").innerHTML='<div style="font-family:monospace;font-size:11px;word-break:break-all;padding:10px;background:#000;border-radius:10px;color:#4ade80">'+esc(d.result||d.error)+'</div>';
}
async function toolUUID(){
  var r=await fetch("/api/devtool/uuid");var d=await r.json();
  document.getElementById("toolOutput").innerHTML='<div style="font-family:monospace;font-size:11px;padding:10px;background:#000;border-radius:10px;color:#4ade80">'+esc(d.uuid)+'</div>';
}
async function toolLorem(){
  var r=await fetch("/api/devtool/lorem?n=3");var d=await r.json();
  document.getElementById("toolOutput").innerHTML='<textarea style="height:150px">'+esc(d.text)+'</textarea>';
}
function toolJSON(){
  document.getElementById("toolOutput").innerHTML='<textarea id="jsonIO" placeholder="Paste JSON..." style="height:120px"></textarea><button class="btn btn-primary" style="width:100%;margin-top:6px;padding:10px" onclick="formatJSON()">Format</button>';
}
function formatJSON(){
  try{var v=document.getElementById("jsonIO").value;var p=JSON.parse(v);document.getElementById("jsonIO").value=JSON.stringify(p,null,2);}
  catch(e){alert("Invalid: "+e.message);}
}
function toolColorPicker(){
  document.getElementById("toolOutput").innerHTML='<input type="color" id="clrPkr" style="width:100%;height:60px" oninput="document.getElementById(\'clrTxt\').innerText=this.value"><div id="clrTxt" style="text-align:center;font-family:monospace;padding:8px;color:#4ade80">#000000</div>';
}
async function showProcs(){
  var r=await fetch("/api/proc-list");var d=await r.json();
  var html='<div style="max-height:340px;overflow-y:auto;font-family:monospace;font-size:11px;background:#000;padding:10px;border-radius:10px;color:#4ade80">';
  (d.procs||[]).forEach(function(l){html+=esc(l)+"<br>";});
  html+='</div>';
  document.getElementById("toolOutput").innerHTML=html;
}

// ============ SNIPPETS ============
async function openSnippets(){
  try{
    var r=await fetch("/api/snippets");var d=await r.json();
    var html='<h3><i class="fa-solid fa-scissors"></i> Code Snippets</h3><div style="max-height:300px;overflow-y:auto">';
    if(!d.items||!d.items.length)html+='<div class="empty">No snippets</div>';
    else d.items.forEach(function(s,i){
      html+='<div style="background:#0b1220;padding:8px;border-radius:8px;margin:4px 0;display:flex;gap:6px;align-items:center"><b style="color:#60a5fa;flex:1;font-size:12px">'+esc(s.name)+' <small style="color:#94a3b8">['+esc(s.lang)+']</small></b><button class="btn btn-success" style="padding:4px 8px" onclick="insertSnippet(\''+esc(s.code).replace(/'/g,"\\'").replace(/\n/g,"\\n")+'\')"><i class="fa-solid fa-plus"></i></button><button class="btn btn-danger" style="padding:4px 8px" onclick="delSnippet('+i+')"><i class="fa-solid fa-trash"></i></button></div>';
    });
    html+='</div><button class="btn btn-success" style="width:100%;margin-top:8px;padding:11px" onclick="addSnippet()">+ New Snippet</button><button class="btn" style="width:100%;margin-top:6px;padding:11px" onclick="closeModal()">Close</button>';
    showModal(html);
  }catch(e){}
}
function insertSnippet(code){if(!cm)return toast("Open a file first","error");cm.replaceSelection(code);closeModal();}
async function addSnippet(){
  var name=prompt("Name:");if(!name)return;
  var lang=prompt("Language:","java")||"text";
  var code=prompt("Code:");if(!code)return;
  await fetch("/api/snippets",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:name,lang:lang,code:code})});
  openSnippets();
}
async function delSnippet(i){await fetch("/api/snippets",{method:"DELETE",headers:{"Content-Type":"application/json"},body:JSON.stringify({index:i})});openSnippets();}

// ============ MACROS ============
async function openMacros(){
  try{
    var r=await fetch("/api/macros");var d=await r.json();
    var html='<h3><i class="fa-solid fa-record-vinyl"></i> Macros</h3>';
    (d.macros||[]).forEach(function(m){
      html+='<div class="file-item file"><div class="icon-wrap"><i class="fa-solid fa-play"></i></div><span class="name">'+esc(m.name)+' <small style="color:#94a3b8">'+m.steps.length+' steps</small></span><button class="btn btn-success" style="padding:5px 9px" onclick="runMacro(\''+m.id+'\')"><i class="fa-solid fa-play"></i></button><button class="btn btn-danger" style="padding:5px 9px" onclick="delMacro(\''+m.id+'\')"><i class="fa-solid fa-trash"></i></button></div>';
    });
    html+='<button class="btn btn-success" style="width:100%;margin-top:8px;padding:11px" onclick="createMacro()">+ Record Macro</button><button class="btn" style="width:100%;margin-top:6px;padding:11px" onclick="closeModal()">Close</button>';
    showModal(html);
  }catch(e){}
}
async function createMacro(){
  var name=prompt("Macro name:");if(!name)return;
  var cmd=prompt("Step 1: shell command:");if(!cmd)return;
  var steps=[{type:"cmd",value:cmd}];
  if(confirm("Add build step?"))steps.push({type:"build"});
  await fetch("/api/macros",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:name,steps:steps})});
  openMacros();
}
async function runMacro(id){
  try{
    var r=await fetch("/api/macros/run/"+id,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({project:PROJECT})});
    var d=await r.json();
    if(r.ok)toast("Macro executed");else toast(d.error||"Fail","error");
    closeModal();
  }catch(e){toast("Error","error");}
}
async function delMacro(id){await fetch("/api/macros",{method:"DELETE",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:id})});openMacros();}

// ============ CUSTOM THEMES ============
async function openCustomThemes(){
  try{
    var r=await fetch("/api/themes");var d=await r.json();
    var html='<h3><i class="fa-solid fa-palette"></i> Custom Themes</h3>';
    (d.themes||[]).forEach(function(t){
      html+='<div class="file-item file"><div class="icon-wrap" style="background:'+(t.colors.primary||"#3b82f6")+'"></div><span class="name">'+esc(t.name)+'</span><button class="btn btn-success" style="padding:5px 9px" onclick="applyTheme(\''+t.id+'\')"><i class="fa-solid fa-check"></i></button><button class="btn btn-danger" style="padding:5px 9px" onclick="delTheme(\''+t.id+'\')"><i class="fa-solid fa-trash"></i></button></div>';
    });
    html+='<input id="themeName" placeholder="Theme name"><input type="color" id="themePrimary" value="#3b82f6" style="width:100%;height:44px;padding:4px"><button class="btn btn-success" style="width:100%;padding:11px" onclick="createTheme()">+ Create Theme</button><button class="btn" style="width:100%;margin-top:6px;padding:11px" onclick="closeModal()">Close</button>';
    window._customThemes=d.themes||[];
    showModal(html);
  }catch(e){}
}
async function createTheme(){
  var name=document.getElementById("themeName").value.trim();
  var primary=document.getElementById("themePrimary").value;
  if(!name)return;
  await fetch("/api/themes",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:name,colors:{primary:primary}})});
  openCustomThemes();
}
function applyTheme(id){
  var t=(window._customThemes||[]).find(function(x){return x.id===id;});
  if(!t)return;
  if(t.colors.primary){document.documentElement.style.setProperty("--primary",t.colors.primary);}
  toast("Theme applied: "+t.name);
}
async function delTheme(id){await fetch("/api/themes/"+id,{method:"DELETE"});openCustomThemes();}

// ============ PLUGINS ============
async function openPlugins(){
  try{
    var r=await fetch("/api/plugins");var d=await r.json();
    var html='<h3><i class="fa-solid fa-puzzle-piece"></i> Plugins</h3>';
    (d.plugins||[]).forEach(function(p){
      html+='<div class="plugin-item"><h5>'+esc(p.name)+' v'+esc(p.version)+'</h5><p>'+esc(p.description||"No description")+'</p><button class="btn btn-danger" style="padding:5px 9px" onclick="delPlugin(\''+esc(p._file)+'\')"><i class="fa-solid fa-trash"></i> Delete</button></div>';
    });
    html+='<input id="pluginName" placeholder="Plugin name"><input id="pluginDesc" placeholder="Description"><textarea id="pluginCode" placeholder="JavaScript code..." style="height:100px"></textarea><button class="btn btn-success" style="width:100%;padding:11px" onclick="createPlugin()">+ Add Plugin</button><button class="btn" style="width:100%;margin-top:6px;padding:11px" onclick="closeModal()">Close</button>';
    showModal(html);
  }catch(e){}
}
async function createPlugin(){
  var name=document.getElementById("pluginName").value.trim();
  var desc=document.getElementById("pluginDesc").value;
  var code=document.getElementById("pluginCode").value;
  if(!name)return;
  await fetch("/api/plugins",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:name,description:desc,code:code})});
  openPlugins();
}
async function delPlugin(f){await fetch("/api/plugins/"+encodeURIComponent(f),{method:"DELETE"});openPlugins();}

// ============ COMMAND PALETTE ============
var PALETTE_CMDS=[
  {name:"Build APK",icon:"fa-hammer",run:buildApk},
  {name:"Run Current File",icon:"fa-play",run:runCurrent},
  {name:"Scan Errors",icon:"fa-magnifying-glass",run:scanAllErrors},
  {name:"Export ZIP",icon:"fa-file-zipper",run:exportZip},
  {name:"ADB Install",icon:"fa-mobile-button",run:adbInstall},
  {name:"Clean Build",icon:"fa-broom",run:function(){cleanBuild(false);}},
  {name:"Deep Clean",icon:"fa-broom",run:function(){cleanBuild(true);}},
  {name:"Git Status",icon:"fa-code-branch",run:function(){switchPanel("git");}},
  {name:"Logcat Start",icon:"fa-list-ul",run:function(){switchPanel("logcat");logcatStart();}},
  {name:"Real PTY Terminal",icon:"fa-terminal",run:function(){switchPanel("terminal");startPTY();}},
  {name:"Kanban Board",icon:"fa-list-check",run:function(){switchPanel("kanban");}},
  {name:"Project Notes",icon:"fa-note-sticky",run:function(){switchPanel("notes");}},
  {name:"Analytics",icon:"fa-chart-line",run:function(){switchPanel("analytics");}},
  {name:"Rename Package",icon:"fa-box",run:openPkgRename},
  {name:"Strings Editor",icon:"fa-language",run:openStrings},
  {name:"Theme Builder",icon:"fa-brush",run:openThemeBuilder},
  {name:"Manifest Editor",icon:"fa-file-code",run:openManifest},
  {name:"Icon Generator",icon:"fa-image",run:openIconGen},
  {name:"ENV Manager",icon:"fa-key",run:openEnvMgr},
  {name:"Bulk Rename",icon:"fa-i-cursor",run:openBulkRename},
  {name:"Firebase Inject",icon:"fa-fire",run:openFirebase},
  {name:"Version Bump",icon:"fa-hashtag",run:bumpVersion},
  {name:"Keystore Config",icon:"fa-lock",run:openKeystore},
  {name:"Sign Release",icon:"fa-certificate",run:signRelease},
  {name:"Dev Tools",icon:"fa-toolbox",run:openDevTools},
  {name:"Snippets",icon:"fa-scissors",run:openSnippets},
  {name:"Macros",icon:"fa-record-vinyl",run:openMacros},
  {name:"Bookmarks",icon:"fa-bookmark",run:showBookmarks},
  {name:"Recent Files",icon:"fa-clock-rotate-left",run:showRecent},
  {name:"Aliases",icon:"fa-tag",run:showAliases},
  {name:"Plugins",icon:"fa-puzzle-piece",run:openPlugins},
  {name:"Custom Themes",icon:"fa-palette",run:openCustomThemes},
  {name:"Settings",icon:"fa-gear",run:openSettings},
  {name:"Toggle HTML/Android Preview",icon:"fa-eye",run:togglePreviewMode},
  {name:"Notifications",icon:"fa-bell",run:showNotifications},
];
var paletteFiltered=PALETTE_CMDS.slice(),paletteIdx=0;
function openCommandPalette(){
  document.getElementById("cmdPalette").classList.add("show");
  document.getElementById("cmdPaletteInput").value="";
  paletteFiltered=PALETTE_CMDS.slice();paletteIdx=0;renderPalette();
  setTimeout(function(){document.getElementById("cmdPaletteInput").focus();},50);
}
function renderPalette(){
  var ul=document.getElementById("cmdPaletteList");ul.innerHTML="";
  paletteFiltered.slice(0,12).forEach(function(c,i){
    var li=document.createElement("li");
    li.innerHTML='<i class="fa-solid '+c.icon+'"></i>'+esc(c.name);
    if(i===paletteIdx)li.classList.add("active");
    li.onclick=function(){closePalette();c.run();};
    ul.appendChild(li);
  });
}
function filterPalette(){
  var q=document.getElementById("cmdPaletteInput").value.toLowerCase();
  paletteFiltered=PALETTE_CMDS.filter(function(c){return c.name.toLowerCase().indexOf(q)>=0;});
  paletteIdx=0;renderPalette();
}
function paletteKey(e){
  if(e.key==="Escape")closePalette();
  else if(e.key==="ArrowDown"){e.preventDefault();if(paletteIdx<paletteFiltered.length-1){paletteIdx++;renderPalette();}}
  else if(e.key==="ArrowUp"){e.preventDefault();if(paletteIdx>0){paletteIdx--;renderPalette();}}
  else if(e.key==="Enter"){e.preventDefault();var c=paletteFiltered[paletteIdx];if(c){closePalette();c.run();}}
}
function closePalette(){document.getElementById("cmdPalette").classList.remove("show");}

// ============ SETTINGS ============
async function openSettings(){
  document.getElementById("fontSize").value=localStorage.getItem("fontSize")||13;
  document.getElementById("autoSave").value=localStorage.getItem("autoSave")||"off";
  document.getElementById("cmTheme").value=localStorage.getItem("cmTheme")||"dracula";
  document.getElementById("uiLang").value=localStorage.getItem("uiLang")||"en";
  document.getElementById("settingsModal").classList.add("show");
  try{
    var r=await fetch("/api/settings/"+encodeURIComponent(PROJECT));
    var d=await r.json();
    if(document.getElementById("autoBuildChk"))document.getElementById("autoBuildChk").checked=!!d.autoBuild;
  }catch(e){}
}
function applyFontSize(v){localStorage.setItem("fontSize",v);if(cm)cm.getWrapperElement().style.fontSize=v+"px";}
function changeTheme(t){localStorage.setItem("cmTheme",t);if(cm)cm.setOption("theme",t);}
function setLang(l){
  localStorage.setItem("uiLang",l);
  var map={en:{explorer:"Files",preview:"Preview",errors:"Errors",terminal:"Term",build:"Build",git:"Git",logcat:"Log",kanban:"Todo",notes:"Notes",analytics:"Stats"},
           bn:{explorer:"ফাইল",preview:"প্রিভিউ",errors:"ভুল",terminal:"টার্ম",build:"বিল্ড",git:"গিট",logcat:"লগ",kanban:"টুডু",notes:"নোট",analytics:"স্ট্যাট"}};
  var m=map[l]||map.en;
  document.querySelectorAll(".nav-item").forEach(function(it){
    var p=it.dataset.panel;
    if(p&&m[p]){var sp=it.querySelector("span");if(sp)sp.textContent=m[p];}
  });
  toast("Language: "+l);
}

// ============ SHORTCUTS ============
document.addEventListener("keydown",function(e){
  if((e.ctrlKey||e.metaKey)&&e.shiftKey&&e.key.toLowerCase()==="p"){e.preventDefault();openCommandPalette();}
  else if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="s"){e.preventDefault();if(cm)saveFile(false);}
  else if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="b"){e.preventDefault();buildApk();}
  else if(e.key==="Escape")closePalette();
});

// ============ INIT ============
if(localStorage.getItem("uiLang"))setLang(localStorage.getItem("uiLang"));
loadFiles("");
loadPresets();
loadSystemInfo();
setInterval(loadSystemInfo,15000);
pollNotifications();
notifPollTimer=setInterval(pollNotifications,3000);
setTimeout(function(){try{scanAllErrors();}catch(e){}},1500);
setTimeout(function(){try{
  fetch("/api/settings/"+encodeURIComponent(PROJECT)).then(function(r){return r.json();}).then(function(d){
    if(document.getElementById("autoBuildChk"))document.getElementById("autoBuildChk").checked=!!d.autoBuild;
  });
}catch(e){}},1000);
</script>
</body>
</html>
'''

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    print("")
    print("=================================================")
    print("⚡ ZIHAD MOBILE IDE v12.0 — ULTIMATE EDITION")
    print("=================================================")
    print("Projects :", PROJECTS_DIR)
    print("APKs     :", APKS_DIR)
    print("Plugins  :", PLUGINS_DIR)
    print("Kanban   :", KANBAN_DIR)
    print("Notes    :", NOTES_DIR)
    print("Server   : http://127.0.0.1:%d" % PORT)
    print("=================================================")
    print("Features: 12 templates, Git, Logcat, PTY, Kanban,")
    print("Notes, Bookmarks, Plugins, Themes, Aliases,")
    print("Macros, Analytics, Auto-Build, Notifications,")
    print("Dev Tools, Snippets, Command Palette, i18n,")
    print("PWA, Live Preview, Real Termux PTY")
    print("=================================================")
    print("")
    app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)
