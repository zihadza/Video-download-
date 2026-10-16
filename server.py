import os
import re
import json
import time
import shutil
import sqlite3
import mimetypes
import subprocess
import threading
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime
from flask import (
    Flask, request, jsonify, Response, send_file,
    abort, render_template_string
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

HOME = Path.home()
BASE = (HOME / "Projects" / "ZihadIDE").resolve()
PROJECTS = (BASE / "projects").resolve()
BACKUPS = (BASE / "backups").resolve()
SETTINGS_FILE = BASE / "ide_settings.json"

PROJECTS.mkdir(parents=True, exist_ok=True)
BACKUPS.mkdir(parents=True, exist_ok=True)

HOST = "127.0.0.1"
PORT = int(os.environ.get("ZIHAD_IDE_PORT", "3040"))
MAX_EDITOR_FILE = 10 * 1024 * 1024
MAX_COMMAND_TIME = 120

LANGUAGES = {
    ".py": "python", ".pyw": "python",
    ".js": "javascript", ".mjs": "javascript",
    ".html": "html", ".htm": "html",
    ".css": "css", ".json": "json",
    ".xml": "xml", ".php": "php",
    ".java": "java", ".kt": "kotlin",
    ".c": "c", ".h": "c", ".cpp": "cpp",
    ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp",
    ".go": "go", ".rs": "rust", ".rb": "ruby",
    ".pl": "perl", ".sh": "shell", ".bash": "shell",
    ".md": "markdown", ".txt": "text",
    ".yml": "yaml", ".yaml": "yaml", ".toml": "toml",
    ".gradle": "groovy", ".properties": "properties",
    ".sql": "sql", ".dart": "dart"
}


def size_text(n):
    n = float(n)
    if n < 1024:
        return f"{int(n)} B"
    for unit in ("KB", "MB", "GB", "TB"):
        n /= 1024
        if n < 1024 or unit == "TB":
            return f"{n:.2f} {unit}"
    return f"{n:.2f} TB"


def folder_size(path):
    total = 0
    try:
        for p in Path(path).rglob("*"):
            try:
                if p.is_file() and not p.is_symlink():
                    total += p.stat().st_size
            except OSError:
                pass
    except OSError:
        pass
    return total


def safe_name(value):
    value = str(value or "").strip()
    if not value or value in (".", ".."):
        raise ValueError("Name is required.")
    if "/" in value or "\\" in value or "\x00" in value:
        raise ValueError("Name cannot contain path separators.")
    return value


def project_root(name):
    name = safe_name(name)
    p = (PROJECTS / name).resolve()
    if p.parent != PROJECTS:
        raise ValueError("Invalid project path.")
    if not p.is_dir() or p.is_symlink():
        raise FileNotFoundError("Project not found.")
    return p


def safe_path(root, relative=""):
    root = Path(root).resolve()
    relative = str(relative or "").replace("\\", "/")
    if "\x00" in relative:
        raise ValueError("Invalid path.")
    p = (root / relative).resolve()
    if p != root and root not in p.parents:
        raise ValueError("Path is outside the selected project.")
    return p


def command(cmd, cwd, timeout=MAX_COMMAND_TIME):
    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            env=os.environ.copy()
        )
        return {
            "ok": result.returncode == 0,
            "code": result.returncode,
            "output": (result.stdout or "")[-100000:],
            "duration": round(time.time() - start, 2)
        }
    except subprocess.TimeoutExpired as e:
        out = e.stdout or ""
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        return {
            "ok": False, "code": 124,
            "output": str(out) + "\nTimed out.",
            "duration": round(time.time() - start, 2)
        }
    except Exception as e:
        return {
            "ok": False, "code": 1,
            "output": str(e),
            "duration": round(time.time() - start, 2)
        }


def error(message, status=400):
    return jsonify({"ok": False, "error": str(message)}), status


def scan_tree(root, current=None, depth=0):
    current = current or root
    result = []
    if depth > 10:
        return result

    try:
        entries = sorted(
            current.iterdir(),
            key=lambda p: (not p.is_dir(), p.name.lower())
        )
    except OSError:
        return result

    for p in entries:
        if p.is_symlink():
            continue
        try:
            stat = p.stat()
            is_dir = p.is_dir()
            sz = folder_size(p) if is_dir else stat.st_size
            item = {
                "name": p.name,
                "path": p.relative_to(root).as_posix(),
                "type": "folder" if is_dir else "file",
                "size": sz,
                "sizeText": size_text(sz),
                "extension": "" if is_dir else p.suffix.lower(),
                "language": LANGUAGES.get(p.suffix.lower(), "text"),
                "modified": datetime.fromtimestamp(
                    stat.st_mtime
                ).strftime("%Y-%m-%d %H:%M"),
                "childrenList": []
            }
            if is_dir:
                item["childrenList"] = scan_tree(p and root, p, depth + 1)
            result.append(item)
        except (OSError, ValueError):
            continue
    return result


def flatten(items):
    out = []
    for item in items:
        out.append(item)
        out.extend(flatten(item.get("childrenList", [])))
    return out


def read_settings():
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(data):
    old = read_settings()
    old.update(data)
    SETTINGS_FILE.write_text(
        json.dumps(old, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    return old


def make_android_project(root, name, package, language="java"):
    if not re.fullmatch(r"[A-Za-z_]\w*(\.[A-Za-z_]\w*)+", package):
        raise ValueError("Package must look like com.example.myapp.")

    package_dir = root / "app" / "src" / "main"
    package_dir = package_dir / ("java" if language == "java" else "kotlin")
    for part in package.split("."):
        package_dir = package_dir / part
    package_dir.mkdir(parents=True, exist_ok=True)

    safe_label = name.replace("&", "&amp;").replace("<", "&lt;")
    (root / "settings.gradle").write_text(
        "pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }\n"
        "dependencyResolutionManagement { repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS); repositories { google(); mavenCentral() } }\n"
        f"rootProject.name = '{root.name}'\ninclude ':app'\n",
        encoding="utf-8"
    )
    (root / "build.gradle").write_text(
        "plugins { id 'com.android.application' version '8.7.3' apply false }\n",
        encoding="utf-8"
    )
    (root / "gradle.properties").write_text(
        "org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8\n"
        "android.useAndroidX=true\n"
        "android.nonTransitiveRClass=true\n",
        encoding="utf-8"
    )
    appdir = root / "app"
    appdir.mkdir(exist_ok=True)
    (appdir / "build.gradle").write_text(
        "plugins { id 'com.android.application' }\n"
        "android {\n"
        f"    namespace '{package}'\n"
        "    compileSdk 35\n"
        "    defaultConfig {\n"
        f"        applicationId '{package}'\n"
        "        minSdk 23\n"
        "        targetSdk 35\n"
        "        versionCode 1\n"
        "        versionName '1.0'\n"
        "    }\n"
        "}\n",
        encoding="utf-8"
    )

    main = root / "app" / "src" / "main"
    (main / "res" / "values").mkdir(parents=True, exist_ok=True)
    (main / "AndroidManifest.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<manifest xmlns:android="http://schemas.android.com/apk/res/android">\n'
        ' <application android:label="' + safe_label +
        '" android:theme="@android:style/Theme.Material.Light.NoActionBar">\n'
        '  <activity android:name=".MainActivity" android:exported="true">\n'
        '   <intent-filter><action android:name="android.intent.action.MAIN"/>\n'
        '   <category android:name="android.intent.category.LAUNCHER"/></intent-filter>\n'
        '  </activity>\n'
        ' </application>\n</manifest>\n',
        encoding="utf-8"
    )
    (main / "res" / "values" / "strings.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<resources><string name="app_name">' + safe_label +
        '</string></resources>\n',
        encoding="utf-8"
    )

    if language == "java":
        src = (
            f"package {package};\n"
            "import android.app.Activity;\n"
            "import android.os.Bundle;\n"
            "import android.graphics.Color;\n"
            "import android.view.Gravity;\n"
            "import android.widget.LinearLayout;\n"
            "import android.widget.TextView;\n"
            "public class MainActivity extends Activity {\n"
            " @Override public void onCreate(Bundle b) {\n"
            "  super.onCreate(b);\n"
            "  LinearLayout l=new LinearLayout(this);\n"
            "  l.setGravity(Gravity.CENTER);\n"
            "  l.setBackgroundColor(Color.rgb(10,16,30));\n"
            "  TextView t=new TextView(this);\n"
            f"  t.setText({json.dumps(name + ' is ready')});\n"
            "  t.setTextColor(Color.WHITE);t.setTextSize(24);\n"
            "  l.addView(t);setContentView(l);\n"
            " }\n}\n"
        )
        (package_dir / "MainActivity.java").write_text(src, encoding="utf-8")
    else:
        src = (
            f"package {package}\n"
            "import android.app.Activity\n"
            "import android.os.Bundle\n"
            "import android.graphics.Color\n"
            "import android.view.Gravity\n"
            "import android.widget.LinearLayout\n"
            "import android.widget.TextView\n"
            "class MainActivity : Activity() {\n"
            " override fun onCreate(b: Bundle?) {\n"
            "  super.onCreate(b)\n"
            "  val l=LinearLayout(this)\n"
            "  l.gravity=Gravity.CENTER\n"
            "  l.setBackgroundColor(Color.rgb(10,16,30))\n"
            "  val t=TextView(this)\n"
            f"  t.text={json.dumps(name + ' is ready')}\n"
            "  t.setTextColor(Color.WHITE);t.textSize=24f\n"
            "  l.addView(t);setContentView(l)\n"
            " }\n}\n"
        )
        (package_dir / "MainActivity.kt").write_text(src, encoding="utf-8")


HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<meta name="theme-color" content="#080d18">
<title>Zihad Mobile IDE Ultra Pro Max</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/theme/material-darker.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/dialog/dialog.min.css">
<style>
:root{color-scheme:dark;--bg:#080d18;--panel:#101827;--panel2:#151f32;--line:#26354e;--text:#eef4ff;--muted:#8d9db8;--blue:#65a7ff;--purple:#a88aff;--green:#4be0ad;--red:#ff718b;--gold:#f3c76e}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at top left,#1a2b50 0,#080d18 48%,#070a12 100%);color:var(--text);font:14px system-ui,-apple-system,"Segoe UI",sans-serif;min-height:100vh}button,input,select,textarea{font:inherit}button{color:var(--text);background:#1a2841;border:1px solid #304360;border-radius:10px;padding:9px 12px;cursor:pointer;touch-action:manipulation;transition:background .15s,border .15s,transform .15s}button:active{transform:scale(.97)}button:hover{border-color:var(--blue);background:#243756}.primary{background:linear-gradient(120deg,#3678ec,#8257e9);border:0}.danger{color:#ff9cac}.muted{color:var(--muted)}.tiny{font-size:11px}.hidden{display:none!important}.top{position:sticky;top:0;z-index:20;background:#080d18ed;backdrop-filter:blur(16px);border-bottom:1px solid var(--line);padding:10px 13px;display:flex;align-items:center;gap:10px}.logo{width:39px;height:39px;border-radius:13px;display:grid;place-items:center;background:linear-gradient(135deg,#3988ff,#a16bff);font-size:22px}.brand{font-weight:850;letter-spacing:.2px}.brand small{display:block;font-weight:500;color:var(--muted);font-size:10px}.online{margin-left:auto;color:#a8f4d9;font-size:11px;display:flex;align-items:center;gap:6px}.dot{width:8px;height:8px;background:var(--green);border-radius:50%;box-shadow:0 0 10px #4be0ad88}
.wrap{max-width:1500px;margin:auto;padding:12px;display:grid;grid-template-columns:225px minmax(0,1fr);gap:12px}.panel{min-width:0;background:linear-gradient(155deg,#121c2d,#0c1422);border:1px solid var(--line);border-radius:15px;overflow:hidden;box-shadow:0 10px 34px #0002}.head{padding:11px 12px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:8px;font-weight:750}.spacer{flex:1}.side{position:sticky;top:70px;align-self:start;max-height:calc(100vh - 80px);overflow:auto}.pad{padding:10px}.select,.field{width:100%;min-width:0;background:#080f1b;border:1px solid var(--line);color:var(--text);padding:10px;border-radius:9px;outline:none}.field:focus,.select:focus{border-color:var(--blue)}.navgrid{display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-top:8px}.nav{width:100%;background:transparent;border-color:transparent;text-align:left;padding:10px 8px;display:flex;gap:8px;align-items:center}.nav.active{background:#223453;border-color:#3c5681}.ico{width:20px;text-align:center;color:var(--blue)}.section{font-size:10px;letter-spacing:1.4px;color:#8091ad;font-weight:800;padding:12px 7px 5px}.stats{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:10px}.stat{background:#0a1322;border:1px solid #24334b;border-radius:10px;padding:9px}.stat strong{display:block;font-size:16px}.stat span{color:var(--muted);font-size:10px}
.hero{padding:16px;background:linear-gradient(110deg,#172a4a,#191a38 65%,#291a43)}.hero h1{font-size:20px;margin:0 0 5px}.hero p{color:#b3c2dc;margin:0;font-size:12px;line-height:1.6}.actions{display:flex;gap:6px;flex-wrap:wrap;margin-top:12px}.actions button{font-size:12px;padding:8px 10px}.workspace{display:grid;gap:11px;margin-top:11px}.toolbar{display:flex;gap:5px;flex-wrap:wrap;padding:8px;border-bottom:1px solid var(--line);background:#0c1422}.toolbar button{padding:7px 9px;font-size:11px}.tabs{display:flex;overflow:auto;background:#090f1b;border-bottom:1px solid var(--line)}.tab{white-space:nowrap;border:0;border-radius:0;border-right:1px solid #1d2b42;background:transparent;color:var(--muted);font-size:12px;padding:10px 12px}.tab.active{background:#17243a;color:white;border-bottom:2px solid var(--blue)}.cmwrap{height:39vh;min-height:230px;max-height:620px}.CodeMirror{height:100%;font-size:13px;line-height:1.6;background:#0a111d}.CodeMirror-gutters{background:#0a111d;border-color:#24334b}.CodeMirror-linenumber{color:#62738d}.foot{padding:8px 10px;border-top:1px solid var(--line);display:flex;gap:8px;justify-content:space-between;flex-wrap:wrap;font-size:10px;color:var(--muted)}.lower{display:grid;grid-template-columns:1fr 1fr;gap:11px}.boxbody{padding:10px;min-width:0}.filetools{display:flex;gap:6px;margin-bottom:8px}.filelist{max-height:310px;overflow:auto}.fileitem{display:flex;gap:7px;align-items:center;padding:9px 6px;border-radius:8px;cursor:pointer;border:1px solid transparent}.fileitem:hover,.fileitem.selected{background:#1b2a43;border-color:#2e4568}.fname{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.fsize{color:var(--muted);font-size:10px;white-space:nowrap}.console{height:160px;overflow:auto;background:#070c14;color:#c7d6ef;border-radius:9px;padding:10px;font:12px/1.55 ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere}.good{color:var(--green)}.bad{color:var(--red)}.terminalrow{display:flex;gap:6px;margin-top:7px}.terminalrow .field{flex:1}.pill{border:1px solid #344968;background:#16243a;border-radius:99px;padding:4px 8px;font-size:10px;color:#c2d3ef}.modalback{position:fixed;inset:0;z-index:90;background:#02050bdc;display:grid;place-items:center;padding:15px}.modal{width:min(520px,100%);max-height:90vh;overflow:auto;background:#111b2b;border:1px solid #34445f;border-radius:17px;padding:16px;box-shadow:0 25px 80px #0009}.modal h3{margin:0 0 12px}.modalactions{display:flex;justify-content:flex-end;gap:7px;margin-top:12px}.modal .field,.modal .select{margin:5px 0 10px}.toast{position:fixed;z-index:100;bottom:20px;left:50%;transform:translate(-50%,15px);opacity:0;pointer-events:none;background:#1b2c46;border:1px solid #45618a;border-radius:12px;padding:11px 15px;transition:.2s;max-width:92vw;box-shadow:0 10px 35px #0008}.toast.show{opacity:1;transform:translate(-50%,0)}.preview{width:100%;height:42vh;min-height:270px;border:0;background:white;border-radius:8px}.progress{height:7px;background:#26344b;border-radius:8px;overflow:hidden;margin:10px 0}.progress i{display:block;width:0;height:100%;background:linear-gradient(90deg,#4d8cff,#b18bff);transition:width .25s}.badge{font-size:10px;padding:4px 7px;border-radius:7px;background:#172640;color:#a9caff}
@media(min-width:1000px){.cmwrap{height:48vh}.workspace{gap:12px}}
@media(max-width:760px){.wrap{display:block;padding:8px}.side{position:static;max-height:none;margin-bottom:9px}.pad{padding:8px}.navgrid{grid-template-columns:repeat(4,1fr)}.nav{flex-direction:column;justify-content:center;text-align:center;gap:3px;padding:7px 2px;font-size:10px}.ico{font-size:16px}.stats{display:none}.section{padding-top:8px}.hero{padding:13px}.hero h1{font-size:18px}.workspace{margin-top:9px;gap:9px}.cmwrap{height:39vh;min-height:220px}.lower{grid-template-columns:1fr}.top{padding:9px}.online{font-size:0}.online .dot{width:9px;height:9px}.brand small{font-size:9px}.toolbar{gap:4px}.toolbar button{padding:7px;font-size:10px}.filetools{flex-wrap:wrap}.filetools .field{flex-basis:100%}.console{height:150px}.preview{height:48vh}}
</style>
</head>
<body>
<header class="top">
 <div class="logo">⚡</div>
 <div class="brand">ZIHAD MOBILE IDE <small>ULTRA PRO MAX · MOBILE DEVELOPMENT</small></div>
 <div class="online"><span class="dot"></span> LOCAL SERVER ONLINE</div>
</header>
<div class="wrap">
<aside class="panel side">
 <div class="head">◈ Workspace <span class="spacer"></span><button onclick="loadProjects()">↻</button></div>
 <div class="pad">
  <select id="projectSelect" class="select" onchange="switchProject(this.value)"></select>
  <div class="navgrid">
   <button class="nav active" data-page="editor" onclick="page('editor',this)"><span class="ico">⌘</span>Editor</button>
   <button class="nav" data-page="files" onclick="page('files',this)"><span class="ico">▤</span>Files</button>
   <button class="nav" data-page="preview" onclick="page('preview',this)"><span class="ico">◉</span>Preview</button>
   <button class="nav" data-page="build" onclick="page('build',this)"><span class="ico">⚙</span>Build</button>
  </div>
  <div class="section">PROJECT TOOLS</div>
  <button class="nav" onclick="newProject()">＋ New project</button>
  <button class="nav" onclick="newFile()">▧ New file</button>
  <button class="nav" onclick="newFolder()">▣ New folder</button>
  <button class="nav" onclick="runCode()">▶ Run code</button>
  <button class="nav" onclick="checkTools()">⌕ Compiler check</button>
  <button class="nav" onclick="backupProject()">⤓ Backup project</button>
  <button class="nav" onclick="restoreBackup()">⤴ Restore backup</button>
  <button class="nav" onclick="openSettings()">⚙ Settings</button>
  <button class="nav" onclick="showPanel('terminal')">$_ Terminal</button>
  <button class="nav" onclick="showPanel('api')">⇄ API tester</button>
  <button class="nav" onclick="showPanel('database')">▦ SQLite tools</button>
  <button class="nav" onclick="showPanel('git')">⑂ Git tools</button>
  <button class="nav" onclick="showPanel('ai')">✦ AI assistant</button>
  <div class="stats"><div class="stat"><strong id="fileCount">0</strong><span>FILES</span></div><div class="stat"><strong id="projectSize">0 B</strong><span>PROJECT SIZE</span></div></div>
  <div class="section">WORKSPACE STATUS</div><div class="tiny muted" id="status">Loading…</div>
 </div>
</aside>
<main>
 <section class="panel hero">
  <h1 id="heroTitle">Your coding studio, in your pocket.</h1>
  <p>Write code, manage files, preview web projects, use Termux tools and build Android apps from your phone.</p>
  <div class="actions"><button class="primary" onclick="newProject()">＋ Create project</button><button onclick="runCode()">▶ Run</button><button onclick="saveFile()">💾 Save</button><button onclick="page('preview')">◉ Preview</button><button onclick="page('build')">Build APK</button></div>
 </section>
 <div class="workspace">
  <section class="panel" id="editorPanel">
   <div class="head">⌘ Code Editor <span class="badge" id="languageBadge">TEXT</span><span class="spacer"></span><span id="saveStatus" class="tiny muted">Ready</span></div>
   <div class="toolbar">
    <button onclick="saveFile()">💾 Save</button><button onclick="undo()">↶ Undo</button><button onclick="redo()">↷ Redo</button><button onclick="findText()">⌕ Find</button><button onclick="replaceText()">⇄ Replace</button><button onclick="cutAll()">✂ Cut all</button><button onclick="selectAll()">Select all</button><button onclick="newFile()">＋ File</button><button onclick="runCode()">▶ Run</button>
   </div>
   <div id="tabs" class="tabs"></div>
   <div class="cmwrap"><textarea id="source"></textarea></div>
   <div class="foot"><span id="cursor">Ln 1, Col 1</span><span id="lineStats">0 lines · 0 chars</span><span id="sizeLabel">0 B</span><span id="modeLabel">Plain text</span></div>
  </section>
  <section class="panel hidden" id="filesPanel">
   <div class="head">▤ File Manager <span class="spacer"></span><button onclick="refreshTree()">↻ Refresh</button></div>
   <div class="boxbody"><div class="filetools"><input id="fileSearch" class="field" placeholder="Search files and folders…" oninput="renderFiles()"><button onclick="newFolder()">＋ Folder</button></div><div id="fileList" class="filelist"></div><div class="tiny muted" id="fileSummary"></div></div>
  </section>
  <section class="panel hidden" id="previewPanel">
   <div class="head">◉ Live Preview <span class="spacer"></span><button onclick="reloadPreview()">↻ Reload</button><button onclick="openPreview()">↗ Open</button></div>
   <div class="boxbody"><div class="terminalrow"><input id="previewPath" class="field" value="index.html" placeholder="Relative HTML file path"><button class="primary" onclick="reloadPreview()">Preview</button></div><iframe id="previewFrame" class="preview" sandbox="allow-scripts allow-forms allow-modals" title="Web project preview"></iframe><p class="tiny muted">Web preview runs in a sandbox. Android native screens require a real APK build.</p></div>
  </section>
  <section class="panel hidden" id="buildPanel">
   <div class="head">⚙ Build Center <span class="spacer"></span><span class="badge">GRADLE / APK</span></div>
   <div class="boxbody"><p class="muted">Build a debug APK from an Android Gradle project.</p><div class="progress"><i id="buildProgress"></i></div><div id="buildStatus" class="tiny muted">Ready</div><div class="actions"><button class="primary" onclick="buildAPK()">▶ Build debug APK</button><button onclick="checkTools()">Check tools</button><button onclick="backupProject()">Backup first</button></div><div id="buildLog" class="console">Build output will appear here.</div><div id="apkLink"></div></div>
  </section>
  <section class="panel hidden" id="terminalPanel">
   <div class="head">$_ Terminal <span class="spacer"></span><span class="badge">PROJECT ROOT</span></div>
   <div class="boxbody"><div id="terminalOutput" class="console">Terminal ready. Commands run inside the selected project directory.</div><div class="terminalrow"><input id="commandInput" class="field" placeholder="e.g. python main.py" onkeydown="if(event.key==='Enter')runTerminal()"><button class="primary" onclick="runTerminal()">Run</button></div><div class="actions"><button onclick="quick('pwd')">pwd</button><button onclick="quick('ls -lah')">ls -lah</button><button onclick="quick('python --version')">Python</button><button onclick="quick('gradle --version')">Gradle</button></div></div>
  </section>
  <section class="panel hidden" id="apiPanel">
   <div class="head">⇄ HTTP API Tester</div>
   <div class="boxbody"><select id="apiMethod" class="select"><option>GET</option><option>POST</option><option>PUT</option><option>DELETE</option><option>PATCH</option></select><p><input id="apiUrl" class="field" placeholder="https://example.com/api"></p><textarea id="apiBody" class="field" rows="4" placeholder='JSON body for POST/PUT/PATCH'></textarea><button class="primary" onclick="testAPI()">Send request</button><div id="apiResult" class="console" style="margin-top:9px">Response appears here. Cross-origin restrictions may apply.</div></div>
  </section>
  <section class="panel hidden" id="databasePanel">
   <div class="head">▦ SQLite Database Browser</div>
   <div class="boxbody"><p class="tiny muted">Select a SQLite database inside the current project. Queries are limited to read-only SELECT/PRAGMA/EXPLAIN operations.</p><input id="dbPath" class="field" placeholder="database.db"><textarea id="dbQuery" class="field" rows="3">SELECT name FROM sqlite_master WHERE type='table';</textarea><button class="primary" onclick="queryDatabase()">Run read-only query</button><div id="dbResult" class="console" style="margin-top:9px">Database results appear here.</div></div>
  </section>
  <section class="panel hidden" id="gitPanel">
   <div class="head">⑂ Git Tools</div>
   <div class="boxbody"><div class="actions"><button onclick="gitAction('status')">Status</button><button onclick="gitAction('diff')">Diff</button><button onclick="gitAction('log')">Log</button><button onclick="gitAction('branches')">Branches</button></div><input id="gitMessage" class="field" placeholder="Commit message" style="margin-top:8px"><div class="actions"><button onclick="gitAction('commit')">Commit tracked changes</button><button onclick="gitAction('pull')">Pull</button><button onclick="gitAction('push')">Push</button></div><div id="gitResult" class="console" style="margin-top:9px">Git output appears here.</div><p class="tiny muted">Review remotes and changes before pull/push. Credentials are managed by your Git setup.</p></div>
  </section>
  <section class="panel hidden" id="aiPanel">
   <div class="head">✦ AI Coding Assistant</div>
   <div class="boxbody"><p class="tiny muted">Configure an OpenAI-compatible API endpoint in Settings. Never share your API key. AI calls may incur provider charges.</p><textarea id="aiPrompt" class="field" rows="4" placeholder="Explain this code, fix an error, or suggest an improvement…"></textarea><div class="actions"><button class="primary" onclick="askAI('ask')">Ask AI</button><button onclick="askAI('explain')">Explain open file</button><button onclick="askAI('fix')">Suggest a fix</button></div><div id="aiResult" class="console" style="margin-top:9px">AI response appears here.</div><button onclick="applyAI()" style="margin-top:8px">Replace editor with response</button><p class="tiny muted">AI output is a suggestion. Review it before replacing or running code.</p></div>
  </section>
  <section class="panel" id="outputPanel">
   <div class="head">◈ Output & Diagnostics <span class="spacer"></span><button onclick="clearOutput()">Clear</button><button onclick="checkTools()">Check tools</button></div>
   <div class="boxbody"><div id="output" class="console">Welcome to Zihad Mobile IDE Ultra Pro Max.</div></div>
  </section>
 </div>
</main>
</div>
<div id="modalBack" class="modalback hidden"><div class="modal"><h3 id="modalTitle">Dialog</h3><div id="modalBody"></div><div class="modalactions"><button onclick="closeModal()">Cancel</button><button class="primary" id="modalOK">Continue</button></div></div></div>
<div id="toast" class="toast"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/javascript/javascript.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/xml/xml.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/css/css.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/python/python.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/clike/clike.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/php/php.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/shell/shell.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/go/go.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/rust/rust.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/dialog/dialog.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/search/searchcursor.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/search/search.min.js"></script>
<script>
const $=id=>document.getElementById(id);
let cm,currentProject='',currentFile='',tree=[],tabs={},activePage='editor',autosave=null,aiAnswer='';
async function api(url,opts={}){
 const res=await fetch(url,{...opts,headers:{'Content-Type':'application/json',...(opts.headers||{})}});
 const data=await res.json().catch(()=>({ok:false,error:'Invalid server response'}));
 if(!res.ok||data.ok===false)throw Error(data.error||('HTTP '+res.status));
 return data;
}
function post(url,data={}){return api(url,{method:'POST',body:JSON.stringify(data)})}
function toast(s){$('toast').textContent=s;$('toast').classList.add('show');clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').classList.remove('show'),2500)}
function output(id,s,ok=null){const el=$(id);el.textContent=String(s??'');el.className='console'+(ok===true?' good':ok===false?' bad':'')}
function append(id,s,ok=null){const el=$(id),d=document.createElement('div');d.textContent=String(s);if(ok===true)d.className='good';if(ok===false)d.className='bad';el.appendChild(d);el.scrollTop=el.scrollHeight}
function fmt(n){if(n<1024)return n+' B';let v=n/1024;for(const u of ['KB','MB','GB','TB']){if(v<1024||u==='TB')return v.toFixed(2)+' '+u;v/=1024}return n+' B'}
function openModal(title,html,fn){$('modalTitle').textContent=title;$('modalBody').innerHTML=html;$('modalBack').classList.remove('hidden');$('modalOK').onclick=async()=>{try{await fn()}catch(e){toast(e.message)}}}
function closeModal(){$('modalBack').classList.add('hidden')}
function fld(id,label,placeholder,value=''){return `<label class="tiny muted">${label}</label><input class="field" id="${id}" placeholder="${placeholder}" value="${String(value).replace(/"/g,'&quot;')}">`}
function page(name,btn=null){activePage=name;for(const p of ['editor','files','preview','build','terminal','api','database','git','ai'])$(p+'Panel').classList.toggle('hidden',p!==name);if(btn){document.querySelectorAll('[data-page]').forEach(b=>b.classList.remove('active'));btn.classList.add('active')}if(name==='preview')reloadPreview().catch(e=>toast(e.message));if(name==='files')renderFiles()}
function showPanel(name){page(name);document.getElementById(name+'Panel')?.scrollIntoView({behavior:'smooth',block:'start'})}
function mode(path){const ext=(path.split('.').pop()||'').toLowerCase();return ({js:'javascript',mjs:'javascript',html:'xml',htm:'xml',css:'css',py:'python',java:'text/x-java',kt:'text/x-kotlin',c:'text/x-csrc',h:'text/x-csrc',cpp:'text/x-c++src',php:'application/x-httpd-php',xml:'xml',json:{name:'javascript',json:true},sh:'shell',bash:'shell',go:'go',rs:'rust',sql:'text/x-sql'})[ext]||'text/plain'}
function editorStats(){if(!cm)return;let s=cm.getValue(),c=cm.getCursor();$('cursor').textContent=`Ln ${c.line+1}, Col ${c.ch+1}`;$('lineStats').textContent=`${s?s.split('\n').length:0} lines · ${s.length} chars`;$('sizeLabel').textContent=fmt(new TextEncoder().encode(s).length);$('languageBadge').textContent=(currentFile.split('.').pop()||'TEXT').toUpperCase();$('modeLabel').textContent=(currentFile.split('.').pop()||'Plain text').toUpperCase()}
function init(){
 cm=CodeMirror.fromTextArea($('source'),{theme:'material-darker',lineNumbers:true,lineWrapping:false,indentUnit:4,tabSize:4,matchBrackets:true,mode:'text/plain',extraKeys:{'Ctrl-S':saveFile,'Cmd-S':saveFile,'Ctrl-F':findText,'Ctrl-H':replaceText,'Ctrl-Z':undo,'Ctrl-Y':redo}});
 cm.on('change',()=>{editorStats();$('saveStatus').textContent='Unsaved';$('saveStatus').style.color='var(--gold)';if(currentFile){tabs[currentFile]=cm.getValue();clearTimeout(autosave);autosave=setTimeout(()=>saveFile(true),1000)}});cm.on('cursorActivity',editorStats);
}
async function loadProjects(){
 try{const d=await api('/api/projects');const sel=$('projectSelect');sel.innerHTML='';d.projects.forEach(p=>{let o=document.createElement('option');o.value=p.name;o.textContent=p.name+' · '+p.sizeText;sel.appendChild(o)});if(!d.projects.length){currentProject='';$('status').textContent='Create your first project';tree=[];renderFiles();return}const name=d.projects.some(p=>p.name===currentProject)?currentProject:d.projects[0].name;sel.value=name;await switchProject(name)}catch(e){toast(e.message)}
}
async function switchProject(name){if(!name)return;currentProject=name;currentFile='';tabs={};$('status').textContent='Loading '+name;await refreshTree();let all=flat(tree).filter(x=>x.type==='file');let first=all.find(x=>/^(index\.html|main\.py|main\.java|main\.kt|app\.js)$/i.test(x.name))||all[0];if(first)await openFile(first.path);else{cm.setValue('// Create a file to begin.');renderTabs()}$('status').textContent='Active: '+name;output('output','Project loaded: '+name,true)}
async function refreshTree(){if(!currentProject)return;const d=await api('/api/tree/'+encodeURIComponent(currentProject));tree=d.tree;$('fileCount').textContent=d.fileCount;$('projectSize').textContent=fmt(d.totalSize);$('fileSummary').textContent=`${d.fileCount} files · ${d.folderCount} folders · ${fmt(d.totalSize)} total`;renderFiles()}
function flat(items,out=[]){for(const x of items){out.push(x);if(x.childrenList)flat(x.childrenList,out)}return out}
function renderFiles(){const el=$('fileList');if(!el)return;el.innerHTML='';let q=($('fileSearch')?.value||'').toLowerCase();let rows=flat(tree).filter(x=>!q||x.path.toLowerCase().includes(q));if(!rows.length){el.textContent='No files found.';return}for(const f of rows){let r=document.createElement('div');r.className='fileitem'+(f.path===currentFile?' selected':'');let i=document.createElement('span');i.textContent=f.type==='folder'?'📁':f.extension==='.html'?'🌐':f.extension==='.js'?'📜':'📄';let n=document.createElement('span');n.className='fname';n.textContent=(f.type==='folder'?'▸ ':'')+f.name;n.title=f.path;let s=document.createElement('span');s.className='fsize';s.textContent=f.sizeText;r.append(i,n,s);r.onclick=()=>f.type==='folder'?folderActions(f):openFile(f.path);r.oncontextmenu=e=>{e.preventDefault();itemActions(f)};el.appendChild(r)}}
async function openFile(path){try{if(currentFile&&cm)tabs[currentFile]=cm.getValue();let d=await api('/api/file/'+encodeURIComponent(currentProject)+'?path='+encodeURIComponent(path));currentFile=path;tabs[path]=d.content;cm.setValue(d.content);cm.clearHistory();cm.setOption('mode',mode(path));$('saveStatus').textContent='Saved';$('saveStatus').style.color='var(--green)';editorStats();renderTabs();renderFiles();page('editor')}catch(e){toast(e.message)}}
function renderTabs(){const el=$('tabs');el.innerHTML='';Object.keys(tabs).forEach(p=>{let b=document.createElement('button');b.className='tab'+(p===currentFile?' active':'');b.textContent=p.split('/').pop()+' ×';b.onclick=()=>{if(p===currentFile){delete tabs[p];currentFile=Object.keys(tabs)[0]||'';if(currentFile)openFile(currentFile);else{cm.setValue('');renderTabs()}}else openFile(p)};el.appendChild(b)})}
async function saveFile(silent=false){if(!currentProject||!currentFile||!cm)return;let content=cm.getValue();try{let d=await post('/api/file/'+encodeURIComponent(currentProject),{path:currentFile,content});tabs[currentFile]=content;$('saveStatus').textContent='Saved';$('saveStatus').style.color='var(--green)';if(!silent)toast('Saved · '+d.sizeText);if(activePage==='preview')reloadPreview().catch(()=>{});refreshTree().catch(()=>{})}catch(e){$('saveStatus').textContent='Save failed';$('saveStatus').style.color='var(--red)';if(!silent)toast(e.message)}}
function undo(){cm.undo()}function redo(){cm.redo()}function findText(){cm.execCommand('find')}function replaceText(){cm.execCommand('replace')}function selectAll(){cm.focus();cm.execCommand('selectAll')}
async function cutAll(){if(!cm)return;cm.focus();cm.setValue('');if(currentFile){await saveFile();toast('All content cleared and saved; clipboard untouched')}else toast('Editor cleared')}
function newFile(){if(!currentProject)return toast('Create a project first');openModal('Create file',fld('newPath','Relative path','src/main.js'),async()=>{let p=$('newPath').value.trim();if(!p)throw Error('Enter a file path');await post('/api/file-create',{project:currentProject,path:p,content:''});closeModal();await refreshTree();await openFile(p);toast('File created')})}
function newFolder(){if(!currentProject)return toast('Create a project first');openModal('Create folder',fld('newFolderPath','Folder path','src/components'),async()=>{let p=$('newFolderPath').value.trim();if(!p)throw Error('Enter folder path');await post('/api/folder-create',{project:currentProject,path:p});closeModal();await refreshTree();toast('Folder created')})}
function itemActions(f){openModal('File actions',`<p class="tiny muted">${f.path} · ${f.sizeText}</p>${fld('renameTo','Rename','New name',f.name)}<button onclick="copyItem('${f.path.replace(/'/g,"\\'")}')">Copy file/folder</button> <button class="danger" onclick="deleteItem('${f.path.replace(/'/g,"\\'")}')">Delete</button>`,async()=>{let n=$('renameTo').value.trim();if(!n)throw Error('Enter a name');await post('/api/rename',{project:currentProject,path:f.path,name:n});closeModal();await refreshTree();toast('Renamed')})}
function folderActions(f){openModal('Folder actions',`<p>${f.path} · ${f.sizeText}</p>${fld('folderRename','Rename folder','New name',f.name)}<button class="danger" onclick="deleteItem('${f.path.replace(/'/g,"\\'")}')">Delete folder</button>`,async()=>{let n=$('folderRename').value.trim();if(!n)throw Error('Enter a name');await post('/api/rename',{project:currentProject,path:f.path,name:n});closeModal();await refreshTree()})}
async function deleteItem(path){if(!confirm('Delete '+path+'? This cannot be undone.'))return;try{await post('/api/delete',{project:currentProject,path});closeModal();if(path===currentFile){currentFile='';cm.setValue('')}await refreshTree();toast('Deleted')}catch(e){toast(e.message)}}
async function copyItem(path){try{await post('/api/copy',{project:currentProject,path});closeModal();await refreshTree();toast('Copied')}catch(e){toast(e.message)}}
function newProject(){openModal('Create project',fld('projectName','Project name','MyWebsite')+'<label class="tiny muted">Template</label><select id="projectType" class="select"><option value="web">Web app · HTML/CSS/JS</option><option value="python">Python</option><option value="android">Android Java</option><option value="kotlin">Android Kotlin</option><option value="empty">Empty</option></select>'+fld('appLabel','Android app label','My Android App')+fld('packageName','Android package','com.example.myapp'),async()=>{let name=$('projectName').value.trim();if(!name)throw Error('Enter project name');let d=await post('/api/project-create',{name,type:$('projectType').value,appName:$('appLabel').value||name,packageName:$('packageName').value||'com.example.myapp'});closeModal();currentProject=d.name;await loadProjects();toast('Project created')})}
async function runCode(){if(!currentFile)return toast('Open a file first');await saveFile(true);try{let d=await post('/api/run',{project:currentProject,path:currentFile});output('output',d.output,d.ok);if(d.preview){$('previewPath').value=currentFile;page('preview')}else page('editor')}catch(e){toast(e.message)}}
async function runTerminal(){let c=$('commandInput').value.trim();if(!c)return;$('commandInput').value='';append('terminalOutput','$ '+c);try{let d=await post('/api/terminal',{project:currentProject,command:c});append('terminalOutput',d.output||'(No output)',d.ok)}catch(e){append('terminalOutput',e.message,false)}}
function quick(c){$('commandInput').value=c;runTerminal()}
async function checkTools(){try{let d=await api('/api/tools');output('output',d.output);toast('Environment check complete')}catch(e){toast(e.message)}}
async function backupProject(){try{let d=await post('/api/backup',{project:currentProject});output('output',`Backup created\n${d.path}\nSize: ${d.sizeText}`,true);toast('Backup created')}catch(e){toast(e.message)}}
async function restoreBackup(){try{let d=await api('/api/backups');if(!d.backups.length)return toast('No backups found');openModal('Restore backup','<p class="tiny muted">Restoring replaces the selected project. A current backup is created first.</p><select id="backupChoice" class="select">'+d.backups.map(b=>`<option value="${b.name}">${b.name} · ${b.sizeText}</option>`).join('')+'</select>',async()=>{let b=$('backupChoice').value;if(!confirm('Replace current project from this backup?'))return;await post('/api/restore',{project:currentProject,backup:b});closeModal();await switchProject(currentProject);toast('Restored')})}catch(e){toast(e.message)}}
async function reloadPreview(){if(!currentProject)return;await saveFile(true);let p=$('previewPath').value.trim()||'index.html';$('previewFrame').src='/preview/'+encodeURIComponent(currentProject)+'/'+p.split('/').map(encodeURIComponent).join('/')+'?t='+Date.now()}
function openPreview(){if($('previewFrame').src)window.open($('previewFrame').src,'_blank')}
async function buildAPK(){if(!currentProject)return toast('Select a project');$('buildProgress').style.width='25%';$('buildStatus').textContent='Build running…';$('apkLink').innerHTML='';output('buildLog','Starting Gradle…');try{let d=await post('/api/build',{project:currentProject});$('buildProgress').style.width=d.ok?'100%':'0%';$('buildStatus').textContent=d.ok?'Build successful':'Build failed';output('buildLog',d.output,d.ok);if(d.apk){let a=document.createElement('a');a.href=d.apk;a.textContent='⬇ Download APK · '+d.apkSizeText;a.style.display='block';a.style.marginTop='12px';a.style.color='#8ab4ff';$('apkLink').appendChild(a)}}catch(e){$('buildProgress').style.width='0%';output('buildLog',e.message,false)}}
async function testAPI(){let url=$('apiUrl').value.trim(),method=$('apiMethod').value;if(!url)return toast('Enter a URL');try{let d=await post('/api/http-test',{url,method,body:$('apiBody').value});output('apiResult',JSON.stringify(d,null,2),d.ok)}catch(e){output('apiResult',e.message,false)}}
async function queryDatabase(){try{let d=await post('/api/sqlite',{project:currentProject,path:$('dbPath').value,query:$('dbQuery').value});output('dbResult',JSON.stringify(d,null,2),d.ok)}catch(e){output('dbResult',e.message,false)}}
async function gitAction(action){try{let d=await post('/api/git',{project:currentProject,action,message:$('gitMessage').value});output('gitResult',d.output,d.ok)}catch(e){output('gitResult',e.message,false)}}
async function openSettings(){let s=await api('/api/settings');openModal('IDE Settings',fld('aiEndpoint','AI API endpoint (OpenAI-compatible)','https://api.example.com/v1/chat/completions',s.aiEndpoint||'')+fld('aiModel','AI model name','model-name',s.aiModel||'')+fld('aiKey','AI API key','Keep private; blank keeps current key','')+'<label class="tiny muted">Editor autosave delay (ms)</label><input id="autosaveDelay" class="field" type="number" min="300" max="10000" value="'+(s.autosaveDelay||1000)+'"><label class="tiny muted">Theme</label><select id="themeSetting" class="select"><option value="dark">AMOLED Dark</option><option value="blue">Deep Blue</option></select>',async()=>{let data={aiEndpoint:$('aiEndpoint').value.trim(),aiModel:$('aiModel').value.trim(),autosaveDelay:Math.max(300,Math.min(10000,Number($('autosaveDelay').value)||1000)),theme:$('themeSetting').value};if($('aiKey').value)data.aiKey=$('aiKey').value;await post('/api/settings',data);closeModal();toast('Settings saved')})}
async function askAI(action){let prompt=$('aiPrompt').value.trim();if(action==='explain')prompt='Explain this code clearly, preferably in Bangla:\n'+(cm.getValue());if(action==='fix')prompt='Review this code and suggest a safe fix. Return explanation and corrected code:\n'+cm.getValue();if(!prompt)return toast('Enter a prompt');output('aiResult','Contacting AI provider…');try{let d=await post('/api/ai',{prompt});aiAnswer=d.answer||'';output('aiResult',aiAnswer,d.ok)}catch(e){output('aiResult',e.message,false)}}
function applyAI(){if(!aiAnswer)return toast('No AI response');if(!confirm('Replace the entire editor with the AI response?'))return;cm.setValue(aiAnswer);toast('Review and save the suggested code')}
function clearOutput(){output('output','Output cleared')}
window.addEventListener('beforeunload',()=>{if(currentFile&&cm&&tabs[currentFile]!==cm.getValue())saveFile(true)});
document.addEventListener('visibilitychange',()=>{if(document.hidden&&currentFile)saveFile(true)});
init();loadProjects();
</script>
</body>
</html>"""


@app.get("/")
def home():
    return render_template_string(HTML)


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "app": "Zihad Mobile IDE Ultra Pro Max", "port": PORT})


@app.get("/api/projects")
def list_projects():
    out = []
    for p in sorted(PROJECTS.iterdir(), key=lambda x: x.name.lower()):
        if p.is_dir() and not p.is_symlink():
            n = folder_size(p)
            out.append({
                "name": p.name, "size": n, "sizeText": size_text(n),
                "modified": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            })
    return jsonify({"ok": True, "projects": out})


@app.post("/api/project-create")
def create_project():
    d = request.get_json(silent=True) or {}
    try:
        name = safe_name(d.get("name"))
        root = safe_path(PROJECTS, name)
        if root.exists():
            return error("Project already exists.", 409)
        root.mkdir(parents=True)
        kind = d.get("type", "web")
        if kind == "web":
            (root / "index.html").write_text(
                '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>My App</title><link rel="stylesheet" href="style.css"></head><body><main><h1>Hello, Zihad IDE!</h1><p>Your web project is ready.</p><button id="test">Test button</button></main><script src="app.js"></script></body></html>',
                encoding="utf-8")
            (root / "style.css").write_text(
                "body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0b1220;color:#eef4ff;font:16px system-ui}main{text-align:center;padding:24px}button{padding:12px 18px;border:0;border-radius:10px;background:#568aff;color:white}",
                encoding="utf-8")
            (root / "app.js").write_text(
                "document.querySelector('#test')?.addEventListener('click',()=>alert('It works!'));",
                encoding="utf-8")
        elif kind == "python":
            (root / "main.py").write_text('print("Hello from Zihad Mobile IDE!")\n', encoding="utf-8")
            (root / "README.md").write_text("# " + name + "\n", encoding="utf-8")
        elif kind in ("android", "kotlin"):
            make_android_project(root, d.get("appName", name), d.get("packageName", "com.example.myapp"), "kotlin" if kind == "kotlin" else "java")
        elif kind == "empty":
            (root / "README.md").write_text("# " + name + "\n", encoding="utf-8")
        else:
            shutil.rmtree(root, ignore_errors=True)
            return error("Unknown project type.")
        return jsonify({"ok": True, "name": name})
    except Exception as e:
        return error(e)


@app.get("/api/tree/<project>")
def api_tree(project):
    try:
        root = project_root(project)
        tree = scan_tree(root)
        items = flatten(tree)
        return jsonify({
            "ok": True, "tree": tree,
            "fileCount": sum(x["type"] == "file" for x in items),
            "folderCount": sum(x["type"] == "folder" for x in items),
            "totalSize": folder_size(root)
        })
    except Exception as e:
        return error(e, 404)


@app.get("/api/file/<project>")
def get_file(project):
    try:
        root = project_root(project)
        p = safe_path(root, request.args.get("path", ""))
        if not p.is_file() or p.is_symlink():
            return error("File not found.", 404)
        if p.stat().st_size > MAX_EDITOR_FILE:
            return error("File exceeds the editor's 10 MB limit.")
        content = p.read_text(encoding="utf-8", errors="replace")
        return jsonify({
            "ok": True, "content": content,
            "size": p.stat().st_size, "sizeText": size_text(p.stat().st_size),
            "language": LANGUAGES.get(p.suffix.lower(), "text")
        })
    except Exception as e:
        return error(e, 404)


@app.post("/api/file/<project>")
def save_file(project):
    d = request.get_json(silent=True) or {}
    try:
        root = project_root(project)
        p = safe_path(root, d.get("path", ""))
        content = d.get("content", "")
        if p == root or not isinstance(content, str):
            return error("Invalid file content or path.")
        if len(content.encode("utf-8")) > MAX_EDITOR_FILE:
            return error("File exceeds the editor's 10 MB limit.")
        if p.exists() and p.is_dir():
            return error("Target is a folder.")
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".zihad-tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(p)
        return jsonify({"ok": True, "size": p.stat().st_size, "sizeText": size_text(p.stat().st_size)})
    except Exception as e:
        return error(e)


@app.post("/api/file-create")
def create_file():
    d = request.get_json(silent=True) or {}
    try:
        root = project_root(d.get("project"))
        p = safe_path(root, d.get("path", ""))
        if p == root or p.exists():
            return error("Invalid path or item already exists.")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(d.get("content", "")), encoding="utf-8")
        return jsonify({"ok": True})
    except Exception as e:
        return error(e)


@app.post("/api/folder-create")
def create_folder():
    d = request.get_json(silent=True) or {}
    try:
        root = project_root(d.get("project"))
        p = safe_path(root, d.get("path", ""))
        if p == root:
            return error("Choose a folder name.")
        p.mkdir(parents=True, exist_ok=False)
        return jsonify({"ok": True})
    except Exception as e:
        return error(e)


@app.post("/api/rename")
def rename_item():
    d = request.get_json(silent=True) or {}
    try:
        root = project_root(d.get("project"))
        old = safe_path(root, d.get("path", ""))
        name = safe_name(d.get("name"))
        new = safe_path(old.parent, name)
        if old == root or not old.exists() or old.is_symlink():
            return error("Item not found.")
        if new.exists():
            return error("Target already exists.")
        old.rename(new)
        return jsonify({"ok": True})
    except Exception as e:
        return error(e)


@app.post("/api/delete")
def delete_item():
    d = request.get_json(silent=True) or {}
    try:
        root = project_root(d.get("project"))
        p = safe_path(root, d.get("path", ""))
        if p == root or not p.exists() or p.is_symlink():
            return error("Cannot delete this path.")
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        return jsonify({"ok": True})
    except Exception as e:
        return error(e)


@app.post("/api/copy")
def copy_item():
    d = request.get_json(silent=True) or {}
    try:
        root = project_root(d.get("project"))
        src = safe_path(root, d.get("path", ""))
        if src == root or not src.exists() or src.is_symlink():
            return error("Source not found.")
        dest = src.with_name(src.name + ".copy")
        i = 2
        while dest.exists():
            dest = src.with_name(src.name + f".copy{i}")
            i += 1
        if src.is_dir():
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)
        return jsonify({"ok": True, "path": dest.relative_to(root).as_posix()})
    except Exception as e:
        return error(e)


@app.get("/preview/<project>/<path:relative>")
def preview(project, relative):
    try:
        root = project_root(project)
        p = safe_path(root, relative)
        if not p.is_file() or p.is_symlink():
            abort(404)
        mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        return send_file(p, mimetype=mime, conditional=True)
    except Exception:
        abort(404)


@app.post("/api/terminal")
def terminal():
    d = request.get_json(silent=True) or {}
    try:
        root = project_root(d.get("project"))
        cmd = str(d.get("command", "")).strip()
        if not cmd:
            return error("Enter a command.")
        if len(cmd) > 3000:
            return error("Command too long.")
        # Terminal commands execute with the Termux user's permissions.
        # Keep this server bound to localhost; never expose it publicly.
        return jsonify({"ok": True, **command(cmd, root)})
    except Exception as e:
        return error(e)


@app.post("/api/run")
def run_source():
    d = request.get_json(silent=True) or {}
    try:
        root = project_root(d.get("project"))
        p = safe_path(root, d.get("path", ""))
        if not p.is_file() or p.is_symlink():
            return error("Source file not found.")
        rel = json.dumps(p.relative_to(root).as_posix())
        ext = p.suffix.lower()
        cmds = {
            ".py": f"python {rel}", ".js": f"node {rel}",
            ".mjs": f"node {rel}", ".php": f"php {rel}",
            ".sh": f"bash {rel}", ".bash": f"bash {rel}",
            ".rb": f"ruby {rel}", ".pl": f"perl {rel}",
            ".go": f"go run {rel}",
            ".c": f"gcc {rel} -o .zihad-run && ./.zihad-run",
            ".cpp": f"g++ {rel} -o .zihad-run && ./.zihad-run",
            ".cc": f"g++ {rel} -o .zihad-run && ./.zihad-run",
            ".rs": f"rustc {rel} -o .zihad-run && ./.zihad-run",
            ".java": f"javac {rel} && java -cp . {json.dumps(p.stem)}"
        }
        if ext in (".html", ".htm"):
            return jsonify({"ok": True, "output": "Open the Preview tab to view this HTML file.", "preview": True})
        if ext not in cmds:
            return jsonify({"ok": False, "output": f"No run command configured for {ext or 'this file'}."})
        return jsonify(command(cmds[ext], root))
    except Exception as e:
        return error(e)


@app.post("/api/backup")
def backup():
    d = request.get_json(silent=True) or {}
    try:
        root = project_root(d.get("project"))
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = BACKUPS / f"{root.name}-{stamp}"
        shutil.copytree(root, dest, ignore=shutil.ignore_patterns(".gradle", "build", ".git"))
        n = folder_size(dest)
        return jsonify({"ok": True, "path": str(dest), "size": n, "sizeText": size_text(n)})
    except Exception as e:
        return error(e)


@app.get("/api/backups")
def backups():
    out = []
    for p in sorted(BACKUPS.iterdir(), reverse=True):
        if p.is_dir() and not p.is_symlink():
            n = folder_size(p)
            out.append({"name": p.name, "size": n, "sizeText": size_text(n)})
    return jsonify({"ok": True, "backups": out})


@app.post("/api/restore")
def restore():
    d = request.get_json(silent=True) or {}
    try:
        root = project_root(d.get("project"))
        name = safe_name(d.get("backup"))
        src = safe_path(BACKUPS, name)
        if src.parent != BACKUPS or not src.is_dir() or src.is_symlink():
            return error("Backup not found.")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safety = BACKUPS / f"{root.name}-before-restore-{stamp}"
        shutil.copytree(root, safety, ignore=shutil.ignore_patterns(".gradle", "build", ".git"))
        temp = PROJECTS / (root.name + ".restore-tmp")
        if temp.exists():
            shutil.rmtree(temp)
        shutil.copytree(src, temp)
        shutil.rmtree(root)
        temp.rename(root)
        return jsonify({"ok": True, "safetyBackup": str(safety)})
    except Exception as e:
        return error(e)


@app.get("/api/tools")
def tools():
    checks = [
        "python --version", "node --version", "php --version",
        "java -version", "gradle --version", "git --version",
        "gcc --version", "g++ --version", "go version",
        "rustc --version", "cmake --version"
    ]
    lines = [
        "Zihad Mobile IDE — environment",
        "Python: " + str(shutil.which("python")),
        "Java: " + str(shutil.which("java")),
        "Gradle: " + str(shutil.which("gradle")),
        ""
    ]
    for c in checks:
        r = command(c, BASE, 8)
        first = (r["output"].splitlines() or ["Unavailable"])[0]
        lines.append(("[OK] " if r["ok"] else "[MISSING] ") + c + " — " + first)
    return jsonify({"ok": True, "output": "\n".join(lines)})


@app.post("/api/build")
def build():
    d = request.get_json(silent=True) or {}
    try:
        root = project_root(d.get("project"))
        if not (root / "app" / "build.gradle").is_file() and not (root / "app" / "build.gradle.kts").is_file():
            return jsonify({"ok": False, "output": "This is not an Android Gradle project."})
        gradlew = root / "gradlew"
        if gradlew.is_file():
            cmd = "bash ./gradlew assembleDebug"
        elif shutil.which("gradle"):
            cmd = "gradle assembleDebug"
        else:
            return jsonify({"ok": False, "output": "Gradle is not installed or not in PATH."})
        result = command(cmd, root, 900)
        apk = root / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
        out = {"ok": result["ok"], "output": result["output"], "duration": result["duration"]}
        if result["ok"] and apk.is_file():
            out["apk"] = "/api/apk/" + root.name
            out["apkSize"] = apk.stat().st_size
            out["apkSizeText"] = size_text(apk.stat().st_size)
        elif result["ok"]:
            out["ok"] = False
            out["output"] += "\nAPK was not found at the expected location."
        return jsonify(out)
    except Exception as e:
        return error(e)


@app.get("/api/apk/<project>")
def apk(project):
    try:
        root = project_root(project)
        p = safe_path(root, "app/build/outputs/apk/debug/app-debug.apk")
        if not p.is_file():
            return error("APK not found; build first.", 404)
        return send_file(p, as_attachment=True, download_name=root.name + "-debug.apk")
    except Exception as e:
        return error(e, 404)


@app.post("/api/git")
def git():
    d = request.get_json(silent=True) or {}
    try:
        root = project_root(d.get("project"))
        action = d.get("action")
        cmds = {
            "status": "git status --short --branch",
            "diff": "git diff --",
            "log": "git log -8 --oneline --decorate",
            "branches": "git branch -a",
            "commit": "git add -u && git commit -m " + json.dumps(str(d.get("message") or "IDE update")),
            "pull": "git pull",
            "push": "git push"
        }
        if action not in cmds:
            return error("Unknown Git action.")
        r = command(cmds[action], root, 180)
        return jsonify(r)
    except Exception as e:
        return error(e)


@app.post("/api/sqlite")
def sqlite_query():
    d = request.get_json(silent=True) or {}
    try:
        root = project_root(d.get("project"))
        p = safe_path(root, d.get("path", ""))
        query = str(d.get("query", "")).strip()
        if not p.is_file() or p.suffix.lower() not in (".db", ".sqlite", ".sqlite3"):
            return error("Choose an existing SQLite database file.")
        if not re.match(r"^(SELECT|PRAGMA|EXPLAIN)\b", query, re.I):
            return error("Only SELECT, PRAGMA and EXPLAIN are allowed.")
        con = sqlite3.connect("file:" + str(p) + "?mode=ro", uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        try:
            cur = con.execute(query)
            rows = [dict(r) for r in cur.fetchmany(200)]
            return jsonify({"ok": True, "columns": [x[0] for x in cur.description] if cur.description else [], "rows": rows, "limit": 200})
        finally:
            con.close()
    except Exception as e:
        return error(e)


@app.get("/api/settings")
def get_settings():
    s = read_settings()
    # Never return the saved API key to the browser.
    s.pop("aiKey", None)
    return jsonify({"ok": True, **s})


@app.post("/api/settings")
def set_settings():
    d = request.get_json(silent=True) or {}
    allowed = {"aiEndpoint", "aiModel", "aiKey", "autosaveDelay", "theme"}
    clean = {k: v for k, v in d.items() if k in allowed}
    try:
        if "aiEndpoint" in clean and clean["aiEndpoint"]:
            if not clean["aiEndpoint"].startswith("https://"):
                return error("AI endpoint must use HTTPS.")
        save_settings(clean)
        return jsonify({"ok": True})
    except Exception as e:
        return error(e)


@app.post("/api/ai")
def ai():
    d = request.get_json(silent=True) or {}
    settings = read_settings()
    endpoint = settings.get("aiEndpoint", "")
    key = settings.get("aiKey", "")
    model = settings.get("aiModel", "")
    prompt = str(d.get("prompt", "")).strip()
    if not endpoint or not key or not model:
        return error("Configure an HTTPS AI endpoint, model and API key in Settings.")
    if not prompt:
        return error("Prompt is empty.")
    if len(prompt) > 50000:
        return error("Prompt is too long.")
    try:
        body = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a careful coding assistant. Explain risks and do not claim code was tested unless it was."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2
        }).encode("utf-8")
        req = urllib.request.Request(
            endpoint, data=body, method="POST",
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + key}
        )
        with urllib.request.urlopen(req, timeout=60) as res:
            payload = json.loads(res.read().decode("utf-8", "replace"))
        answer = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not answer:
            return error("AI provider returned no message.")
        return jsonify({"ok": True, "answer": answer})
    except urllib.error.HTTPError as e:
        return error("AI provider HTTP error: " + str(e.code))
    except Exception as e:
        return error("AI request failed: " + str(e))


@app.post("/api/http-test")
def http_test():
    d = request.get_json(silent=True) or {}
    url = str(d.get("url", "")).strip()
    method = str(d.get("method", "GET")).upper()
    if method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        return error("Unsupported HTTP method.")
    if not url.startswith("https://"):
        return error("Only HTTPS URLs are allowed.")
    try:
        body = d.get("body", "")
        data = body.encode("utf-8") if body and method in ("POST", "PUT", "PATCH") else None
        req = urllib.request.Request(
            url, data=data, method=method,
            headers={"Content-Type": "application/json", "User-Agent": "ZihadMobileIDE/1.0"}
        )
        with urllib.request.urlopen(req, timeout=20) as res:
            text = res.read(500000).decode("utf-8", "replace")
            return jsonify({"ok": True, "status": res.status, "headers": dict(res.headers), "body": text})
    except urllib.error.HTTPError as e:
        try:
            body = e.read(200000).decode("utf-8", "replace")
        except Exception:
            body = ""
        return jsonify({"ok": False, "status": e.code, "body": body})
    except Exception as e:
        return error(e)


@app.errorhandler(413)
def too_large(_e):
    return jsonify({"ok": False, "error": "Request too large."}), 413


@app.errorhandler(404)
def missing(_e):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "API endpoint not found."}), 404
    return "Not found", 404


if __name__ == "__main__":
    print("=" * 48)
    print("⚡ ZIHAD MOBILE IDE ULTRA PRO MAX")
    print("Projects:", PROJECTS)
    print("Backups :", BACKUPS)
    print("Open    : http://127.0.0.1:" + str(PORT))
    print("Security: localhost only")
    print("=" * 48)
    app.run(host=HOST, port=PORT, debug=False, threaded=True)
