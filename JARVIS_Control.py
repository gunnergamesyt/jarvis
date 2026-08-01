import tkinter as tk
from tkinter import ttk, colorchooser, font as tkfont
import threading, queue, os, json, subprocess, difflib, webbrowser, shutil, re, requests, html, traceback, asyncio, uuid, time
from bs4 import BeautifulSoup
import cloudscraper
import speech_recognition as sr
import ollama
import edge_tts
import pygame

VERSION = "1.5.8"
UPDATE_URL = "https://raw.githubusercontent.com/gunnergamesyt/jarvis/main/JARVIS_Control.py"
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_config.json")

def check_for_update():
    """Check GitHub for a newer version and auto-download if available"""
    try:
        # Cache-busting query param so the raw CDN never serves a stale copy
        r = requests.get(UPDATE_URL + f"?cb={int(time.time())}", timeout=8)
        if r.status_code != 200:
            add_log("sys", f"Update check failed (HTTP {r.status_code}).")
            return None
        content = r.text
        m = re.search(r'VERSION\s*=\s*"([\d.]+)"', content)
        if not m:
            return None
        remote = m.group(1)
        def ver(v):
            return tuple(int(x) for x in v.split("."))
        if ver(remote) > ver(VERSION):
            path = os.path.abspath(__file__)
            backup = path + ".old"
            try:
                if os.path.exists(backup):
                    os.remove(backup)
                os.rename(path, backup)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception as e:
                add_log("sys", f"Update failed: cannot write {path} ({e}).")
                if os.path.exists(backup) and not os.path.exists(path):
                    os.rename(backup, path)
                return None
            # Fetch latest requirements too so dep updates (e.g. sounddevice) are detected
            try:
                rr = requests.get("https://raw.githubusercontent.com/gunnergamesyt/jarvis/main/requirements.txt?cb=" + str(int(time.time())), timeout=8)
                req_path = os.path.join(os.path.dirname(path), "requirements.txt")
                if rr.status_code == 200:
                    new_req = rr.text.replace("\r\n", "\n").strip()
                    old_req = ""
                    if os.path.exists(req_path):
                        with open(req_path, encoding="utf-8") as f:
                            old_req = f.read().replace("\r\n", "\n").strip()
                    if new_req != old_req:
                        with open(req_path, "w", encoding="utf-8") as f:
                            f.write(rr.text)
                        return remote + ":DEPS"
            except Exception:
                pass
            return remote
        return None
    except Exception as e:
        add_log("sys", f"Update check failed: {e}")
        return None
DEFAULT_CONFIG = {
    "window": {"width": 600, "height": 450},
    "theme": {
        "bg": "#1a1a1a", "fg": "#cccccc", "accent": "#00ff88",
        "user_color": "#4fc3f7", "jarvis_color": "#00ff88",
        "font_family": "Consolas", "font_size": 10
    },
    "audio": {
        "mic_index": -1, "tts_rate": 180,
        "tts_voice": "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Speech\\Voices\\Tokens\\TTS_MS_EN-US_DAVID_11.0"
    },
    "animation": {"file": "off"},
    "minecraft": {
        "mods_folder": os.path.expandvars(r"%APPDATA%\.minecraft\mods"),
        "modpacks_folder": os.path.join(os.path.dirname(os.path.abspath(__file__)), "modpacks")
    }
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except:
            return dict(DEFAULT_CONFIG)
    return dict(DEFAULT_CONFIG)

def save_config(cfg):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(cfg, f, indent=2)

cfg = load_config()
tts_on = True

# ── Speech ──
def speak(text):
    global tts_on
    clean = text.replace("sir/ma'am", "sir").replace("ma'am", "sir")
    if "sir" not in clean.lower():
        clean += ", sir."
    add_log("jarvis", clean)
    if not tts_on:
        return
    try:
        path = os.environ['TEMP'] + "\\jarvis_" + str(uuid.uuid4()) + ".mp3"
        asyncio.run(edge_tts.Communicate(clean, "en-GB-RyanNeural").save(path))
        pygame.mixer.init()
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        pygame.mixer.music.stop()
        pygame.mixer.quit()
        os.unlink(path)
    except:
        pass

# ── Corrections ──
corrections = {
    "modern": "modrinth", "moderation": "modrinth", "moderate": "modrinth",
    "modreth": "modrinth", "modrith": "modrinth", "modrath": "modrinth",
    "curseforge": "curseforge", "course forge": "curseforge", "curse forge": "curseforge",
    "cursforge": "curseforge", "kurs forge": "curseforge", "cors forge": "curseforge",
    "curseforce": "curseforge", "curseforce app": "curseforge", "curse forge app": "curseforge",
    "modrinth": "modrinth", "modranth": "modrinth", "modrith app": "modrinth",
}

# ── Apps ──
APPS = {
    "notepad": "notepad.exe", "calculator": "calc.exe", "paint": "mspaint.exe",
    "cmd": "cmd.exe", "command prompt": "cmd.exe", "terminal": "cmd.exe",
    "explorer": "explorer.exe", "file explorer": "explorer.exe",
    "task manager": "taskmgr.exe", "control panel": "control.exe",
    "settings": "start ms-settings:",
    "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "edge": "start microsoft-edge:", "firefox": r"C:\Program Files\Mozilla Firefox\firefox.exe",
    "spotify": "start spotify:",
    "code": "code", "vs code": "code", "vscode": "code",
    "modrinth": r"C:\Users\%USERNAME%\AppData\Local\Modrinth App\Modrinth App.exe",
    "curseforge": r"C:\Users\%USERNAME%\AppData\Local\Programs\CurseForge Windows\CurseForge.exe",
}

def run_cmd(cmd):
    try:
        if cmd.startswith("start "):
            subprocess.run(cmd, shell=True)
        elif "\\" in cmd:
            os.startfile(os.path.expandvars(cmd))
        else:
            subprocess.Popen(cmd, shell=True)
    except Exception:
        pass

# ── Auto-discover folders & files ──
FOLDERS = {
    "downloads": os.path.expandvars(r"%USERPROFILE%\Downloads"),
    "download": os.path.expandvars(r"%USERPROFILE%\Downloads"),
    "documents": os.path.expandvars(r"%USERPROFILE%\Documents"),
    "document": os.path.expandvars(r"%USERPROFILE%\Documents"),
    "desktop": os.path.expandvars(r"%USERPROFILE%\Desktop"),
    "pictures": os.path.expandvars(r"%USERPROFILE%\Pictures"),
    "images": os.path.expandvars(r"%USERPROFILE%\Pictures"),
    "music": os.path.expandvars(r"%USERPROFILE%\Music"),
    "videos": os.path.expandvars(r"%USERPROFILE%\Videos"),
    "video": os.path.expandvars(r"%USERPROFILE%\Videos"),
    "home": os.path.expandvars(r"%USERPROFILE%"),
    "user": os.path.expandvars(r"%USERPROFILE%"),
    "appdata": os.path.expandvars(r"%APPDATA%"),
    "mods": os.path.expandvars(r"%APPDATA%\.minecraft\mods"),
    "minecraft": os.path.expandvars(r"%APPDATA%\.minecraft"),
}

def find_file(name):
    """Search common folders for a file matching the name"""
    search_dirs = [
        os.path.expandvars(r"%USERPROFILE%\Downloads"),
        os.path.expandvars(r"%USERPROFILE%\Documents"),
        os.path.expandvars(r"%USERPROFILE%\Desktop"),
        os.path.expandvars(r"%USERPROFILE%\Pictures"),
        os.path.expandvars(r"%USERPROFILE%\Music"),
        os.path.expandvars(r"%USERPROFILE%\Videos"),
    ]
    name_l = name.lower()
    for folder in search_dirs:
        if not os.path.exists(folder):
            continue
        for root, dirs, files in os.walk(folder):
            if root.count(os.sep) - folder.count(os.sep) > 3:
                continue
            for f in files:
                base = os.path.splitext(f)[0].lower()
                if name_l in base or base in name_l:
                    return os.path.join(root, f)
    return None

# ── Auto-discover installed apps ──
def discover_apps():
    """Scan Start Menu + common paths to find all installed apps"""
    discovered = {}
    start_menu_dirs = [
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
        os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs"),
    ]
    for folder in start_menu_dirs:
        if not os.path.exists(folder):
            continue
        for root, dirs, files in os.walk(folder):
            for f in files:
                if f.lower().endswith((".lnk", ".url")):
                    base = os.path.splitext(f)[0].strip()
                    if not base:
                        continue
                    key = base.lower()
                    if key not in discovered:
                        discovered[key] = os.path.join(root, f)
    # Common paths scan
    common = [
        r"C:\Program Files", r"C:\Program Files (x86)",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs"),
    ]
    for folder in common:
        if not os.path.exists(folder):
            continue
        for root, dirs, files in os.walk(folder):
            if root.count(os.sep) - folder.count(os.sep) > 2:
                continue
            for f in files:
                if f.lower().endswith(".exe"):
                    base = os.path.splitext(f)[0].strip()
                    if base and base.lower() not in discovered:
                        discovered[base.lower()] = os.path.join(root, f)
            # Only go 2 levels deep
    return discovered

INSTALLED = discover_apps()

def find_app(name):
    """Find an app by name across common install locations"""
    checks = [
        r"C:\Program Files\{0}\{0}.exe",
        r"C:\Program Files (x86)\{0}\{0}.exe",
        r"C:\Program Files\Google\{0}\Application\{0}.exe",
        r"C:\Program Files\{0}\Application\{0}.exe",
        r"%LOCALAPPDATA%\Programs\{0}\{0}.exe",
        r"%LOCALAPPDATA%\{0}\{0}.exe",
        r"%LOCALAPPDATA%\{0} App\{0} App.exe",
    ]
    for pattern in checks:
        p = os.path.expandvars(pattern.format(name.title()))
        if os.path.exists(p):
            return p
    return None

def launch_app(name):
    name = name.lower().strip()
    play_opening_animation()
    # Direct match in known apps
    if name in APPS:
        run_cmd(APPS[name])
        return True
    # Direct match in discovered apps
    if name in INSTALLED:
        run_cmd(INSTALLED[name])
        return True
    # Fuzzy match against known + discovered apps
    known = list(APPS.keys()) + list(INSTALLED.keys())
    m = difflib.get_close_matches(name, known, n=1, cutoff=0.5)
    if m:
        match = m[0]
        if match in APPS:
            run_cmd(APPS[match])
        else:
            run_cmd(INSTALLED[match])
        return True
    # Try common locations
    path = find_app(name)
    if path:
        subprocess.Popen(path)
        return True
    # Try `where` (PATH apps like spotify, code)
    try:
        result = subprocess.run(f"where {name}", shell=True, capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            subprocess.Popen(name, shell=True)
            return True
    except:
        pass
    # Try Windows Store app URI
    try:
        run_cmd(f"start {name}:")
        return True
    except:
        pass
    return False

# ── Opening Animation (plays when an app is launched through JARVIS) ──
ANIM_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "animations")

def get_animations():
    """List custom animations (mp4 base names in the animations folder)"""
    try:
        if not os.path.isdir(ANIM_DIR):
            return []
        return sorted(os.path.splitext(f)[0] for f in os.listdir(ANIM_DIR)
                      if f.lower().endswith(".mp4"))
    except Exception:
        return []

def ensure_default_animation():
    """Generate the built-in boot animation (mp4) + audio (mp3) on first run"""
    try:
        if not os.path.isdir(ANIM_DIR):
            os.makedirs(ANIM_DIR, exist_ok=True)
        mp4 = os.path.join(ANIM_DIR, "default.mp4")
        if os.path.exists(mp4):
            return mp4
        import cv2
        import numpy as np
        W, H, FPS, DUR = 1280, 720, 30, 3.0
        out = cv2.VideoWriter(mp4, cv2.VideoWriter_fourcc(*'mp4v'), FPS, (W, H))
        total = int(FPS * DUR)
        font = cv2.FONT_HERSHEY_SIMPLEX
        for i in range(total):
            t = i / total
            frame = np.zeros((H, W, 3), dtype=np.uint8)
            cv2.putText(frame, "JARVIS", (W//2 - 175, H//2 - 40), font, 2.6, (0, 255, 136), 7, cv2.LINE_AA)
            cv2.putText(frame, "Systems online", (W//2 - 140, H//2 + 35), font, 1.0, (200, 200, 200), 2, cv2.LINE_AA)
            bx, by, bw, bh = W//2 - 250, H//2 + 80, 500, 12
            cv2.rectangle(frame, (bx, by), (bx + int(bw * t), by + bh), (0, 255, 136), -1)
            cv2.rectangle(frame, (bx, by), (bx + bw, by + bh), (255, 255, 255), 1)
            out.write(frame)
        out.release()
        try:
            mp3 = os.path.join(ANIM_DIR, "default.mp3")
            if not os.path.exists(mp3):
                asyncio.run(edge_tts.Communicate("Systems online, sir.", "en-GB-RyanNeural").save(mp3))
        except Exception:
            pass
        return mp4
    except Exception:
        return None

def play_opening_animation():
    """Play the configured mp4 (+ paired mp3) fullscreen before opening an app"""
    try:
        anim = cfg.get('animation', {}).get('file', 'off')
        if anim == 'off' or not anim:
            return
        mp4 = os.path.join(ANIM_DIR, anim + ".mp4")
        if not os.path.exists(mp4):
            return
        import cv2
        import numpy as np
        import pygame
        cap = cv2.VideoCapture(mp4)
        if not cap.isOpened():
            return
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frames = []
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frames.append(frame)
        cap.release()
        if not frames:
            return
        pygame.init()
        info = pygame.display.Info()
        sw, sh = info.current_w, info.current_h
        screen = pygame.display.set_mode((sw, sh), pygame.NOFRAME)
        pygame.display.set_caption("JARVIS")
        mp3 = os.path.join(ANIM_DIR, anim + ".mp3")
        has_audio = False
        if os.path.exists(mp3):
            try:
                pygame.mixer.init()
                pygame.mixer.music.load(mp3)
                pygame.mixer.music.play()
                has_audio = True
            except Exception:
                pass
        surf_frames = []
        for frame in frames:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb = np.swapaxes(rgb, 0, 1)
            sf = pygame.surfarray.make_surface(rgb)
            surf_frames.append(pygame.transform.scale(sf, (sw, sh)))
        clock = pygame.time.Clock()
        playing, idx = True, 0
        while playing:
            for e in pygame.event.get():
                if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                    playing = False
            if idx >= len(surf_frames):
                break
            screen.blit(surf_frames[idx], (0, 0))
            pygame.display.flip()
            idx += 1
            clock.tick(fps)
        if has_audio:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
        pygame.quit()
    except Exception:
        pass

# ── Close Apps ──
def lnk_target(path):
    """Resolve a .lnk shortcut to its target path using pywin32 if available"""
    try:
        from win32com.client import Dispatch
        shell = Dispatch("WScript.Shell")
        return shell.CreateShortcut(path).TargetPath
    except Exception:
        return None

def close_app(app):
    """Close an app by name (handles spaces, fuzzy names, discovered apps)"""
    app = app.lower().strip()
    exe = None
    # Resolve process name from known apps
    if app in APPS:
        cmd = APPS[app]
        if cmd.startswith("start "):
            exe = app.replace(" ", "") + ".exe"
        else:
            base = os.path.basename(os.path.expandvars(cmd))
            exe = base if base.lower().endswith(".exe") else base + ".exe"
    # Resolve from discovered shortcuts (get the real exe name)
    elif app in INSTALLED:
        tgt = lnk_target(INSTALLED[app])
        if tgt and tgt.lower().endswith(".exe"):
            exe = os.path.basename(tgt)
        else:
            exe = app.replace(" ", "") + ".exe"
    else:
        # Fuzzy match against known + discovered apps
        known = list(APPS.keys()) + list(INSTALLED.keys())
        m = difflib.get_close_matches(app, known, n=1, cutoff=0.5)
        if m:
            return close_app(m[0])
        exe = app.replace(" ", "") + ".exe"
    # Try to kill by exact exe name
    if exe:
        r = subprocess.run(f'taskkill /im "{exe}" /f', shell=True, capture_output=True, text=True)
        if r.returncode == 0:
            return True
    # Fallback: fuzzy match against running processes
    try:
        out = subprocess.run('tasklist /FO CSV /NH', shell=True, capture_output=True, text=True).stdout
        best, best_score = None, 0.0
        app_clean = app.replace(" ", "").lower()
        for line in out.splitlines():
            parts = line.split('","')
            if not parts:
                continue
            pname = parts[0].strip('"')
            if not pname.lower().endswith(".exe"):
                continue
            pclean = pname.lower().replace(".exe", "").replace(" ", "")
            score = difflib.SequenceMatcher(None, app_clean, pclean).ratio()
            if score > best_score:
                best_score = score
                best = pname
        if best and best_score >= 0.6:
            r2 = subprocess.run(f'taskkill /im "{best}" /f', shell=True, capture_output=True, text=True)
            if r2.returncode == 0:
                return True
    except Exception:
        pass
    return False

# ── File Operations ──
def file_put(src, dst):
    src, dst = os.path.expandvars(src), os.path.expandvars(dst)
    if not os.path.exists(src):
        return f"Source not found: {src}"
    if os.path.isdir(dst):
        dst = os.path.join(dst, os.path.basename(src))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    return f"Copied {os.path.basename(src)} to {dst}"

def file_move(src, dst):
    src, dst = os.path.expandvars(src), os.path.expandvars(dst)
    if not os.path.exists(src):
        return f"Source not found: {src}"
    if os.path.isdir(dst):
        dst = os.path.join(dst, os.path.basename(src))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.move(src, dst)
    return f"Moved {os.path.basename(src)} to {dst}"

# ── Tutorial Fetcher ──
def fetch_tutorial(url):
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(r.text, 'html.parser')
        for tag in soup(['script','style','nav','header','footer','aside']):
            tag.decompose()
        text = soup.get_text(separator='\n', strip=True)
        lines = [l for l in text.split('\n') if len(l) > 40]
        return '\n'.join(lines[:30])[:2000]
    except Exception as e:
        return f"Failed to fetch tutorial: {e}"

# ── Minecraft Mod Installer (Modrinth + CurseForge) ──
MR_API = "https://api.modrinth.com/v2"
CF_BASE = "https://www.curseforge.com/minecraft/mc-mods"
cf_scraper = cloudscraper.create_scraper()

def search_modrinth(query):
    try:
        r = requests.get(f"{MR_API}/search", params={"query": query, "facets": '[[\"project_type:mod\"]]', "limit": 5}, timeout=10)
        return r.json().get("hits", [])
    except:
        return []

def mr_download(project_id):
    try:
        r = requests.get(f"{MR_API}/project/{project_id}/version", params={"loaders": '["fabric","forge","neoforge"]'}, timeout=10)
        v = r.json()
        if v:
            fi = v[0]['files'][0]
            return fi['url'], fi['filename']
    except:
        pass
    return None, None

def search_curseforge(query):
    try:
        r = cf_scraper.get(f"{CF_BASE}?search={requests.utils.quote(query)}", timeout=10)
        slugs = list(dict.fromkeys(re.findall(r'/minecraft/mc-mods/([\w-]+)', r.text)))
        results = []
        for slug in slugs[:5]:
            pr = cf_scraper.get(f"{CF_BASE}/{slug}", timeout=10)
            title_m = re.search(r'<title>(.+?) Minecraft', pr.text)
            desc_m = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]+)"', pr.text)
            results.append({"slug": slug, "title": title_m.group(1).strip() if title_m else slug, "desc": desc_m.group(1)[:200] if desc_m else ""})
        return results
    except:
        return []

def cf_page(slug):
    try:
        r = cf_scraper.get(f"{CF_BASE}/{slug}/files", timeout=10)
        file_ids = re.findall(r'/minecraft/mc-mods/[\w-]+/files/(\d+)', r.text)
        if file_ids:
            return f"{CF_BASE}/{slug}/download/{file_ids[0]}"
    except:
        pass
    return f"{CF_BASE}/{slug}"

def install_mod(name):
    mods_dir = cfg['minecraft']['mods_folder']
    os.makedirs(mods_dir, exist_ok=True)

    # Try Modrinth first
    add_log("sys", "Searching Modrinth...")
    mr_hits = search_modrinth(name)
    if mr_hits:
        mod = mr_hits[0]
        if len(mr_hits) > 1:
            prompt = (f"User wants '{name}'. Pick the best from:\n" +
                      "\n".join(f"{i+1}. {m['title']}" for i,m in enumerate(mr_hits)) + "\nReply with ONLY the number.")
            try:
                c = re.search(r'\d+', ollama.generate(model='llama3.2', prompt=prompt)['response'])
                mod = mr_hits[min(int(c.group())-1, len(mr_hits)-1)] if c else mr_hits[0]
            except:
                mod = mr_hits[0]
        url, fname = mr_download(mod['project_id'])
        if url and fname:
            dest = os.path.join(mods_dir, fname)
            dl = requests.get(url, timeout=60, stream=True)
            with open(dest, 'wb') as f:
                for chunk in dl.iter_content(8192):
                    f.write(chunk)
            return f"Installed {mod['title']} from Modrinth -> {fname}"

    # Fallback: CurseForge
    add_log("sys", "Not on Modrinth. Searching CurseForge...")
    cf_hits = search_curseforge(name)
    if cf_hits:
        mod = cf_hits[0]
        url = cf_page(mod['slug'])
        webbrowser.open(url)
        return f"Opening {mod['title']} on CurseForge in your browser — please download manually, sir."

    return f"Could not find any mod matching '{name}' on Modrinth or CurseForge."

# ── Modpack Downloader ──
def mp_folder():
    return cfg.get('minecraft', {}).get('modpacks_folder',
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "modpacks"))

def search_modpack(name):
    try:
        r = requests.get(f"{MR_API}/search", params={"query": name, "facets": '[[\"project_type:modpack\"]]', "limit": 5}, timeout=10)
        return r.json().get("hits", [])
    except:
        return []

def download_modpack(name):
    os.makedirs(mp_folder(), exist_ok=True)
    add_log("sys", "Searching modpacks...")
    hits = search_modpack(name)
    if not hits:
        return f"Could not find any modpack matching '{name}'."

    if len(hits) == 1:
        pack = hits[0]
    else:
        prompt = (f"User wants modpack '{name}'. Pick the best from:\n" +
                  "\n".join(f"{i+1}. {m['title']} - {m.get('description','')[:80]}" for i,m in enumerate(hits)) +
                  "\nReply with ONLY the number.")
        try:
            c = re.search(r'\d+', ollama.generate(model='llama3.2', prompt=prompt)['response'])
            pack = hits[min(int(c.group())-1, len(hits)-1)] if c else hits[0]
        except:
            pack = hits[0]

    try:
        r = requests.get(f"{MR_API}/project/{pack['project_id']}/version", timeout=10)
        versions = r.json()
        if not versions:
            return f"Found {pack['title']} but no versions available."
        for f in versions[0]['files']:
            if f['filename'].endswith('.mrpack'):
                url = f['url']
                fname = f['filename']
                dest = os.path.join(mp_folder(), fname)
                add_log("sys", f"Downloading {fname}...")
                dl = requests.get(url, timeout=120, stream=True)
                with open(dest, 'wb') as f:
                    for chunk in dl.iter_content(8192):
                        f.write(chunk)
                # Extract the .mrpack into a folder
                pack_dir = os.path.join(mp_folder(), pack['title'].replace(' ', '_'))
                import zipfile
                os.makedirs(pack_dir, exist_ok=True)
                with zipfile.ZipFile(dest, 'r') as zf:
                    zf.extractall(pack_dir)
                return (f"Downloaded and extracted {pack['title']} to {pack_dir}. "
                        f"You can import it into Prism Launcher or your launcher of choice, sir.")
        return f"Found {pack['title']} but no .mrpack file available."
    except Exception as e:
        return f"Failed to download {pack['title']}: {e}"

def create_modpack(pack_name, mod_names):
    pack_dir = os.path.join(mp_folder(), pack_name.replace(' ', '_'))
    mods_dir = os.path.join(pack_dir, 'mods')
    os.makedirs(mods_dir, exist_ok=True)
    results = []
    for m_name in mod_names:
        m_name = m_name.strip().lower()
        add_log("sys", f"Finding mod: {m_name}...")
        hits = search_modrinth(m_name)
        if hits:
            mod = hits[0]
            url, fname = mr_download(mod['project_id'])
            if url and fname:
                dest = os.path.join(mods_dir, fname)
                dl = requests.get(url, timeout=60, stream=True)
                with open(dest, 'wb') as f:
                    for chunk in dl.iter_content(8192):
                        f.write(chunk)
                results.append(f"  {mod['title']} -> {fname}")
            else:
                results.append(f"  {m_name}: found but no download")
        else:
            results.append(f"  {m_name}: not found")
    summary = "\n".join(results)
    return f"Created pack '{pack_name}' at {pack_dir}:\n{summary}"

# ── Modpack Browser (conversational) ──
browse = {"results": None, "idx": 0, "source": None, "query": None}

def browse_modpacks(query, source="modrinth"):
    browse["query"] = query
    browse["source"] = source
    browse["idx"] = 0
    if source == "modrinth":
        hits = search_modpack(query)
        browse["results"] = hits
    else:
        hits = search_curseforge(query)
        browse["results"] = hits if hits else []
    if not browse["results"]:
        browse["results"] = None
        return None
    return browse["results"][0]

def show_current():
    r = browse["results"]
    i = browse["idx"]
    if not r or i >= len(r):
        return None
    item = r[i]
    if browse["source"] == "modrinth":
        return f"{item['title']} — {item.get('description','')[:120]}"
    else:
        return f"{item['title']} — {item.get('desc','')[:120]}"

def download_current():
    r = browse["results"]
    i = browse["idx"]
    if not r or i >= len(r):
        return None
    item = r[i]
    if browse["source"] == "modrinth":
        return download_modpack(item['title'])
    else:
        webbrowser.open(f"{CF_BASE}/{item['slug']}")
        return f"Opening {item['title']} on CurseForge for you, sir."

# ── Voice Command Parser ──
def execute(q):
    # Open websites
    if "open youtube" in q or "youtube" in q:
        speak("Opening YouTube, sir.")
        webbrowser.open("https://youtube.com")
    elif "open google" in q or "google" in q:
        speak("Opening Google, sir.")
        webbrowser.open("https://google.com")
    elif "open curseforge" in q or "curseforge" in q:
        if launch_app("curseforge"):
            speak("Opening CurseForge app, sir.")
        else:
            speak("Opening CurseForge web, sir.")
            webbrowser.open("https://curseforge.com")
    elif "open modrinth" in q or "modrinth" in q:
        if launch_app("modrinth"):
            speak("Opening Modrinth app, sir.")
        else:
            speak("Opening Modrinth web, sir.")
            webbrowser.open("https://modrinth.com")

    # Open modpacks (before general "open" handler)
    elif ("open" in q or "show" in q) and "modpack" in q and not ("folder" in q or "directory" in q):
        query = q.replace("open","").replace("show","").replace("modpack","").replace("modpacks","").strip()
        if not query:
            query = "popular"
        source = "curseforge" if "curseforge" in q else "modrinth"
        first = browse_modpacks(query, source)
        if first:
            total = len(browse["results"])
            desc = show_current()
            speak(f"Pack 1 of {total}: {desc}. Say next to continue, or download that to install it.")
        else:
            speak(f"No modpacks found, sir.")

    # Open known folders / files / apps
    elif q.startswith("open ") or q.startswith("go to ") or q.startswith("show me "):
        target = q.split(" ", 2)[2].strip() if q.startswith("show me ") else q.split(" ", 1)[1].strip()
        target = target.replace("folder", "").replace("the", "").replace("app", "").strip()
        if target in FOLDERS and os.path.exists(FOLDERS[target]):
            os.startfile(FOLDERS[target])
            speak(f"Opening {target} folder, sir.")
            return
        # Find a file by name
        m = find_file(target)
        if m:
            os.startfile(os.path.dirname(m))
            speak(f"Found {os.path.basename(m)}, sir.")
            return
        # Launch an app (fuzzy matching handles misheard names like "curse forge")
        if launch_app(target):
            speak(f"Launching {target}, sir.")
            return
        # Last resort: treat as a website
        site = target.replace("website", "").replace("site", "").strip()
        if site and " " not in site:
            speak(f"Opening {target} as a website, sir.")
            webbrowser.open(f"https://{site}.com")
            return
        speak(f"Sorry sir, I couldn't find {target}.")

    # Launch apps
    elif q.startswith("launch ") or q.startswith("run "):
        app = q.split(" ", 1)[1].strip()
        if launch_app(app):
            speak(f"Launching {app}, sir.")
        else:
            speak(f"Opening {app} as a website, sir.")
            webbrowser.open(f"https://{app}.com")

    # Close apps
    elif q.startswith("close ") or q.startswith("kill ") or q.startswith("exit ") or q.startswith("stop "):
        app = q.split(" ", 1)[1].strip()
        # Don't let it kill JARVIS itself
        if app in ("jarvis", "javis", "open code", "opencode"):
            speak("I cannot close myself, sir.")
        elif close_app(app):
            speak(f"Closed {app}, sir.")
        else:
            speak(f"Could not find {app} running, sir.")

    # File operations
    elif q.startswith("copy ") and " to " in q:
        parts = q.split(" to ", 1)
        src = parts[0].replace("copy ", "", 1).strip()
        dst = parts[1].strip()
        msg = file_put(src, dst)
        speak(msg)

    elif q.startswith("move ") and " to " in q:
        parts = q.split(" to ", 1)
        src = parts[0].replace("move ", "", 1).strip()
        dst = parts[1].strip()
        msg = file_move(src, dst)
        speak(msg)

    elif q.startswith("put ") and " in " in q:
        parts = q.split(" in ", 1)
        src = parts[0].replace("put ", "", 1).strip()
        dst = parts[1].strip()
        msg = file_put(src, dst)
        speak(msg)

    # Tutorials
    elif q.startswith("follow tutorial ") or q.startswith("read tutorial ") or q.startswith("tutorial "):
        url = q.split("tutorial ", 1)[1].strip()
        if not url.startswith("http"):
            url = "https://" + url
        add_log("sys", f"Fetching tutorial from {url}...")
        content = fetch_tutorial(url)
        prompt = ("Summarize the key steps from this tutorial in 3-5 bullet points:\n" + content[:1500])
        try:
            resp = ollama.generate(model='llama3.2', prompt=prompt)
            speak(f"Here is the tutorial summary: {resp['response']}")
        except:
            speak("Could not process that tutorial, sir.")

    # Minecraft mods
    elif "install" in q and ("mod" in q or "mods" in q) and "pack" not in q:
        mod_name = q.replace("install", "", 1).replace("mod", "", 1).replace("for", "", 1).replace("minecraft", "", 1).strip()
        if not mod_name:
            mod_name = q
        add_log("sys", f"Searching for mod '{mod_name}'...")
        msg = install_mod(mod_name)
        speak(msg)

    # Open modpacks folder
    elif ("open" in q or "show" in q) and "modpack" in q and ("folder" in q or "directory" in q):
        os.startfile(mp_folder())
        speak("Opening modpacks folder, sir.")

    # Browse modpacks (find/list modpacks conversationally)
    elif ("browse" in q or "find" in q or "search" in q or "look" in q) and "modpack" in q:
        query = q.replace("browse","").replace("find","").replace("search","").replace("look","").replace("for","").replace("at","").replace("modpack","").replace("modpacks","").replace("curseforge","").replace("modrinth","").strip()
        if not query:
            query = "popular"
        source = "curseforge" if "curseforge" in q else "modrinth"
        add_log("sys", f"Searching {source} for modpacks...")
        first = browse_modpacks(query, source)
        if first:
            total = len(browse["results"])
            desc = show_current()
            speak(f"Pack 1 of {total}: {desc}. Say next to continue, or download that to install it.")
        else:
            speak(f"No modpacks found for {query}, sir.")

    elif q in ("next", "next one", "next modpack", "next pack", "go next"):
        if browse["results"]:
            browse["idx"] += 1
            total = len(browse["results"])
            if browse["idx"] >= total:
                browse["idx"] = 0
            desc = show_current()
            speak(f"Pack {browse['idx']+1} of {total}: {desc}. Say next or download this one.")
        else:
            speak("Not browsing any modpacks right now, sir.")

    elif q in ("back", "previous", "go back", "previous one"):
        if browse["results"]:
            browse["idx"] -= 1
            total = len(browse["results"])
            if browse["idx"] < 0:
                browse["idx"] = total - 1
            desc = show_current()
            speak(f"Pack {browse['idx']+1} of {total}: {desc}.")
        else:
            speak("Not browsing any modpacks right now, sir.")

    elif q in ("download that", "install that", "get this one", "download this", "install this"):
        if browse["results"] and browse["idx"] < len(browse["results"]):
            msg = download_current()
            speak(msg)
            browse["results"] = None
        else:
            speak("No modpack selected to download, sir.")

    # Modpack download (direct name)
    elif ("download" in q or "get" in q) and "modpack" in q:
        name = q.replace("download", "").replace("get","").replace("modpack","").replace("for","").replace("minecraft","").strip()
        if not name:
            name = q
        msg = download_modpack(name)
        speak(msg)

    # Create modpack
    elif ("create" in q or "make" in q) and "modpack" in q:
        rest = q.replace("create","").replace("make","").replace("a","").replace("called","").replace("named","").strip()
        # Try to extract pack name and mods
        parts = re.split(r' with | containing | including | using ', rest, 1)
        if len(parts) > 1:
            pname = parts[0].replace("modpack","").strip()
            mods_str = parts[1]
            mods_list = [m.strip() for m in re.split(r',| and ', mods_str) if m.strip()]
            if not pname:
                pname = mods_list[0] + "_pack" if mods_list else "my_pack"
            msg = create_modpack(pname, mods_list)
            speak(msg)
        else:
            mods = rest.replace("modpack","").strip()
            if mods:
                prompt = (f"User wants a modpack with: {mods}. "
                          "Suggest a name and list compatible mods. 2 sentence reply.")
                try:
                    r = ollama.generate(model='llama3.2', prompt=prompt)
                    speak(r['response'])
                except:
                    speak("Could not suggest a pack, sir.")
            else:
                speak("What mods should the pack include, sir?")

    # PC shutdown/restart
    elif ("shut" in q and "down" in q and not any(x in q for x in ["jarvis","opencode"])) or ("shutdown" in q and not "jarvis" in q):
        speak("Shutting down PC in 10 seconds, sir. Say abort to cancel.")
        subprocess.run("shutdown /s /t 10", shell=True)

    elif "restart" in q or "reboot" in q:
        speak("Restarting PC in 10 seconds, sir. Say abort to cancel.")
        subprocess.run("shutdown /r /t 10", shell=True)

    elif "abort" in q and ("shutdown" in q or "restart" in q):
        subprocess.run("shutdown /a", shell=True)
        speak("Aborted shutdown, sir.")

    # Exit JARVIS
    elif "goodbye" in q or "offline" in q or "turn off" in q or ("shut" in q and "down" in q and "jarvis" in q):
        speak("Shutting down. Goodbye, sir.")
        os._exit(0)

    # AI conversation
    elif q:
        try:
            prompt = ("You are JARVIS, Tony Stark's loyal male robotic butler. "
                      "You are speaking directly to your master, who is a man. "
                      "You must explicitly address the user as 'sir'. "
                      "Never say 'ma'am' or 'sir/ma'am'. "
                      "Respond in 1 brief sentence. " f"User command: {q}")
            resp = ollama.generate(model='llama3.2', prompt=prompt)
            speak(resp['response'])
        except:
            speak("Core timeout error, sir.")

# ── Listen ──
def get_mic_names():
    """Enumerate real input devices only (pyaudio -> sounddevice -> fallback)"""
    names = []
    try:
        import pyaudio
        p = pyaudio.PyAudio()
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info.get('maxInputChannels', 0) > 0:
                names.append(info.get('name') or f"Mic {i}")
        p.terminate()
    except Exception:
        pass
    if not names:
        try:
            names = sr.Microphone.list_microphone_names()
        except Exception:
            pass
    if not names:
        try:
            import sounddevice as sd
            for i, d in enumerate(sd.query_devices()):
                if d.get('max_input_channels', 0) > 0:
                    names.append(d['name'])
        except Exception:
            pass
    if not names:
        add_log("sys", "No microphone backend found. Run: pip install pyaudio sounddevice")
        return ["Default (auto)"]
    return names

def listen():
    r = sr.Recognizer()
    r.energy_threshold = 150
    r.dynamic_energy_threshold = True
    r.dynamic_energy_adjustment_damping = 0.15
    r.dynamic_energy_ratio = 1.0
    r.pause_threshold = 0.6
    idx = cfg['audio']['mic_index']
    try:
        src = sr.Microphone(device_index=idx) if idx >= 0 else sr.Microphone()
    except:
        src = sr.Microphone()
    with src:
        r.adjust_for_ambient_noise(src, duration=1.0)
        try:
            audio = r.listen(src, timeout=4, phrase_time_limit=5)
            result = r.recognize_google(audio, language='en-US', show_all=True)
            if isinstance(result, dict) and 'alternative' in result:
                q = result['alternative'][0]['transcript'].lower()
            else:
                q = result.lower() if result else ""
            for w, r in corrections.items():
                q = q.replace(w, r)
            add_log("user", q)
            return q
        except:
            return ""

# ── Main Loop ──
def loop():
    speak("Systems online. How can I help you, sir?")
    while running:
        q = listen()
        if q and running:
            execute(q)

msg_q = queue.Queue()
def add_log(sender, text):
    msg_q.put((sender, text))

def process():
    while not msg_q.empty():
        s, t = msg_q.get()
        tag = "user" if s == "user" else ("jarvis" if s == "jarvis" else "dim")
        prefix = "You: " if s == "user" else ("JARVIS: " if s == "jarvis" else "")
        log.config(state=tk.NORMAL)
        log.insert(tk.END, f"{prefix}{t}\n", tag)
        log.see(tk.END)
        log.config(state=tk.DISABLED)
    root.after(100, process)

running = False

def start():
    global running, thread, INSTALLED
    if running:
        return
    running = True
    INSTALLED = discover_apps()
    log.config(state=tk.NORMAL)
    log.delete("1.0", tk.END)
    log.config(state=tk.DISABLED)
    btn_start.config(state=tk.DISABLED, bg="#333")
    btn_stop.config(state=tk.NORMAL, bg="#cc0000")
    status_label.config(text="ON", fg=cfg['theme']['accent'])
    thread = threading.Thread(target=loop, daemon=True)
    thread.start()

def stop():
    global running
    running = False
    btn_start.config(state=tk.NORMAL, bg="#006600")
    btn_stop.config(state=tk.DISABLED, bg="#440000")
    status_label.config(text="OFF", fg="#ff4444")

# ── Theme Apply ──
def apply_theme():
    t = cfg['theme']
    root.configure(bg=t['bg'])
    title_label.config(bg=t['bg'], fg=t['accent'])
    status_label.config(bg=t['bg'])
    log.config(bg=t['bg'], fg=t['fg'], font=(t['font_family'], t['font_size']))
    log.tag_config("user", foreground=t['user_color'])
    log.tag_config("jarvis", foreground=t['jarvis_color'])
    log.tag_config("dim", foreground="#555")
    btn_frame.config(bg=t['bg'])
    input_frame.config(bg=t['bg'])
    input_field.config(bg=t['bg'], fg=t['fg'], font=(t['font_family'], t['font_size']), insertbackground=t['accent'])
    root.geometry(f"{cfg['window']['width']}x{cfg['window']['height']}")

# ── Settings Window ──
def open_settings():
    sw = tk.Toplevel(root)
    sw.title("Settings")
    sw.configure(bg="#2a2a2a")
    sw.geometry("560x460")
    sw.resizable(True, True)
    f = ("Segoe UI", 10)
    row = [0]

    # Scrollable area so no settings ever get cut off
    canvas = tk.Canvas(sw, bg="#2a2a2a", highlightthickness=0)
    vsb = ttk.Scrollbar(sw, orient="vertical", command=canvas.yview)
    host = tk.Frame(canvas, bg="#2a2a2a")
    host.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=host, anchor="nw")
    canvas.configure(yscrollcommand=vsb.set)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)

    def on_wheel(e):
        canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
    canvas.bind("<MouseWheel>", on_wheel)
    host.bind("<MouseWheel>", on_wheel)

    def lbl(text):
        tk.Label(host, text=text, fg="#ccc", bg="#2a2a2a", font=f).grid(row=row[0], column=0, sticky="w", padx=10, pady=4)
        row[0] += 1

    def btn(text, cmd):
        b = tk.Button(host, text=text, command=cmd, bg="#3a3a3a", fg="white", font=f)
        b.grid(row=row[0]-1, column=1, padx=10, pady=4, sticky="ew")

    lbl("Background color")
    btn("Pick", lambda: cfg['theme'].__setitem__('bg', colorchooser.askcolor(color=cfg['theme']['bg'])[1]) and apply_theme() if colorchooser.askcolor(color=cfg['theme']['bg'])[1] else None)

    lbl("Accent color")
    btn("Pick", lambda: cfg['theme'].__setitem__('accent', colorchooser.askcolor(color=cfg['theme']['accent'])[1]) and apply_theme() if colorchooser.askcolor(color=cfg['theme']['accent'])[1] else None)

    lbl("User text color")
    btn("Pick", lambda: cfg['theme'].__setitem__('user_color', colorchooser.askcolor(color=cfg['theme']['user_color'])[1]) and apply_theme() if colorchooser.askcolor(color=cfg['theme']['user_color'])[1] else None)

    lbl("JARVIS text color")
    btn("Pick", lambda: cfg['theme'].__setitem__('jarvis_color', colorchooser.askcolor(color=cfg['theme']['jarvis_color'])[1]) and apply_theme() if colorchooser.askcolor(color=cfg['theme']['jarvis_color'])[1] else None)

    lbl("Font")
    font_var = tk.StringVar(value=cfg['theme']['font_family'])
    fm = ttk.Combobox(host, textvariable=font_var, values=sorted(set(tkfont.families())), font=f, state="readonly")
    fm.grid(row=row[0]-1, column=1, padx=10, pady=4, sticky="ew")
    fm.bind("<<ComboboxSelected>>", lambda e: (cfg['theme'].__setitem__('font_family', font_var.get()), apply_theme()))

    lbl("Font size")
    sv = tk.IntVar(value=cfg['theme']['font_size'])
    tk.Spinbox(host, from_=8, to=24, textvariable=sv, width=5, font=f).grid(row=row[0]-1, column=1, padx=10, pady=4, sticky="w")
    tk.Button(host, text="Apply", command=lambda: (cfg['theme'].__setitem__('font_size', sv.get()), apply_theme()), bg="#3a3a3a", fg="white", font=f).grid(row=row[0]-1, column=2, padx=5)

    lbl("Window width")
    wv = tk.IntVar(value=cfg['window']['width'])
    tk.Spinbox(host, from_=300, to=1200, textvariable=wv, width=5, font=f).grid(row=row[0]-1, column=1, padx=10, pady=4, sticky="w")
    tk.Button(host, text="Apply", command=lambda: (cfg['window'].__setitem__('width', wv.get()), apply_theme()), bg="#3a3a3a", fg="white", font=f).grid(row=row[0]-1, column=2, padx=5)

    lbl("Window height")
    hv = tk.IntVar(value=cfg['window']['height'])
    tk.Spinbox(host, from_=200, to=1000, textvariable=hv, width=5, font=f).grid(row=row[0]-1, column=1, padx=10, pady=4, sticky="w")
    tk.Button(host, text="Apply", command=lambda: (cfg['window'].__setitem__('height', hv.get()), apply_theme()), bg="#3a3a3a", fg="white", font=f).grid(row=row[0]-1, column=2, padx=5)

    lbl("Microphone")
    mics = [m for m in get_mic_names() if m != "Default (auto)"]
    options = ["Default (auto)"] + mics
    idx = cfg['audio']['mic_index']
    mv = tk.StringVar(value="Default (auto)" if idx < 0 else (mics[idx] if idx < len(mics) else mics[0]))
    mm = ttk.Combobox(host, textvariable=mv, values=options, font=f, state="readonly")
    mm.grid(row=row[0]-1, column=1, padx=10, pady=4, sticky="ew")
    mm.bind("<<ComboboxSelected>>", lambda e: cfg['audio'].__setitem__('mic_index', options.index(mv.get()) - 1))

    lbl("Opening animation")
    anims = ["Off"] + get_animations()
    cur = cfg.get('animation', {}).get('file', 'off')
    av = tk.StringVar(value="Off" if cur == 'off' or not cur else cur)
    am = ttk.Combobox(host, textvariable=av, values=anims, font=f, state="readonly")
    am.grid(row=row[0]-1, column=1, padx=10, pady=4, sticky="ew")
    am.bind("<<ComboboxSelected>>", lambda e: cfg['animation'].__setitem__('file', 'off' if av.get() == 'Off' else av.get()))
    tk.Button(host, text="Folder", command=lambda: (ensure_default_animation(), os.startfile(ANIM_DIR)), bg="#3a3a3a", fg="white", font=f).grid(row=row[0]-1, column=2, padx=5)

    lbl("TTS Rate")
    rv = tk.IntVar(value=cfg['audio']['tts_rate'])
    tk.Spinbox(host, from_=100, to=400, textvariable=rv, width=5, font=f).grid(row=row[0]-1, column=1, padx=10, pady=4, sticky="w")
    tk.Button(host, text="Apply", command=lambda: cfg['audio'].__setitem__('tts_rate', rv.get()), bg="#3a3a3a", fg="white", font=f).grid(row=row[0]-1, column=2, padx=5)

    lbl("Mods folder")
    mfv = tk.StringVar(value=cfg['minecraft']['mods_folder'])
    tk.Entry(host, textvariable=mfv, font=f, bg="#333", fg="white", width=30).grid(row=row[0]-1, column=1, padx=10, pady=4, sticky="ew")
    tk.Button(host, text="Set", command=lambda: cfg['minecraft'].__setitem__('mods_folder', mfv.get()), bg="#3a3a3a", fg="white", font=f).grid(row=row[0]-1, column=2, padx=5)

    lbl("Modpacks folder")
    mpfv = tk.StringVar(value=cfg['minecraft']['modpacks_folder'])
    tk.Entry(host, textvariable=mpfv, font=f, bg="#333", fg="white", width=30).grid(row=row[0]-1, column=1, padx=10, pady=4, sticky="ew")
    tk.Button(host, text="Set", command=lambda: cfg['minecraft'].__setitem__('modpacks_folder', mpfv.get()), bg="#3a3a3a", fg="white", font=f).grid(row=row[0]-1, column=2, padx=5)

    row[0] += 1
    tk.Button(host, text="SAVE & CLOSE", command=lambda: (save_config(cfg), sw.destroy()),
              bg="#006600", fg="white", font=("Segoe UI", 11, "bold"), padx=20, pady=5
             ).grid(row=row[0], column=0, columnspan=3, pady=15)

    sw.transient(root)
    sw.grab_set()
    sw.wait_window()

# ── GUI ──
root = tk.Tk()
root.title("JARVIS")
root.geometry(f"{cfg['window']['width']}x{cfg['window']['height']}")
root.configure(bg=cfg['theme']['bg'])

title_label = tk.Label(root, text=f"JARVIS  v{VERSION}", fg=cfg['theme']['accent'], bg=cfg['theme']['bg'],
                       font=("Segoe UI", 18, "bold"))
title_label.pack(pady=(8,0))

status_label = tk.Label(root, text="OFF", fg="#ff4444", bg=cfg['theme']['bg'],
                        font=("Segoe UI", 10, "bold"))
status_label.pack()

log = tk.Text(root, bg=cfg['theme']['bg'], fg=cfg['theme']['fg'],
              font=(cfg['theme']['font_family'], cfg['theme']['font_size']),
              wrap=tk.WORD, state=tk.DISABLED, height=14, borderwidth=2, relief=tk.SUNKEN)
log.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
log.config(state=tk.NORMAL)
log.insert(tk.END, "Press START to begin.\n")
log.config(state=tk.DISABLED)
log.tag_config("user", foreground=cfg['theme']['user_color'])
log.tag_config("jarvis", foreground=cfg['theme']['jarvis_color'])
log.tag_config("dim", foreground="#555")
scroll = tk.Scrollbar(log)
scroll.pack(side=tk.RIGHT, fill=tk.Y)
log.config(yscrollcommand=scroll.set)
scroll.config(command=log.yview)

input_frame = tk.Frame(root, bg=cfg['theme']['bg'])
input_frame.pack(fill=tk.X, padx=10, pady=(0,5))

def send_text(event=None):
    text = input_field.get().strip()
    if not text:
        return
    input_field.delete(0, tk.END)
    add_log("user", text.lower())
    if running:
        execute(text.lower())
    else:
        add_log("jarvis", "Press START first, sir.")

input_field = tk.Entry(input_frame, bg="#111", fg=cfg['theme']['fg'],
                       font=(cfg['theme']['font_family'], cfg['theme']['font_size']),
                       insertbackground=cfg['theme']['accent'], relief=tk.SUNKEN, borderwidth=2)
input_field.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
input_field.bind("<Return>", send_text)

send_btn = tk.Button(input_frame, text="SEND", command=send_text, width=6,
                     bg="#333366", fg="white", font=("Segoe UI", 9, "bold"))
send_btn.pack(side=tk.RIGHT, padx=(5,0))

btn_frame = tk.Frame(root, bg=cfg['theme']['bg'])
btn_frame.pack(pady=(0,10))

btn_start = tk.Button(btn_frame, text="  START  ", command=start,
                      bg="#006600", fg="white", font=("Segoe UI", 11, "bold"), padx=15, pady=5, cursor="hand2")
btn_start.pack(side=tk.LEFT, padx=5)

btn_stop = tk.Button(btn_frame, text="  STOP  ", command=stop, state=tk.DISABLED,
                     bg="#440000", fg="white", font=("Segoe UI", 11, "bold"), padx=15, pady=5, cursor="hand2")
btn_stop.pack(side=tk.LEFT, padx=5)

btn_tts = tk.Button(btn_frame, text="  TTS: ON  ", command=lambda: toggle_tts(),
                    bg="#006600", fg="white", font=("Segoe UI", 10, "bold"), padx=10, pady=5, cursor="hand2")
btn_tts.pack(side=tk.LEFT, padx=5)

btn_settings = tk.Button(btn_frame, text="  SETTINGS  ", command=open_settings,
                         bg="#333366", fg="white", font=("Segoe UI", 10, "bold"), padx=10, pady=5, cursor="hand2")
btn_settings.pack(side=tk.LEFT, padx=5)

def toggle_tts():
    global tts_on
    tts_on = not tts_on
    btn_tts.config(text=f"  TTS: {'ON' if tts_on else 'OFF'}  ", bg="#006600" if tts_on else "#444")

def verify_deps():
    missing = []
    for mod in ("pyaudio", "sounddevice"):
        try:
            __import__(mod)
        except Exception:
            missing.append(mod)
    if missing:
        msg = "Microphone backend missing: " + ", ".join(missing) + ". Run INSTALL_JARVIS.bat to install dependencies."
        add_log("sys", msg)

def run_update_check():
    if UPDATE_URL.endswith("gunnergamesyt/jarvis/main/"):
        return
    add_log("sys", "Checking for updates...")
    new_ver = check_for_update()
    if new_ver and new_ver.endswith(":DEPS"):
        new_ver = new_ver[:-5]
        add_log("sys", f"Update v{new_ver} downloaded + new dependencies! Restart JARVIS, then run INSTALL_JARVIS.bat.")
        speak(f"Update version {new_ver} downloaded, with new dependencies. Please restart me, and run the installer, sir.")
    elif new_ver:
        add_log("sys", f"Update v{new_ver} downloaded! Please restart JARVIS.")
        speak(f"Update version {new_ver} downloaded. Please restart me, sir.")
    else:
        add_log("sys", "JARVIS is up to date.")

root.after(100, process)
root.after(1500, lambda: threading.Thread(target=run_update_check, daemon=True).start())
root.after(3000, lambda: threading.Thread(target=verify_deps, daemon=True).start())
root.after(4000, lambda: threading.Thread(target=ensure_default_animation, daemon=True).start())
root.mainloop()
