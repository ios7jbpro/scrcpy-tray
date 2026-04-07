import subprocess
import threading
import os
import time
import json
import tkinter as tk
import sys
import ctypes
from pystray import Icon, Menu, MenuItem
from PIL import Image, ImageDraw

SCRIPT_DIR = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
SCRCPY_PATH = os.path.join(SCRIPT_DIR, "scrcpy.exe")

icon = None
devices_cache = []
app_cache = {}
fetching_status = {}
favorites = []

# Support for installed version: Store favorites in AppData
FAVORITES_DIR = os.path.join(os.getenv('APPDATA', os.path.expanduser("~")), "scrcpy-tray")
try:
    if not os.path.exists(FAVORITES_DIR):
        os.makedirs(FAVORITES_DIR)
except:
    FAVORITES_DIR = SCRIPT_DIR # Fallback to local
FAVORITES_FILE = os.path.join(FAVORITES_DIR, "favorites.json")


def run_cmd(cmd):
    try:
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL, creationflags=creationflags)
    except:
        return ""


def get_adb_devices():
    output = run_cmd(["adb", "devices"])
    lines = output.strip().splitlines()[1:]

    devices = []
    for line in lines:
        if line.strip():
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                devices.append(parts[0])
    return devices


def get_device_name(device_id):
    name = run_cmd(["adb", "-s", device_id, "shell", "getprop", "ro.product.model"]).strip()
    return name if name else device_id


def lock_device(device_id):
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    # Send Home (3) then Power (26)
    run_cmd(["adb", "-s", device_id, "shell", "input", "keyevent", "3"])
    subprocess.Popen([
        "adb", "-s", device_id,
        "shell", "input", "keyevent", "26"
    ], creationflags=creationflags)


def set_nav_mode(device_id, mode):
    # mode 1 = 3-button, mode 2 = gestures
    run_cmd(["adb", "-s", device_id, "shell", "settings", "put", "secure", "navigation_mode", str(mode)])


def load_favorites():
    global favorites
    if os.path.exists(FAVORITES_FILE):
        try:
            with open(FAVORITES_FILE, 'r') as f:
                favorites = json.load(f)
        except:
            favorites = []


def save_favorites():
    try:
        with open(FAVORITES_FILE, 'w') as f:
            json.dump(favorites, f)
    except:
        pass


def add_favorite(device_id, device_label, pkg, app_label):
    global favorites
    # avoid duplicates
    for fav in favorites:
        if fav['device_id'] == device_id and fav['package'] == pkg:
            return
    favorites.append({
        'device_id': device_id,
        'package': pkg,
        'label': app_label,
        'device_label': device_label
    })
    save_favorites()
    if icon:
        refresh_devices()


def remove_favorite(index):
    global favorites
    if 0 <= index < len(favorites):
        favorites.pop(index)
        save_favorites()
        if icon:
            refresh_devices()


def fetch_apps(device_id, device_label):
    if device_id in fetching_status and fetching_status[device_id]:
        return

    def run_fetch():
        fetching_status[device_id] = True
        try:
            output = run_cmd(["adb", "-s", device_id, "shell", "pm", "list", "packages", "-3"])
            packages = [line.split(":")[1].strip() for line in output.strip().splitlines() if ":" in line]

            apps = []
            for pkg in packages:
                # try to get label
                info = run_cmd(["adb", "-s", device_id, "shell", "dumpsys", "package", pkg])
                label = pkg
                for line in info.splitlines():
                    if "label=" in line:
                        label = line.split("=")[1].strip()
                        break
                apps.append((pkg, label))

            # sort by label
            apps.sort(key=lambda x: x[1].lower())
            app_cache[device_id] = apps
        finally:
            fetching_status[device_id] = False
            if icon:
                refresh_devices()
                icon.notify(f"Ready to launch apps for {device_label}", "Scan Complete")

    threading.Thread(target=run_fetch, daemon=True).start()


def run_nav_button_process(nav_type, device_id, device_label):
    # Set unique AUMID for this process to prevent taskbar grouping
    aumid = f"Antigravity.Scrcpy.Nav.{nav_type}.{device_id[:8]}"
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(aumid)
    except:
        pass

    # nav_type: 'back', 'home', 'recents'
    titles = {
        'back': f"Back - {device_label}",
        'home': f"Go home - {device_label}",
        'recents': f"Recents - {device_label}"
    }
    keycodes = {
        'back': '4',
        'home': '3',
        'recents': '187'
    }
    
    title = titles.get(nav_type, f"Nav - {device_label}")
    keycode = keycodes.get(nav_type, '3')
    
    icon_map = {
        'back': 'back.png',
        'home': 'home.png',
        'recents': 'recents.png'
    }
    icon_file = icon_map.get(nav_type)

    try:
        root = tk.Tk()
        root.title(title)
        
        if icon_file:
            icon_path = os.path.join(SCRIPT_DIR, icon_file)
            if os.path.exists(icon_path):
                img = tk.PhotoImage(file=icon_path)
                root.iconphoto(True, img)
                
        # Make it invisible but keep it in the taskbar
        root.attributes("-alpha", 0.0)
        root.geometry("1x1+0+0")
        
        # Start minimized
        root.iconify()

        # Cooldown to prevent double-triggering (Wait 1s)
        last_trigger = [0]

        def on_event(event):
            now = time.time()
            if now - last_trigger[0] < 1.0:
                return
            last_trigger[0] = now
            
            # When user tries to focus or un-minimize
            root.iconify()
            # Send Nav Command
            run_cmd(["adb", "-s", device_id, "shell", "input", "keyevent", keycode])

        # FocusIn and Map detect taskbar interaction
        root.bind("<FocusIn>", on_event)
        root.bind("<Map>", on_event)

        # Separate thread won't work easily here for stop_event 
        # since it's a separate process. It will be killed by parent.
        root.mainloop()
    except:
        pass


def start_scrcpy(device_id, launch_package=None):
    if not isinstance(device_id, str):
        print("invalid device id:", device_id)
        return

    def run():
        # Navbar logic: Launch Back, Home, Recents as separate processes
        device_name = get_device_name(device_id)
        processes = []

        def spawn_button(type_, delay):
            time.sleep(delay)
            # Re-execute the current script with special args
            cmd = []
            if getattr(sys, 'frozen', False):
                # When frozen (bundled EXE), sys.executable is the exe itself
                cmd = [sys.executable, "--nav-button", type_, device_id, device_name]
            else:
                # When running as script
                cmd = [sys.executable, __file__, "--nav-button", type_, device_id, device_name]
            
            p = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            return p

        # Start them sequentially for order
        threading.Thread(target=lambda: processes.append(spawn_button('back', 3.0))).start()
        threading.Thread(target=lambda: processes.append(spawn_button('home', 3.3))).start()
        threading.Thread(target=lambda: processes.append(spawn_button('recents', 3.6))).start()

        try:
            # Check for Android 11 audio issue
            android_ver = run_cmd(["adb", "-s", device_id, "shell", "getprop", "ro.build.version.release"]).strip()
            if android_ver == "11":
                # Wake up the screen
                run_cmd(["adb", "-s", device_id, "shell", "input", "keyevent", "224"])
                time.sleep(0.5)
                # Unlock (Space keyevent)
                run_cmd(["adb", "-s", device_id, "shell", "input", "keyevent", "62"])
                time.sleep(0.5)

            # disable auto-rotation and lock to portrait
            run_cmd(["adb", "-s", device_id, "shell", "settings", "put", "system", "accelerometer_rotation", "0"])
            run_cmd(["adb", "-s", device_id, "shell", "settings", "put", "system", "user_rotation", "0"])

            # enable 3-button navigation
            set_nav_mode(device_id, 1)

            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            proc = subprocess.Popen([
                SCRCPY_PATH,
                "-s", device_id,
                "-S",
                "--stay-awake",
                "--screen-off-timeout=300"
            ], creationflags=creationflags)

            # launch app if requested
            if launch_package:
                # wait a bit for scrcpy to show up
                time.sleep(1) 
                
                # unlock (space key event)
                run_cmd(["adb", "-s", device_id, "shell", "input", "keyevent", "62"])

                subprocess.Popen([
                    "adb", "-s", device_id,
                    "shell", "monkey",
                    "-p", launch_package,
                    "-c", "android.intent.category.LAUNCHER", "1"
                ], creationflags=creationflags)

            # wait until scrcpy closes
            proc.wait()

            # stop the navbar buttons
            for p in processes:
                try:
                    p.terminate()
                except:
                    pass

            # restore gesture navigation
            set_nav_mode(device_id, 2)

            # restore auto-rotation
            run_cmd(["adb", "-s", device_id, "shell", "settings", "put", "system", "accelerometer_rotation", "1"])

            # lock screen after exit (goes Home first)
            lock_device(device_id)

        except Exception as e:
            print("scrcpy error:", e)

    threading.Thread(target=run, daemon=True).start()


def load_icon():
    icon_path = os.path.join(SCRIPT_DIR, "icon.png")
    try:
        if os.path.exists(icon_path):
            return Image.open(icon_path)
    except:
        pass
        
    # fallback if file is missing or broken
    img = Image.new('RGB', (64, 64), (30, 30, 30))
    d = ImageDraw.Draw(img)
    d.rectangle((16, 16, 48, 48), fill=(0, 200, 0))
    return img


def build_menu():
    global devices_cache, favorites

    items = []

    # Favorites Section at the very top
    if favorites:
        fav_items = []
        online_ids = [d[0] for d in devices_cache]
        
        for i, fav in enumerate(favorites):
            is_online = fav['device_id'] in online_ids
            
            # capture closure
            def make_fav_action(f):
                return lambda icon, item: start_scrcpy(f['device_id'], f['package'])
            def make_remove_action(idx):
                return lambda icon, item: remove_favorite(idx)
            
            label = f"{fav['label']} - {fav['device_label']}"
            if not is_online:
                label += " (offline)"
            
            fav_items.append(
                MenuItem(
                    label, 
                    Menu(
                        MenuItem("Stream & Launch", make_fav_action(fav), enabled=is_online),
                        MenuItem("Remove Favorite", make_remove_action(i))
                    )
                )
            )
        
        items.append(MenuItem("Favorites", Menu(*fav_items)))
        items.append(Menu.SEPARATOR)

    if not devices_cache:
        items.append(MenuItem("No devices", None, enabled=False))
        items.append(MenuItem("Refresh", lambda icon, item: refresh_devices()))
        items.append(MenuItem("Exit", lambda icon, item: icon.stop()))
        return Menu(*items)

    for dev_id, dev_name in devices_cache:
        def make_action(d, p=None):
            return lambda icon, item: start_scrcpy(d, p)

        # start an app submenu
        if dev_id in app_cache:
            app_items = []
            for pkg, label in app_cache[dev_id]:
                # submenu for each app in the list
                def make_add_fav_action(d_id, d_lbl, p, l):
                    return lambda icon, item: add_favorite(d_id, d_lbl, p, l)

                app_items.append(
                    MenuItem(
                        label,
                        Menu(
                            MenuItem("Launch", make_action(dev_id, pkg)),
                            MenuItem("Add to Favorites", make_add_fav_action(dev_id, dev_name, pkg, label))
                        )
                    )
                )
            
            start_app_menu = Menu(*app_items)
        elif fetching_status.get(dev_id):
            start_app_menu = Menu(MenuItem("Loading apps...", None, enabled=False))
        else:
            def trigger_fetch(d, l):
                return lambda icon, item: fetch_apps(d, l)
            start_app_menu = Menu(MenuItem("Fetch apps", trigger_fetch(dev_id, dev_name)))

        label = f"{dev_name} ({dev_id[:8]})"

        items.append(
            MenuItem(
                label,
                Menu(
                    MenuItem("Start stream", make_action(dev_id)),
                    MenuItem("Start an App", start_app_menu)
                )
            )
        )

    return Menu(
        *items,
        MenuItem("Refresh", lambda icon, item: refresh_devices()),
        MenuItem("Exit", lambda icon, item: icon.stop())
    )


def refresh_devices():
    global devices_cache

    ids = get_adb_devices()
    new_cache = []

    for dev in ids:
        name = get_device_name(dev)
        new_cache.append((dev, name))

    devices_cache = new_cache

    if icon:
        icon.menu = build_menu()
        icon.update_menu()


def auto_refresh_loop():
    while True:
        refresh_devices()
        time.sleep(5)


if __name__ == "__main__":
    if "--nav-button" in sys.argv:
        try:
            btn_type = sys.argv[2]
            dev_id = sys.argv[3]
            dev_label = sys.argv[4]
            run_nav_button_process(btn_type, dev_id, dev_label)
        except:
            pass
        sys.exit(0)

    image = load_icon()

    icon = Icon("ADB Tray", image, "ADB Devices")

    load_favorites()
    refresh_devices()

    threading.Thread(target=auto_refresh_loop, daemon=True).start()

    icon.run()