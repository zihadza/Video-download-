# ============================================================
# ZIHAD MOBILE IDE v15.0 — ULTIMATE PRO EDITION
# PART 1/3 : Imports + Config + Helpers + Timeouts +
#            Project Details (50 fields) + Templates + Home
# ============================================================
from flask import Flask, jsonify, request, send_file, Response
from pathlib import Path
import json, re, subprocess, shutil, os, threading, time, uuid, zipfile, io, sys, base64, hashlib, sqlite3
import urllib.request, urllib.error
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
BUILD_LOG_CACHE_DIR = BASE_DIR / "build_logs_cache"
PROJECT_CACHE_DIR   = BASE_DIR / "project_cache"
CLIPBOARD_DIR  = BASE_DIR / "clipboard"
TRASH_DIR      = BASE_DIR / "trash"
TRASH_META_FILE = BASE_DIR / "trash_meta.json"

for d in [PROJECTS_DIR, APKS_DIR, HISTORY_DIR, BACKUP_DIR,
          SIGNED_DIR, PLUGINS_DIR, KANBAN_DIR, NOTES_DIR,
          BUILD_LOG_CACHE_DIR, PROJECT_CACHE_DIR,
          CLIPBOARD_DIR, TRASH_DIR]:
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
IDE_SETTINGS_FILE   = BASE_DIR / "ide_settings.json"
TIMEOUTS_FILE       = BASE_DIR / "timeouts.json"
EDITOR_THEMES_FILE  = BASE_DIR / "editor_themes.json"
APP_META_FILE       = BASE_DIR / "app_meta.json"

PORT = 3097
APP_VERSION = "15.0.0"
APP_ICON_SVG = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E%E2%9A%A1%3C/text%3E%3C/svg%3E"
TERMUX_PREFIX = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
BUILDS = {}
LOGCAT_PROCS = {}
PTY_SESSIONS = {}
AUTO_BUILD_LOCK = {}

# Session clipboard (in-memory, per process)
CLIPBOARD = {
    "items": [],       # list of {"source_path": str, "name": str, "is_folder": bool, "project": str}
    "action": None,    # "copy" | "cut"
    "project": None,
    "created": 0,
}

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
    ".sql": {"name": "SQL", "run": None, "check": None},
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

# ============================================================
#  TIMEOUT MANAGEMENT SYSTEM
# ============================================================
DEFAULT_TIMEOUTS = {
    "wrapper_generation": 300,
    "build_timeout": 1800,
    "build_poll_interval": 700,
    "run_command": 300,
    "run_code": 120,
    "check_file": 60,
    "scan_errors": 30,
    "adb_install": 90,
    "git_push": 180,
    "git_pull": 180,
    "git_fetch": 180,
    "pty_poll_interval": 300,
    "logcat_poll_interval": 700,
    "notif_poll_interval": 3000,
    "system_info_poll": 15000,
    "auto_save_delay": 2500,
    "auto_build_debounce": 4,
    "download_jar_timeout": 120,
    "build_heartbeat": 30,
    "build_ui_line_limit": 1000,
}

TIMEOUT_LABELS = {
    "wrapper_generation":  ("Gradle Wrapper Generation", "Time to generate/download Gradle wrapper", 30, 600, "fa-download"),
    "build_timeout":       ("APK Build Timeout", "Max time for full build", 300, 7200, "fa-hammer"),
    "build_poll_interval": ("Build Log Poll Interval", "UI refresh rate during build (ms)", 300, 3000, "fa-rotate"),
    "run_command":         ("Terminal Command Timeout", "Max time for shell commands", 30, 3600, "fa-terminal"),
    "run_code":            ("Run Code Timeout", "Max time for code execution", 30, 900, "fa-play"),
    "check_file":          ("File Check Timeout", "Max time for single file check", 10, 300, "fa-magnifying-glass"),
    "scan_errors":         ("Error Scan Timeout", "Max time per file during scan", 10, 180, "fa-bug"),
    "adb_install":         ("ADB Install Timeout", "Max time for adb install", 30, 600, "fa-mobile-button"),
    "git_push":            ("Git Push Timeout", "Max time for git push", 30, 1800, "fa-cloud-arrow-up"),
    "git_pull":            ("Git Pull Timeout", "Max time for git pull", 30, 1800, "fa-cloud-arrow-down"),
    "git_fetch":           ("Git Fetch Timeout", "Max time for git fetch", 30, 1800, "fa-cloud"),
    "pty_poll_interval":   ("PTY Poll Interval", "PTY refresh rate (ms)", 100, 2000, "fa-terminal"),
    "logcat_poll_interval":("Logcat Poll Interval", "Logcat refresh (ms)", 300, 3000, "fa-list-ul"),
    "notif_poll_interval": ("Notification Poll", "Notification refresh (ms)", 1000, 10000, "fa-bell"),
    "system_info_poll":    ("System Info Poll", "System monitor refresh (ms)", 3000, 60000, "fa-microchip"),
    "auto_save_delay":     ("Auto Save Delay", "Delay before auto-save (ms)", 500, 10000, "fa-floppy-disk"),
    "auto_build_debounce": ("Auto Build Debounce", "Delay between auto-builds (sec)", 1, 60, "fa-robot"),
    "download_jar_timeout":("JAR Download Timeout", "Max time to download wrapper JAR", 30, 300, "fa-file-arrow-down"),
    "build_heartbeat":     ("Build Heartbeat", "If no output in N sec → show 'still working'", 10, 120, "fa-heart-pulse"),
    "build_ui_line_limit": ("Build UI Line Limit", "Max lines shown in build UI (older removed, cache keeps all)", 200, 5000, "fa-list"),
}

def get_timeouts():
    saved = load_json(TIMEOUTS_FILE, {})
    merged = dict(DEFAULT_TIMEOUTS)
    if isinstance(saved, dict):
        for k, v in saved.items():
            if k in DEFAULT_TIMEOUTS and isinstance(v, (int, float)):
                merged[k] = max(1, int(v))
    return merged

def get_timeout(key, fallback=None):
    return get_timeouts().get(key, fallback or DEFAULT_TIMEOUTS.get(key, 60))

def save_timeouts(data):
    current = get_timeouts()
    for k, v in data.items():
        if k in DEFAULT_TIMEOUTS:
            try:
                current[k] = max(1, int(float(v)))
            except:
                pass
    save_json(TIMEOUTS_FILE, current)
    return current

# ============================================================
#  BUILD LOG CACHE (only last, truncated, configurable)
# ============================================================
LOG_MAX_LINES = 5000  # hard cap in cache

def cache_build_log(project_name, lines):
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", project_name)
    cache_file = BUILD_LOG_CACHE_DIR / f"{safe}.log"
    meta_file = BUILD_LOG_CACHE_DIR / f"{safe}.meta.json"
    if len(lines) > LOG_MAX_LINES:
        lines = lines[-LOG_MAX_LINES:]
    try:
        cache_file.write_text("\n".join(lines), encoding="utf-8")
        save_json(meta_file, {
            "project": project_name, "saved_at": time.time(),
            "total_lines": len(lines), "truncated": len(lines) >= LOG_MAX_LINES
        })
        return True
    except Exception as e:
        print(f"Log cache error: {e}")
        return False

def get_cached_log(project_name):
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", project_name)
    cache_file = BUILD_LOG_CACHE_DIR / f"{safe}.log"
    meta_file = BUILD_LOG_CACHE_DIR / f"{safe}.meta.json"
    if not cache_file.exists():
        return {"lines": [], "meta": None}
    try:
        lines = cache_file.read_text(encoding="utf-8").split("\n")
        return {"lines": lines, "meta": load_json(meta_file, None)}
    except:
        return {"lines": [], "meta": None}

def clear_cached_log(project_name):
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", project_name)
    for ext in [".log", ".meta.json"]:
        f = BUILD_LOG_CACHE_DIR / f"{safe}{ext}"
        if f.exists():
            try: f.unlink()
            except: pass

# ============================================================
#  VERSION VALIDATION
# ============================================================
def validate_version_code(v):
    try:
        n = int(v)
        return 1 <= n < 2147483647
    except:
        return False

def validate_version_name(v):
    if not v or not isinstance(v, str):
        return False
    return re.match(r"^\d+(\.\d+){1,3}$", v.strip()) is not None

# ============================================================
#  STANDARD HELPERS
# ============================================================
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
    items = [i for i in data.get("items", []) if not (i["project"] == project and i["path"] == path)]
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
        "id": str(uuid.uuid4())[:8], "project": project, "title": title,
        "body": body, "kind": kind, "ts": time.time(), "read": False,
        "app_name": "Zihad IDE", "app_version": APP_VERSION,
        "app_icon": APP_ICON_SVG,
    })
    save_json(NOTIF_FILE, {"items": notifs[:200]})

# ============================================================
#  AUTO-DOWNLOAD GRADLE WRAPPER (fixes timeout)
# ============================================================
def ensure_wrapper_ready(project, gradle_ver="8.11.1", log_callback=None):
    """Ensure gradle-wrapper.jar + gradlew exist. Downloads directly if missing."""
    wrapper_dir = project / "gradle" / "wrapper"
    wrapper_dir.mkdir(parents=True, exist_ok=True)
    wrapper_jar = wrapper_dir / "gradle-wrapper.jar"
    gradlew = project / "gradlew"
    
    if wrapper_jar.exists() and wrapper_jar.stat().st_size > 10000 and gradlew.exists():
        if log_callback: log_callback(f"✓ Wrapper ready (v{gradle_ver})")
        return True
    
    if log_callback: log_callback(f"📥 Downloading Gradle wrapper JAR (v{gradle_ver})...")
    try:
        url = f"https://raw.githubusercontent.com/gradle/gradle/v{gradle_ver}.0/gradle/wrapper/gradle-wrapper.jar"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=get_timeout("download_jar_timeout")) as r:
            wrapper_jar.write_bytes(r.read())
        if log_callback: log_callback("✓ Wrapper JAR downloaded")
    except Exception as e:
        if log_callback: log_callback(f"⚠️ JAR download failed: {e}")
        try:
            if log_callback: log_callback("⚙️ Trying gradle wrapper command...")
            subprocess.run(
                f"gradle wrapper --gradle-version {gradle_ver}",
                shell=True, cwd=str(project), capture_output=True,
                timeout=get_timeout("wrapper_generation")
            )
            if log_callback: log_callback("✓ Wrapper generated via command")
        except subprocess.TimeoutExpired:
            if log_callback: log_callback("❌ Wrapper generation timed out")
            return False
        except Exception as e:
            if log_callback: log_callback(f"❌ Wrapper failed: {e}")
            return False
    
    for fname in ["gradlew", "gradlew.bat"]:
        fp = project / fname
        if not fp.exists():
            try:
                url = f"https://raw.githubusercontent.com/gradle/gradle/v{gradle_ver}.0/{fname}"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=get_timeout("download_jar_timeout")) as r:
                    fp.write_bytes(r.read())
                if fname == "gradlew":
                    fp.chmod(0o755)
            except:
                pass
    
    props = wrapper_dir / "gradle-wrapper.properties"
    props_content = f"""distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\\://services.gradle.org/distributions/gradle-{gradle_ver}-bin.zip
networkTimeout=120000
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
"""
    props.write_text(props_content, encoding="utf-8")
    
    return wrapper_jar.exists() and wrapper_jar.stat().st_size > 10000

# ============================================================
#  PROJECT DETAILS (50 FIELDS — UPGRADED)
# ============================================================
SKIP_DIRS_DETAIL = {"build", ".gradle", ".git", "node_modules", ".cxx", "transforms-3", ".idea"}

def get_project_details(project):
    """Return 50 fields of project info. Used by /api/project-details."""
    details = {
        # 1-10: App Info
        "name": project.name,                                         # 1
        "path": str(project),                                         # 2
        "package": "?",                                               # 3
        "language": "?",                                              # 4
        "version": {"code": "?", "name": "?"},                        # 5,6
        "sdk": {"compile": "?", "min": "?", "target": "?"},           # 7,8,9
        "template": "?",                                              # 10
        "created": "?",                                               # 11 (extra)
        # 12-20: File Stats
        "total_files": 0,
        "total_folders": 0,
        "total_size": 0,
        "total_size_human": "0 B",
        "code_files": 0,
        "resource_files": 0,
        "asset_files": 0,
        "config_files": 0,
        "build_files": 0,
        "generated_files": 0,
        # 21-28: Language breakdown
        "language_stats": {},
        # 29-35: Dependencies
        "dependencies": [],
        "plugins": [],
        "third_party": [],
        # 36-43: Build info
        "build_info": {
            "last_build_status": "none",
            "last_build_time": None,
            "last_build_duration": 0,
            "last_apk_size": 0,
            "total_builds": 0,
            "success_rate": 0,
            "avg_build_time": 0,
            "most_common_error": None,
        },
        # 44-50: Security & Config
        "manifest_info": {"permissions": [], "activities": [], "services": [], "receivers": []},
        "keystore_configured": False,
        "firebase_configured": False,
        "icon": None,
        # Extra
        "history": [],
        "has_wrapper": False,
        "has_local_props": False,
        "has_git": False,
    }

    # Read project.json for language/template/created
    info_file = project / "project.json"
    if info_file.exists():
        try:
            info = json.loads(info_file.read_text(encoding="utf-8"))
            details["language"] = info.get("language", "?")
            details["template"] = info.get("template", "?")
            details["created"] = info.get("created", "?")
            details["version"]["code"] = info.get("versionCode", "?")
            details["version"]["name"] = info.get("versionName", "?")
            details["package"] = info.get("package", "?")
        except:
            pass

    # File stats walk
    ext_counts, ext_sizes = {}, {}
    code_ext = set(LANGUAGES.keys())
    resource_ext = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".xml", ".json"}
    asset_ext = {".ttf", ".otf", ".woff", ".woff2", ".mp3", ".wav", ".mp4", ".webm"}
    config_ext = {".properties", ".gradle", ".pro", ".json", ".gitignore", ".env"}
    build_names = {"build.gradle", "settings.gradle", "gradle.properties", "gradlew", "gradle-wrapper.jar", "gradle-wrapper.properties", "proguard-rules.pro"}

    try:
        for p in project.rglob("*"):
            parts = set(p.parts)
            if parts & SKIP_DIRS_DETAIL:
                # Still count build files even in build dir
                continue
            try:
                if p.is_file():
                    details["total_files"] += 1
                    sz = p.stat().st_size
                    details["total_size"] += sz
                    ext = p.suffix.lower() or "_noext"
                    ext_counts[ext] = ext_counts.get(ext, 0) + 1
                    ext_sizes[ext] = ext_sizes.get(ext, 0) + sz
                    # Categorize
                    if ext in code_ext:
                        details["code_files"] += 1
                    elif ext in resource_ext:
                        details["resource_files"] += 1
                    elif ext in asset_ext:
                        details["asset_files"] += 1
                    if ext in config_ext or p.name in build_names:
                        details["config_files"] += 1
                    if p.name in build_names:
                        details["build_files"] += 1
                elif p.is_dir():
                    details["total_folders"] += 1
            except:
                continue
    except:
        pass

    details["total_size_human"] = human_size(details["total_size"])

    # Language breakdown
    lang_map = {
        ".java": "Java", ".kt": "Kotlin", ".xml": "XML", ".gradle": "Gradle",
        ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
        ".html": "HTML", ".css": "CSS", ".json": "JSON", ".md": "Markdown",
        ".c": "C", ".cpp": "C++", ".h": "C Header", ".go": "Go", ".rs": "Rust",
        ".rb": "Ruby", ".php": "PHP", ".sh": "Shell", ".sql": "SQL",
        ".properties": "Properties", ".txt": "Text"
    }
    total_code = sum(ext_counts.get(ext, 0) for ext in lang_map.keys())
    if total_code > 0:
        for ext, lang in lang_map.items():
            cnt = ext_counts.get(ext, 0)
            if cnt > 0:
                details["language_stats"][lang] = {
                    "count": cnt,
                    "percent": round(cnt / total_code * 100, 1),
                    "size": human_size(ext_sizes.get(ext, 0))
                }

    # Gradle file parsing
    gradle_file = project / "app" / "build.gradle"
    if gradle_file.exists():
        try:
            txt = gradle_file.read_text(encoding="utf-8", errors="replace")
            matches = re.findall(r"(?:implementation|api|compileOnly|runtimeOnly)\s+['\"]([^'\"]+)['\"]", txt)
            for m in matches:
                details["dependencies"].append({"name": m, "size": "~"})
            plugins = re.findall(r"id\s+['\"]([^'\"]+)['\"]\s+version\s+['\"]([^'\"]+)['\"]", txt)
            for m in plugins:
                details["plugins"].append({"type": "plugin", "name": m[0], "version": m[1]})
            vc = re.search(r"versionCode\s+(\d+)", txt)
            vn = re.search(r'versionName\s+"([^"]+)"', txt)
            if vc: details["version"]["code"] = vc.group(1)
            if vn: details["version"]["name"] = vn.group(1)
            ns = re.search(r'namespace\s+["\']([^"\']+)["\']', txt)
            if ns: details["package"] = ns.group(1)
            cs = re.search(r"compileSdk\s+(\d+)", txt)
            tgt = re.search(r"targetSdk\s+(\d+)", txt)
            mins = re.search(r"minSdk\s+(\d+)", txt)
            if cs: details["sdk"]["compile"] = cs.group(1)
            if tgt: details["sdk"]["target"] = tgt.group(1)
            if mins: details["sdk"]["min"] = mins.group(1)
        except:
            pass

    # Manifest parsing
    manifest_file = project / "app" / "src" / "main" / "AndroidManifest.xml"
    if manifest_file.exists():
        try:
            txt = manifest_file.read_text(encoding="utf-8", errors="replace")
            icon_m = re.search(r'android:icon="@([^"]+)"', txt)
            if icon_m: details["icon"] = icon_m.group(1)
            details["manifest_info"]["permissions"] = re.findall(r'<uses-permission android:name="([^"]+)"', txt)
            details["manifest_info"]["activities"] = re.findall(r'<activity android:name="([^"]+)"', txt)
            details["manifest_info"]["services"] = re.findall(r'<service android:name="([^"]+)"', txt)
            details["manifest_info"]["receivers"] = re.findall(r'<receiver android:name="([^"]+)"', txt)
        except:
            pass

    # Firebase check
    details["firebase_configured"] = (project / "app" / "google-services.json").exists()

    # Keystore check
    ks = load_json(KEYSTORE_FILE, {})
    details["keystore_configured"] = bool(ks.get("storeFile"))

    # Wrapper / local.props / git
    details["has_wrapper"] = (project / "gradlew").exists()
    details["has_local_props"] = (project / "local.properties").exists()
    details["has_git"] = (project / ".git").exists()

    # Build info from history
    hist = load_json(BUILD_HISTORY, {}).get(project.name, [])
    details["history"] = hist[:10]
    if hist:
        details["build_info"]["total_builds"] = len(hist)
        last = hist[0]
        details["build_info"]["last_build_status"] = "success" if last.get("success") else "fail"
        details["build_info"]["last_build_time"] = last.get("ts")
        details["build_info"]["last_build_duration"] = last.get("duration", 0)
        details["build_info"]["last_apk_size"] = last.get("apk_size", 0)
        ok = sum(1 for h in hist if h.get("success"))
        details["build_info"]["success_rate"] = round(ok / len(hist) * 100, 1)
        details["build_info"]["avg_build_time"] = round(sum(h.get("duration", 0) for h in hist) / len(hist), 1)
        # Most common error
        freq = load_json(ERROR_FREQ_FILE, {}).get(project.name, {})
        if freq:
            top = max(freq.items(), key=lambda x: x[1])
            details["build_info"]["most_common_error"] = {"text": top[0], "count": top[1]}

    return details

# ============================================================
#  CLIPBOARD HELPERS (for copy/paste file operations)
# ============================================================
def clipboard_set(items, action, project):
    CLIPBOARD["items"] = items
    CLIPBOARD["action"] = action
    CLIPBOARD["project"] = project
    CLIPBOARD["created"] = time.time()

def clipboard_clear():
    CLIPBOARD["items"] = []
    CLIPBOARD["action"] = None
    CLIPBOARD["project"] = None

def clipboard_info():
    return {
        "count": len(CLIPBOARD["items"]),
        "action": CLIPBOARD["action"],
        "project": CLIPBOARD["project"],
        "items": CLIPBOARD["items"][:20],
    }

# ============================================================
#  TRASH HELPERS (soft delete with undo)
# ============================================================
def trash_add(project_name, file_path, is_folder):
    """Move a file/folder to trash, record metadata."""
    meta = load_json(TRASH_META_FILE, {"items": []})
    entry_id = str(uuid.uuid4())[:12]
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", Path(file_path).name)
    dest = TRASH_DIR / f"{entry_id}__{safe_name}"
    entry = {
        "id": entry_id,
        "project": project_name,
        "orig_path": file_path,
        "name": Path(file_path).name,
        "is_folder": is_folder,
        "deleted_at": time.time(),
        "stored_as": dest.name,
    }
    meta["items"].insert(0, entry)
    meta["items"] = meta["items"][:200]
    save_json(TRASH_META_FILE, meta)
    return entry, dest

def trash_restore(entry_id):
    meta = load_json(TRASH_META_FILE, {"items": []})
    item = next((x for x in meta["items"] if x["id"] == entry_id), None)
    if not item:
        return None
    project = safe_project(item["project"])
    if not project:
        return None
    dest = TRASH_DIR / item["stored_as"]
    target = safe_subpath(project, item["orig_path"])
    if not dest.exists() or not target:
        return None
    if target.exists():
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        if item["is_folder"]:
            shutil.move(str(dest), str(target))
        else:
            shutil.move(str(dest), str(target))
        meta["items"] = [x for x in meta["items"] if x["id"] != entry_id]
        save_json(TRASH_META_FILE, meta)
        return item
    except Exception as e:
        print(f"Trash restore error: {e}")
        return None

# ============================================================
#  PROJECT CREATION WITH ALL TEMPLATES
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
        write_file(java_dir / "HomeActivity.java", home_java)
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
        android:icon="@mipmap/ic_launcher"
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
    
    ide_settings = load_json(IDE_SETTINGS_FILE, {"gradleVersion": "8.11.1", "compileSdk": "34"})
    compile_sdk = ide_settings.get("compileSdk", "34")
    target_sdk = ide_settings.get("targetSdk", compile_sdk)
    min_sdk = ide_settings.get("minSdk", "23")
    
    app_gradle = f'''plugins {{
    id "com.android.application"
}}
android {{
    namespace "{package}"
    compileSdk {compile_sdk}
    defaultConfig {{
        applicationId "{package}"
        minSdk {min_sdk}
        targetSdk {target_sdk}
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

dependencies {{
    implementation 'androidx.appcompat:appcompat:1.6.1'
    implementation 'com.google.android.material:material:1.11.0'
    implementation 'androidx.constraintlayout:constraintlayout:2.1.4'
}}
'''
    gradle_props = '''org.gradle.jvmargs=-Xmx2048m -XX:MaxMetaspaceSize=512m
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
    
    gradle_ver = ide_settings.get("gradleVersion", "8.11.1")
    ensure_wrapper_ready(project, gradle_ver)
    
    return project

# ============================================================
#  HOME PAGE — UPGRADED with UI improvements
# ============================================================
HOME_HTML = r'''<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>Zihad Mobile IDE v15</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
<style>
:root{--bg:#070b14;--card:rgba(17,24,39,.85);--border:rgba(55,65,81,.6);--primary:#3b82f6;--text:#f1f5f9;--muted:#94a3b8;--radius:18px}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;min-height:100vh;background-image:radial-gradient(ellipse at 20% 20%,rgba(59,130,246,.12) 0%,transparent 50%),radial-gradient(ellipse at 80% 80%,rgba(139,92,246,.1) 0%,transparent 50%)}
header{padding:16px 20px;background:rgba(15,23,42,.9);backdrop-filter:blur(20px);border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:50;gap:8px;flex-wrap:wrap}
header h1{font-size:1.15rem;font-weight:700;background:linear-gradient(135deg,#60a5fa,#a78bfa);-webkit-background-clip:text;-webkit-text-fill-color:transparent;display:flex;align-items:center;gap:8px}
header h1 i{color:#60a5fa;-webkit-text-fill-color:initial}
.container{padding:20px;max-width:720px;margin:0 auto}
.card{background:var(--card);backdrop-filter:blur(16px);border:1px solid var(--border);border-radius:var(--radius);padding:20px;margin-bottom:18px;box-shadow:0 8px 32px rgba(0,0,0,.3);transition:all .2s}
.card:hover{box-shadow:0 12px 40px rgba(0,0,0,.4)}
h2{font-size:1.05rem;margin-bottom:12px;color:#e2e8f0;display:flex;align-items:center;gap:8px}
h2 i{color:#60a5fa}
.status-dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#22c55e;margin-right:8px;box-shadow:0 0 10px #22c55e;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
button{border:0;border-radius:12px;padding:11px 16px;margin:4px;font-weight:600;font-size:13px;cursor:pointer;color:#fff;display:inline-flex;align-items:center;gap:6px;transition:transform .15s}
button:active{transform:scale(.96)}
.btn-primary{background:linear-gradient(135deg,#3b82f6,#2563eb)}
.btn-success{background:linear-gradient(135deg,#22c55e,#16a34a)}
.btn-danger{background:linear-gradient(135deg,#ef4444,#dc2626)}
.btn-ghost{background:rgba(55,65,81,.6);border:1px solid var(--border)}
.btn-purple{background:linear-gradient(135deg,#8b5cf6,#7c3aed)}
.btn-orange{background:linear-gradient(135deg,#f59e0b,#d97706)}
input,select{width:100%;padding:14px 16px;margin:8px 0;border-radius:12px;border:1px solid var(--border);background:rgba(8,15,28,.8);color:var(--text);font-size:14px;outline:none;transition:border .2s}
input:focus,select:focus{border-color:var(--primary)}
.project{background:rgba(8,15,28,.6);border:1px solid var(--border);border-radius:14px;padding:16px;margin:10px 0;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;transition:transform .15s}
.project:hover{transform:translateX(2px)}
.project-info{flex:1;min-width:160px}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600;margin-left:6px;background:rgba(59,130,246,.2);color:#93c5fd}
.hidden{display:none!important}
.toast-container{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);z-index:9999;display:flex;flex-direction:column;gap:8px;pointer-events:none}
.toast{background:rgba(15,23,42,.95);border:1px solid var(--border);color:#fff;padding:12px 20px;border-radius:14px;font-size:13px;display:flex;align-items:center;gap:8px;animation:slideUp .3s}
@keyframes slideUp{from{transform:translateY(20px);opacity:0}}
.toast.success{border-color:rgba(34,197,94,.5)}.toast.error{border-color:rgba(239,68,68,.5)}
.fab{position:fixed;bottom:28px;right:24px;width:58px;height:58px;border-radius:50%;background:linear-gradient(135deg,#3b82f6,#8b5cf6);display:flex;align-items:center;justify-content:center;font-size:24px;color:#fff;border:0;z-index:40;box-shadow:0 8px 30px rgba(139,92,246,.6);transition:transform .2s}
.fab:active{transform:scale(.9) rotate(90deg)}
.template-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:12px 0}
.template-card{background:rgba(8,15,28,.7);border:2px solid var(--border);border-radius:14px;padding:12px 8px;text-align:center;cursor:pointer;font-size:12px;transition:all .2s}
.template-card.active{border-color:var(--primary);background:rgba(59,130,246,.12);transform:scale(1.02)}
.template-card span{font-size:22px;display:block;margin-bottom:6px}
.apk-item{background:rgba(8,15,28,.55);border:1px solid var(--border);border-radius:12px;padding:12px;margin:7px 0;display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap}
body.light{--bg:#f1f5f9;--card:#fff;--border:#cbd5e1;--text:#0f172a;--muted:#64748b;background-image:none}
body.light .card{background:#fff;color:#0f172a}
body.light input,body.light select{background:#f8fafc;color:#0f172a}
body.light header{background:#fff;color:#0f172a}
body.light .project,body.light .apk-item,body.light .template-card{background:#f8fafc;color:#0f172a}
.settings-list{display:flex;flex-direction:column;gap:10px}
.setting-item{display:flex;justify-content:space-between;align-items:center;padding:12px 0;border-bottom:1px solid var(--border);font-size:13px;gap:10px}
.setting-item:last-child{border-bottom:0}
.setting-item .label-wrap{flex:1;display:flex;gap:10px;align-items:center}
.setting-item .setting-icon{color:#60a5fa;font-size:16px;width:22px;text-align:center;flex-shrink:0}
.setting-item label{color:var(--text);font-weight:500}
.setting-item small{display:block;color:var(--muted);font-size:11px;margin-top:2px}
.setting-item input[type="number"],.setting-item input[type="text"],.setting-item select{width:110px;padding:8px 10px;margin:0;font-size:12px;flex-shrink:0}
.setting-item input[type="checkbox"]{width:auto;padding:0;margin:0}
.tabs{display:flex;gap:6px;margin-bottom:14px;border-bottom:1px solid var(--border);overflow-x:auto}
.tab{padding:10px 16px;font-size:13px;font-weight:600;cursor:pointer;color:var(--muted);border-bottom:2px solid transparent;white-space:nowrap;transition:color .15s}
.tab.active{color:#60a5fa;border-bottom-color:#60a5fa}
.skeleton{background:linear-gradient(90deg,#1f2937 25%,#374151 50%,#1f2937 75%);background-size:200% 100%;animation:shimmer 1.5s infinite;border-radius:8px}
@keyframes shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}
</style></head>
<body>
<header>
  <h1><i class="fa-solid fa-bolt"></i> Zihad IDE v15</h1>
  <div style="display:flex;gap:2px;flex-wrap:wrap">
    <button class="btn-ghost" onclick="toggleTheme()" id="themeBtn"><i class="fa-solid fa-moon"></i></button>
    <button class="btn-ghost" onclick="openSettings()" title="Settings"><i class="fa-solid fa-gear"></i></button>
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
    <div id="sysStats" style="margin-top:12px;display:grid;grid-template-columns:1fr 1fr;gap:8px"></div>
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
    <div id="projects">
      <div class="skeleton" style="height:60px;margin:10px 0"></div>
      <div class="skeleton" style="height:60px;margin:10px 0"></div>
    </div>
  </div>
</div>
<button class="fab" onclick="showCreate()"><i class="fa-solid fa-plus"></i></button>

<!-- Settings Modal -->
<div id="settingsModal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.85);z-index:999;overflow-y:auto;padding:20px">
  <div style="max-width:600px;margin:0 auto;background:#111827;border-radius:20px;padding:20px;border:1px solid #374151">
    <h2 style="margin-bottom:14px"><i class="fa-solid fa-gear"></i> IDE Settings</h2>
    <div class="tabs">
      <div class="tab active" onclick="switchSettingsTab('general',this)">General</div>
      <div class="tab" onclick="switchSettingsTab('build',this)">Build</div>
      <div class="tab" onclick="switchSettingsTab('timeouts',this)">Timeouts</div>
    </div>
    
    <div id="tab-general" class="settings-content">
      <div class="setting-item"><div class="label-wrap"><i class="fa-solid fa-cube setting-icon"></i><div><label>Compile SDK</label><small>Android API level (21-35)</small></div></div><input type="number" id="set_compileSdk" min="21" max="35" value="34"></div>
      <div class="setting-item"><div class="label-wrap"><i class="fa-solid fa-crosshairs setting-icon"></i><div><label>Target SDK</label><small>Target API level (21-35)</small></div></div><input type="number" id="set_targetSdk" min="21" max="35" value="34"></div>
      <div class="setting-item"><div class="label-wrap"><i class="fa-solid fa-arrow-down setting-icon"></i><div><label>Min SDK</label><small>Minimum API (21-30)</small></div></div><input type="number" id="set_minSdk" min="21" max="30" value="23"></div>
      <div class="setting-item"><div class="label-wrap"><i class="fa-solid fa-cogs setting-icon"></i><div><label>Gradle Version</label><small>e.g. 8.11.1</small></div></div><input type="text" id="set_gradleVersion" value="8.11.1"></div>
    </div>
    
    <div id="tab-build" class="settings-content" style="display:none">
      <div class="setting-item"><div class="label-wrap"><i class="fa-solid fa-robot setting-icon"></i><div><label>Auto-Build on Save</label><small>Trigger build when files change</small></div></div><input type="checkbox" id="set_autoBuild"></div>
      <div class="setting-item"><div class="label-wrap"><i class="fa-solid fa-clock setting-icon"></i><div><label>Build Debounce (sec)</label><small>Delay between auto-builds</small></div></div><input type="number" id="set_autoBuildDebounce" min="1" max="60" value="4"></div>
    </div>
    
    <div id="tab-timeouts" class="settings-content" style="display:none">
      <p style="font-size:12px;color:#94a3b8;margin-bottom:12px">সব timeout এখান থেকে কন্ট্রোল করা যাবে। সব project এ apply হবে।</p>
      <div id="timeoutsList"></div>
    </div>
    
    <div style="display:flex;gap:8px;margin-top:20px">
      <button class="btn-success" style="flex:1" onclick="saveSettings()"><i class="fa-solid fa-check"></i> Save All</button>
      <button class="btn-ghost" onclick="closeSettings()">Cancel</button>
    </div>
  </div>
</div>

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
async function status(){try{var r=await fetch("/api/status");var d=await r.json();document.getElementById("status").innerText="Port "+d.port+" • "+d.projects+" projects • "+d.language_count+" languages • v"+d.version;var si=await fetch("/api/system-info");var sd=await si.json();document.getElementById("sysStats").innerHTML='<div style="background:rgba(8,15,28,.6);padding:10px;border-radius:10px"><small style="color:#94a3b8;font-size:10px">DISK</small><div style="font-size:14px;font-weight:700;color:#60a5fa">'+(sd.disk_percent||0)+'%</div></div><div style="background:rgba(8,15,28,.6);padding:10px;border-radius:10px"><small style="color:#94a3b8;font-size:10px">UPTIME</small><div style="font-size:14px;font-weight:700;color:#4ade80">'+(sd.uptime||"?")+'</div></div>'}catch(e){document.getElementById("status").innerText="Offline"}}
async function loadProjects(){try{var r=await fetch("/api/projects");var d=await r.json();var box=document.getElementById("projects");if(!d.projects.length){box.innerHTML='<p style="color:#94a3b8;text-align:center;padding:20px"><i class="fa-solid fa-inbox"></i><br>No projects yet</p>';return}box.innerHTML="";d.projects.forEach(function(p){var div=document.createElement("div");div.className="project";div.innerHTML='<div class="project-info"><b><i class="fa-solid fa-mobile-screen-button"></i> '+esc(p.name)+'</b><span class="badge">'+esc(p.language||"?")+'</span><br><small style="color:#94a3b8">'+esc(p.package||"")+'</small></div><div><button class="btn-primary" onclick="location.href=\'/project/'+encodeURIComponent(p.name)+'\'"><i class="fa-solid fa-folder-open"></i> Open</button><button class="btn-danger" onclick="deleteProject(\''+esc(p.name)+'\')"><i class="fa-solid fa-trash"></i></button></div>';box.appendChild(div)})}catch(e){document.getElementById("projects").innerText="Error"}}
async function createProject(){var n=document.getElementById("appName").value.trim();var p=document.getElementById("packageName").value.trim();var l=document.getElementById("language").value;if(!n||!p){msg("Name & Package required",1);return}try{var r=await fetch("/api/projects",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:n,package:p,language:l,template:selectedTemplate})});var d=await r.json();if(!r.ok){msg(d.error||"Failed",1);return}msg("Created!",0);toast("Project created");document.getElementById("appName").value="";document.getElementById("packageName").value="";hideCreate();loadProjects();status()}catch(e){msg("Error",1)}}
async function deleteProject(name){if(!confirm("Delete "+name+"?"))return;try{var r=await fetch("/api/projects/"+encodeURIComponent(name),{method:"DELETE"});if(r.ok){toast("Deleted");loadProjects();status()}else toast("Failed","error")}catch(e){toast("Error","error")}}
async function loadApks(){try{var r=await fetch("/api/apks");var d=await r.json();var box=document.getElementById("apksList");if(!d.apks||!d.apks.length){box.innerHTML='<p style="color:#94a3b8;text-align:center">No APKs</p>';return}box.innerHTML="";d.apks.forEach(function(a){var div=document.createElement("div");div.className="apk-item";div.innerHTML='<div><b><i class="fa-solid fa-box-archive"></i> '+esc(a.name)+'</b><br><small style="color:#94a3b8">'+esc(a.size)+' • '+esc(a.mtime)+'</small></div><div><button class="btn-success" onclick="location.href=\'/api/download-saved-apk/'+encodeURIComponent(a.name)+'\'"><i class="fa-solid fa-download"></i></button><button class="btn-danger" onclick="deleteApk(\''+esc(a.name)+'\')"><i class="fa-solid fa-trash"></i></button></div>';box.appendChild(div)})}catch(e){document.getElementById("apksList").innerText="Error"}}
async function deleteApk(name){if(!confirm("Delete?"))return;try{var r=await fetch("/api/apks/"+encodeURIComponent(name),{method:"DELETE"});if(r.ok){toast("Deleted");loadApks()}else toast("Failed","error")}catch(e){toast("Error","error")}}
function msg(t,e){var m=document.getElementById("message");m.style.display="block";m.innerText=t;m.style.background=e?"rgba(127,29,29,.55)":"rgba(20,83,45,.55)"}
async function restoreBackup(input){if(!input.files[0])return;if(!confirm("Restore backup?"))return;var fd=new FormData();fd.append("file",input.files[0]);try{var r=await fetch("/api/restore",{method:"POST",body:fd});var d=await r.json();if(r.ok){toast("Restored!");loadProjects();status()}else toast(d.error||"Failed","error")}catch(e){toast("Error","error")}input.value=""}

var TIMEOUT_LABELS={};
async function openSettings(){document.getElementById("settingsModal").style.display="block";try{var r=await fetch("/api/ide-settings");var d=await r.json();document.getElementById("set_compileSdk").value=d.compileSdk||34;document.getElementById("set_targetSdk").value=d.targetSdk||34;document.getElementById("set_minSdk").value=d.minSdk||23;document.getElementById("set_gradleVersion").value=d.gradleVersion||"8.11.1";var t=await fetch("/api/timeouts");var td=await t.json();TIMEOUT_LABELS=td.labels||{};var values=td.timeouts||{};var list=document.getElementById("timeoutsList");list.innerHTML="";Object.keys(TIMEOUT_LABELS).forEach(function(k){var lbl=TIMEOUT_LABELS[k];var val=values[k]||60;var icon=lbl[4]||"fa-cog";list.innerHTML+='<div class="setting-item"><div class="label-wrap"><i class="fa-solid '+icon+' setting-icon"></i><div><label>'+lbl[0]+'</label><small>'+lbl[1]+' ('+lbl[2]+'-'+lbl[3]+')</small></div></div><input type="number" id="to_'+k+'" min="'+lbl[2]+'" max="'+lbl[3]+'" value="'+val+'"></div>'})}catch(e){}}
function closeSettings(){document.getElementById("settingsModal").style.display="none"}
function switchSettingsTab(id,el){document.querySelectorAll(".tab").forEach(function(t){t.classList.remove("active")});el.classList.add("active");document.querySelectorAll(".settings-content").forEach(function(c){c.style.display="none"});document.getElementById("tab-"+id).style.display="block"}
async function saveSettings(){var data={compileSdk:document.getElementById("set_compileSdk").value,targetSdk:document.getElementById("set_targetSdk").value,minSdk:document.getElementById("set_minSdk").value,gradleVersion:document.getElementById("set_gradleVersion").value};var timeouts={};Object.keys(TIMEOUT_LABELS).forEach(function(k){var el=document.getElementById("to_"+k);if(el)timeouts[k]=parseInt(el.value)||60});try{await fetch("/api/ide-settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});var r=await fetch("/api/timeouts",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(timeouts)});if(r.ok){toast("Settings saved!");closeSettings()}else toast("Failed","error")}catch(e){toast("Error","error")}}

status();loadProjects();
</script>
</body></html>
'''

# ============================================================
# END OF PART 1 — Paste PART 2 BELOW THIS LINE
# ============================================================


