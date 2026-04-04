import socket
import subprocess
import sys
import logging
import time
import json
import re
import threading
import math
import urllib.request
import tkinter as tk
from tkinter import messagebox, font, ttk, filedialog

logging.basicConfig(level=logging.INFO)

# ==============================================================================
# ========================= [全域變數宣告] =================================
# ==============================================================================
device_connected = False
current_location_process = None

tunnel_process = None
tunnel_active = False

connected_devices = [] 
current_udid = None    

longitude_entry = None
latitude_entry = None
target_lon_entry = None
target_lat_entry = None
speed_entry = None
info_label = None
live_lat_label = None
live_lon_label = None
connection_status_label = None
tunnel_status_label = None 
engine_status_label = None 
device_dropdown = None 

joystick_dx = 0
joystick_dy = 0
is_joystick_moving = False

# ==============================================================================
# ========================= [核心功能與引擎 (v2.1.1 破壁者)] ===============
# ==============================================================================

def get_rsd_info(udid):
    try:
        req = urllib.request.Request("http://127.0.0.1:49151/")
        with urllib.request.urlopen(req) as resp:
            raw_data = resp.read().decode('utf-8')
            data = json.loads(raw_data)
            
            if isinstance(data, dict):
                for key, val in data.items():
                    if udid in key:
                        if isinstance(val, list) and len(val) > 0:
                            target = val[0]
                            host = target.get("tunnel-address") or target.get("rsd_address")
                            port = target.get("tunnel-port") or target.get("rsd_port")
                            return host, port
                        elif isinstance(val, dict):
                            host = val.get("tunnel-address") or val.get("rsd_address")
                            port = val.get("tunnel-port") or val.get("rsd_port")
                            return host, port
                            
            elif isinstance(data, list):
                for d in data:
                    if isinstance(d, dict) and (d.get("Identifier") == udid or d.get("udid") == udid):
                        host = d.get("tunnel-address") or d.get("rsd_address")
                        port = d.get("tunnel-port") or d.get("rsd_port")
                        return host, port
                        
    except Exception as e:
        logging.error(f"無法取得 RSD 資訊: {e}")
    return None, None

class ContinuousLocationEngine(threading.Thread):
    def __init__(self, udid, ios_major_version):
        super().__init__()
        self.udid = udid
        self.ios_major_version = ios_major_version
        self.running = True
        self.target_lat = None
        self.target_lon = None
        self.daemon = True
        
    def update_target(self, lat, lon):
        self.target_lat = lat
        self.target_lon = lon

    def get_dvt_service(self):
        try:
            from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider as DvtService
            return DvtService
        except ImportError:
            try:
                from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService as DvtService # type: ignore
                return DvtService
            except ImportError:
                raise ImportError("底層模組解析失敗，無法找到 DvtProvider！")

    def run(self):
        logging.info(f"🚀 啟動 Pure Python 底層引擎 (UDID: {self.udid[:8]} | iOS {self.ios_major_version})")
        if self.ios_major_version < 17:
            self.run_sync()
        else:
            import asyncio
            asyncio.run(self.run_async())

    def run_sync(self):
        try:
            DvtService = self.get_dvt_service()
            from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation
            from pymobiledevice3.lockdown import create_using_usbmux
            
            lockdown = create_using_usbmux(serial=self.udid)
            with DvtService(lockdown=lockdown) as dvt:
                import asyncio
                asyncio.run(self._simulation_loop_async(dvt, LocationSimulation))
        except Exception as e:
            logging.error(f"🚨 Pure Python 引擎 (Sync) 崩潰: {e}")

    async def run_async(self):
        try:
            DvtService = self.get_dvt_service()
            from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation
            from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
            
            host, port = get_rsd_info(self.udid)
            if not host or not port:
                logging.error("❌ 無法取得 RSD 資訊，請確認 tunneld 是否啟動。")
                return
            
            async with RemoteServiceDiscoveryService((host, port)) as rsd:
                is_dvt_async = hasattr(DvtService, '__aenter__')
                if is_dvt_async:
                    async with DvtService(lockdown=rsd) as dvt:
                        await self._simulation_loop_async(dvt, LocationSimulation)
                else:
                    with DvtService(lockdown=rsd) as dvt:
                        await self._simulation_loop_async(dvt, LocationSimulation)
                        
        except Exception as e:
            logging.error(f"🚨 Pure Python 引擎 (Async) 崩潰: {e}")

    async def _simulation_loop_async(self, dvt, LocationSimulation):
        import inspect
        import asyncio
        loc_sim = LocationSimulation(dvt)

        async def _core_loop():
            last_lat, last_lon = None, None
            sim_func = getattr(loc_sim, "set", getattr(loc_sim, "simulate_location", None))
            if not sim_func:
                logging.error("🚨 找不到座標發射函數！")
                return
                
            is_async_func = inspect.iscoroutinefunction(sim_func)
            logging.info(f"✅ DVT 通道建立成功！(發射器: {sim_func.__name__}) 🚀 開始極速連發")
            
            while self.running:
                if self.target_lat is not None and self.target_lon is not None:
                    if (self.target_lat, self.target_lon) != (last_lat, last_lon):
                        try:
                            if is_async_func:
                                await sim_func(self.target_lat, self.target_lon)
                            else:
                                sim_func(self.target_lat, self.target_lon)
                            last_lat, last_lon = self.target_lat, self.target_lon
                        except Exception as e:
                            logging.error(f"管道斷開: {e}")
                            break
                await asyncio.sleep(0.1)

        if hasattr(loc_sim, '__aenter__'):
            async with loc_sim:
                await _core_loop()
        elif hasattr(loc_sim, '__enter__'):
            with loc_sim:
                await _core_loop()
        else:
            if hasattr(loc_sim, 'connect'):
                if inspect.iscoroutinefunction(loc_sim.connect):
                    await loc_sim.connect()
                else:
                    loc_sim.connect()
            await _core_loop()
            
    def stop(self):
        self.running = False

pure_engine = None

def start_tunneld_engine():
    global tunnel_process, tunnel_active
    if tunnel_process is not None: return
    creationflags = 0x08000000 if sys.platform == "win32" else 0
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/IM", "pymobiledevice3.exe", "/T"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creationflags)
            time.sleep(1) 
        tunnel_process = subprocess.Popen(["pymobiledevice3", "remote", "tunneld"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creationflags)
        tunnel_active = True
    except Exception:
        tunnel_active = False

def strip_ansi_codes(text):
    return re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]').sub('', text)

def monitor_device_connection():
    global device_connected, tunnel_active, tunnel_process, connected_devices
    while True:
        try:
            creationflags = 0x08000000 if sys.platform == "win32" else 0
            result = subprocess.run(["pymobiledevice3", "usbmux", "list"], capture_output=True, text=True, check=True, timeout=10, creationflags=creationflags)
            clean_output = strip_ansi_codes(result.stdout)
            if clean_output.strip(): 
                devices_json = json.loads(clean_output)
                connected_devices = [{"name": f"{d.get('DeviceName', 'Unknown')} ({d.get('Identifier','')[:8]}...)", "udid": d.get("Identifier", ""), "version": d.get("ProductVersion", "16.0")} for d in devices_json if d.get("Identifier")]
                device_connected = len(connected_devices) > 0
            else:
                connected_devices = []
                device_connected = False
        except Exception:
            connected_devices = []
            device_connected = False
        
        if tunnel_process and tunnel_process.poll() is not None:
            tunnel_active = False
            tunnel_process = None
        time.sleep(3)

def mount_developer_disk_image():
    try:
        creationflags = 0x08000000 if sys.platform == "win32" else 0
        result = subprocess.run(["pymobiledevice3", "mounter", "auto-mount"], capture_output=True, text=True, check=True, creationflags=creationflags)
        return not result.stderr
    except Exception: return False

def save_as():
    global longitude_entry, latitude_entry
    file_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")])
    if file_path:
        with open(file_path, 'w') as file:
            file.write(f"{longitude_entry.get()},{latitude_entry.get()}")
        messagebox.showinfo("Save As", "Data saved successfully")

def parse_smart_coordinates(coord_str):
    coord_str = coord_str.strip().upper()
    dms_matches = re.findall(r'(\d+)[°\s]+(\d+)[\'\s]+([\d.]+)["\s]*([NSEW])', coord_str)
    if len(dms_matches) == 2:
        lat, lon = None, None
        for match in dms_matches:
            deg, min, sec, direction = match
            dd = float(deg) + float(min) / 60 + float(sec) / 3600
            if direction in ['S', 'W']: dd = -dd
            if direction in ['N', 'S']: lat = dd
            elif direction in ['E', 'W']: lon = dd
        if lat is not None and lon is not None: return lat, lon
    try:
        parts = [p for p in re.split(r'[,\s]+', re.sub(r'[^\d\.\-\,\s]', '', coord_str).strip()) if p] 
        if len(parts) >= 2: return float(parts[0]), float(parts[1])
    except Exception: pass
    return None, None

def load():
    global longitude_entry, latitude_entry, live_lat_label, live_lon_label
    filepath = filedialog.askopenfilename(title="選擇座標檔案", filetypes=(("Text Files", "*.txt"), ("All Files", "*.*")))
    if not filepath: return
    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            lat, lon = parse_smart_coordinates(file.read())
            if lat is not None and lon is not None:
                latitude_entry.delete(0, tk.END); latitude_entry.insert(0, f"{lat:.6f}")
                longitude_entry.delete(0, tk.END); longitude_entry.insert(0, f"{lon:.6f}")
                if live_lat_label and live_lon_label:
                    live_lat_label.config(text=f"LAT: {lat:.6f}")
                    live_lon_label.config(text=f"LON: {lon:.6f}")
                messagebox.showinfo("Success", "座標載入成功！")
            else: messagebox.showerror("解析失敗", "無法辨識檔案中的座標格式！")
    except Exception as e: messagebox.showerror("錯誤", f"讀取檔案發生錯誤：\n{e}")

def validate_coordinates(longitude, latitude):
    return -180 <= longitude <= 180 and -90 <= latitude <= 90

def get_safe_ios_version(udid):
    for d in connected_devices:
        if d["udid"] == udid:
            match = re.search(r'^(\d+)', str(d["version"]))
            return int(match.group(1)) if match else 16
    return 16

def update_location_bg(latitude, longitude):
    global current_udid, pure_engine, engine_status_label
    if not current_udid: return
    ios_major_version = get_safe_ios_version(current_udid)
    if engine_status_label:
        engine_status_label.config(text="⚙️ 引擎: Pure Python (極速)", fg='#4fc1ff')
    if pure_engine is None or pure_engine.udid != current_udid or not pure_engine.is_alive():
        if pure_engine: pure_engine.stop()
        pure_engine = ContinuousLocationEngine(current_udid, ios_major_version)
        pure_engine.start()
    pure_engine.update_target(latitude, longitude)

def safe_exit():
    global tunnel_process, pure_engine
    if pure_engine: pure_engine.stop()
    if tunnel_process is not None:
        try: tunnel_process.terminate(); tunnel_process.wait(timeout=2)
        except: tunnel_process.kill()
    sys.exit(0)
    
def get_distance(lat1, lon1, lat2, lon2):
    R = 6371000  
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi, delta_lambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0)**2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

def set_location():
    global longitude_entry, latitude_entry, live_lat_label, live_lon_label, current_udid
    if not current_udid: return messagebox.showerror("Error", "請先選擇設備！")
    try:
        longitude, latitude = float(longitude_entry.get()), float(latitude_entry.get())
        if not validate_coordinates(longitude, latitude): return messagebox.showerror("Error", "座標範圍錯誤")
        if get_safe_ios_version(current_udid) < 17 and not mount_developer_disk_image():
            return messagebox.showerror("Error", "掛載 Developer Disk Image 失敗。")
        update_location_bg(latitude, longitude)
        if live_lat_label: live_lat_label.config(text=f"LAT: {latitude:.6f}")
        if live_lon_label: live_lon_label.config(text=f"LON: {longitude:.6f}")
    except ValueError: messagebox.showerror("Error", "請輸入有效數字。")

# ==============================================================================
# ========================= [v2.2.1 Pro Dashboard UI] ==========================
# ==============================================================================
def create_card(parent, title, bg_color, fg_color, font):
    card = tk.Frame(parent, bg=bg_color, padx=15, pady=15)
    tk.Label(card, text=title, font=font, bg=bg_color, fg=fg_color, anchor="w").pack(fill="x", pady=(0, 10))
    return card

def main():
    app_bg = '#121212'; card_bg = '#1e1e1e'; input_bg = '#2d2d30'; accent = '#0a84ff'; success = '#32d74b'; warning = '#ff453a'; text_main = '#ffffff'; text_muted = '#8e8e93'   

    global longitude_entry, latitude_entry, target_lon_entry, target_lat_entry, speed_entry
    global live_lat_label, live_lon_label, info_label
    global connection_status_label, tunnel_status_label, engine_status_label, device_dropdown
    global joystick_dx, joystick_dy, is_joystick_moving

    start_tunneld_engine()
    threading.Thread(target=monitor_device_connection, daemon=True).start()

    root = tk.Tk()
    root.title("Rei's iOS Location Simulator Pro v2.2.1")
    root.protocol("WM_DELETE_WINDOW", safe_exit)
    root.configure(bg=app_bg)
    
    ui_font = "Microsoft JhengHei UI"
    f_title = font.Font(family=ui_font, size=16, weight="bold")
    f_card_title = font.Font(family=ui_font, size=12, weight="bold")
    f_main = font.Font(family=ui_font, size=11)
    f_small = font.Font(family=ui_font, size=10)
    f_radar = font.Font(family="Consolas", size=18, weight="bold")

    window_width, window_height = 850, 700
    center_y = max(0, int((root.winfo_screenheight() / 2) - (window_height / 2) - 50))
    root.geometry(f"{window_width}x{window_height}+100+{center_y}")

    style = ttk.Style()
    style.theme_use('clam')
    style.configure('TCombobox', fieldbackground=input_bg, background=card_bg, foreground=text_main, borderwidth=0)
    style.map('TCombobox', fieldbackground=[('readonly', input_bg)], selectbackground=[('readonly', accent)])

    header_frame = tk.Frame(root, bg=app_bg, pady=10)
    header_frame.pack(fill="x", padx=20)
    tk.Label(header_frame, text="Rei's iOS Location Simulator", font=f_title, bg=app_bg, fg=text_main).pack(side="left")
    tk.Label(header_frame, text="Pro Dashboard Edition", font=f_small, bg=app_bg, fg=accent).pack(side="left", padx=10)

    main_container = tk.Frame(root, bg=app_bg)
    main_container.pack(fill="both", expand=True, padx=20, pady=(0, 20))

    # --- 左欄 (Left Column) : 情報與狀態 ---
    left_col = tk.Frame(main_container, bg=app_bg)
    left_col.pack(side="left", fill="both", expand=True, padx=(0, 10))

    status_card = create_card(left_col, "SYSTEM STATUS", card_bg, text_muted, f_small)
    status_card.pack(fill="x", pady=(0, 10))
    
    connection_status_label = tk.Label(status_card, text="🔍 尋找設備中...", font=f_main, bg=card_bg, fg=warning, anchor="w"); connection_status_label.pack(fill="x", pady=2)
    tunnel_status_label = tk.Label(status_card, text="🌐 Tunnel: 啟動中...", font=f_main, bg=card_bg, fg=text_main, anchor="w"); tunnel_status_label.pack(fill="x", pady=2)
    engine_status_label = tk.Label(status_card, text="⚙️ 引擎: 待命中", font=f_main, bg=card_bg, fg=text_main, anchor="w"); engine_status_label.pack(fill="x", pady=2)

    device_frame = tk.Frame(status_card, bg=card_bg); device_frame.pack(fill="x", pady=(10, 0))
    tk.Label(device_frame, text="TARGET DEVICE:", font=f_small, bg=card_bg, fg=text_muted).pack(side="left")
    device_var = tk.StringVar(); device_dropdown = ttk.Combobox(device_frame, textvariable=device_var, state="readonly", font=f_small, width=20); device_dropdown.pack(side="right", fill="x", expand=True, padx=(10, 0))

    def on_device_selected(event):
        global current_udid
        idx = device_dropdown.current()
        if 0 <= idx < len(connected_devices): current_udid = connected_devices[idx]["udid"]
    device_dropdown.bind("<<ComboboxSelected>>", on_device_selected)

    def update_status_labels():
        global device_connected, tunnel_active, connected_devices, current_udid
        new_vals = [d['name'] for d in connected_devices]
        if list(device_dropdown['values']) != new_vals:
            device_dropdown['values'] = new_vals
            if new_vals:
                if device_dropdown.get() not in new_vals: device_dropdown.current(0); current_udid = connected_devices[0]['udid']
            else: device_dropdown.set('No Device Detected'); current_udid = None

        if device_connected and current_udid:
            dev = next((d for d in connected_devices if d["udid"] == current_udid), None)
            connection_status_label.config(text=f"🎯 連線: {dev['name'] if dev else 'Unknown'} (iOS {dev['version'] if dev else '?'})", fg=success)
        else: connection_status_label.config(text="❌ 未鎖定任何設備", fg=warning)
        tunnel_status_label.config(text="🌐 Tunnel: 運作中", fg=success) if tunnel_active else tunnel_status_label.config(text="🌐 Tunnel: 已停止", fg=warning)
        root.after(1000, update_status_labels)
    update_status_labels()

    radar_card = create_card(left_col, "LIVE RADAR", card_bg, text_muted, f_small); radar_card.pack(fill="x", pady=10)
    live_lat_label = tk.Label(radar_card, text="LAT: --.------", font=f_radar, bg=card_bg, fg=accent); live_lat_label.pack(anchor="center", pady=5)
    live_lon_label = tk.Label(radar_card, text="LON: --.------", font=f_radar, bg=card_bg, fg=accent); live_lon_label.pack(anchor="center", pady=5)

    tk.Button(left_col, text="EXIT SYSTEM", font=f_card_title, bg=warning, fg=text_main, borderwidth=0, pady=10, command=safe_exit).pack(side="bottom", fill="x")

    # --- 右欄 (Right Column) : 操作 ---
    right_col = tk.Frame(main_container, bg=app_bg)
    right_col.pack(side="right", fill="both", expand=True, padx=(10, 0))

    # [卡片] 資料管理 (移至右欄最上方)
    data_card = create_card(right_col, "DATA MANAGEMENT (存取)", card_bg, text_muted, f_small)
    data_card.pack(fill="x", pady=(0, 10))
    btn_frame = tk.Frame(data_card, bg=card_bg); btn_frame.pack(fill="x")
    tk.Button(btn_frame, text="Load Data", font=f_main, bg=input_bg, fg=text_main, borderwidth=0, command=load).pack(side="left", fill="x", expand=True, padx=(0, 5))
    tk.Button(btn_frame, text="Save Data", font=f_main, bg=input_bg, fg=text_main, borderwidth=0, command=save_as).pack(side="left", fill="x", expand=True, padx=(5, 0))

    # [卡片] 座標設定
    coord_card = create_card(right_col, "TELEPORT (降落)", card_bg, accent, f_card_title); coord_card.pack(fill="x", pady=10)
    e_f1 = tk.Frame(coord_card, bg=card_bg); e_f1.pack(fill="x", pady=5)
    tk.Label(e_f1, text="Latitude", font=f_small, bg=card_bg, fg=text_muted, width=10, anchor="w").pack(side="left")
    latitude_entry = tk.Entry(e_f1, font=f_main, bg=input_bg, fg=text_main, insertbackground=text_main, borderwidth=0); latitude_entry.pack(side="left", fill="x", expand=True, ipady=3)
    e_f2 = tk.Frame(coord_card, bg=card_bg); e_f2.pack(fill="x", pady=5)
    tk.Label(e_f2, text="Longitude", font=f_small, bg=card_bg, fg=text_muted, width=10, anchor="w").pack(side="left")
    longitude_entry = tk.Entry(e_f2, font=f_main, bg=input_bg, fg=text_main, borderwidth=0); longitude_entry.pack(side="left", fill="x", expand=True, ipady=3)
    tk.Button(coord_card, text="ENGAGE TELEPORT", font=f_main, bg=accent, fg=text_main, borderwidth=0, pady=8, command=set_location).pack(fill="x", pady=(15, 0))

    # [卡片] 自動導航 (預設收合)
    nav_container = tk.Frame(right_col, bg=card_bg); nav_container.pack(fill="x", pady=10)
    def toggle_nav():
        if nav_content.winfo_ismapped(): nav_content.pack_forget(); nav_toggle_btn.config(text="▶  NAVIGATION (自動導航)")
        else: nav_content.pack(fill="x", padx=15, pady=(0, 15)); nav_toggle_btn.config(text="▼  NAVIGATION (自動導航)")
    nav_toggle_btn = tk.Button(nav_container, text="▶  NAVIGATION (自動導航)", font=f_card_title, bg=card_bg, fg=accent, borderwidth=0, anchor="w", padx=15, pady=15, command=toggle_nav); nav_toggle_btn.pack(fill="x")
    nav_content = tk.Frame(nav_container, bg=card_bg)
    n_f1 = tk.Frame(nav_content, bg=card_bg); n_f1.pack(fill="x", pady=2)
    tk.Label(n_f1, text="Target Lat:", font=f_small, bg=card_bg, fg=text_muted, width=10, anchor="w").pack(side="left")
    target_lat_entry = tk.Entry(n_f1, font=f_main, bg=input_bg, fg=text_main, borderwidth=0); target_lat_entry.pack(side="left", fill="x", expand=True, ipady=2)
    n_f2 = tk.Frame(nav_content, bg=card_bg); n_f2.pack(fill="x", pady=2)
    tk.Label(n_f2, text="Target Lon:", font=f_small, bg=card_bg, fg=text_muted, width=10, anchor="w").pack(side="left")
    target_lon_entry = tk.Entry(n_f2, font=f_main, bg=input_bg, fg=text_main, borderwidth=0); target_lon_entry.pack(side="left", fill="x", expand=True, ipady=2)
    n_f3 = tk.Frame(nav_content, bg=card_bg); n_f3.pack(fill="x", pady=2)
    tk.Label(n_f3, text="Speed (km/h):", font=f_small, bg=card_bg, fg=text_muted, width=10, anchor="w").pack(side="left")
    speed_entry = tk.Entry(n_f3, font=f_main, bg=input_bg, fg=text_main, borderwidth=0); speed_entry.insert(0, "15"); speed_entry.pack(side="left", fill="x", expand=True, ipady=2)
    info_label = tk.Label(nav_content, text="輸入目標計算時間", font=f_small, bg=card_bg, fg=text_muted); info_label.pack(pady=5)

    def calculate_eta(*args):
        try:
            dist = get_distance(float(latitude_entry.get()), float(longitude_entry.get()), float(target_lat_entry.get()), float(target_lon_entry.get())) / 1000
            info_label.config(text=f"距離: {dist:.2f} km | 預估: {(dist/float(speed_entry.get())*60 if float(speed_entry.get())>0 else 0):.1f} 分鐘", fg=text_main)
        except ValueError: pass
    for e in [longitude_entry, latitude_entry, target_lon_entry, target_lat_entry, speed_entry]: e.bind("<KeyRelease>", calculate_eta)

    def start_custom_walk():
        if not current_udid: return messagebox.showerror("Error", "請先選擇設備！")
        try:
            slat, slon = float(latitude_entry.get()), float(longitude_entry.get()); elat, elon = float(target_lat_entry.get()), float(target_lon_entry.get()); speed = float(speed_entry.get())
            if speed <= 0: return
            dist_m = get_distance(slat, slon, elat, elon); delay = 0.5; steps = max(1, int((dist_m / (speed * (1000 / 3600))) / delay))
            def walk_loop():
                start_btn.config(state="disabled", bg=input_bg); start_time = time.time()
                for i in range(steps + 1):
                    clat = slat + (elat - slat) * (i / steps); clon = slon + (elon - slon) * (i / steps); update_location_bg(clat, clon)
                    latitude_entry.delete(0, tk.END); latitude_entry.insert(0, f"{clat:.6f}"); longitude_entry.delete(0, tk.END); longitude_entry.insert(0, f"{clon:.6f}")
                    live_lat_label.config(text=f"LAT: {clat:.6f}"); live_lon_label.config(text=f"LON: {clon:.6f}")
                    info_label.config(text=f"導航中: {((i/steps)*100):.1f}% | {int(time.time()-start_time)//60:02d}:{int(time.time()-start_time)%60:02d}"); time.sleep(delay)
                info_label.config(text="已抵達終點！", fg=success); start_btn.config(state="normal", bg=accent)
            threading.Thread(target=walk_loop, daemon=True).start()
        except ValueError: messagebox.showerror("Error", "輸入無效。")
    start_btn = tk.Button(nav_content, text="START ROUTE", font=f_main, bg=accent, fg=text_main, borderwidth=0, pady=5, command=start_custom_walk); start_btn.pack(fill="x", pady=(5, 0))

    # [卡片] 虛擬搖桿 (預設收合)
    joy_container = tk.Frame(right_col, bg=card_bg); joy_container.pack(fill="x", pady=10)
    def toggle_joystick():
        if joy_content.winfo_ismapped(): joy_content.pack_forget(); joy_toggle_btn.config(text="▶  VIRTUAL JOYSTICK (虛擬搖桿)")
        else: joy_content.pack(fill="x", padx=15, pady=(0, 15)); joy_toggle_btn.config(text="▼  VIRTUAL JOYSTICK (虛擬搖桿)")
    joy_toggle_btn = tk.Button(joy_container, text="▶  VIRTUAL JOYSTICK (虛擬搖桿)", font=f_card_title, bg=card_bg, fg=accent, borderwidth=0, anchor="w", padx=15, pady=15, command=toggle_joystick); joy_toggle_btn.pack(fill="x")
    joy_content = tk.Frame(joy_container, bg=card_bg); canvas_size, max_radius = 160, 60; center = canvas_size // 2
    joy_canvas = tk.Canvas(joy_content, width=canvas_size, height=canvas_size, bg=card_bg, highlightthickness=0); joy_canvas.pack(anchor="center", pady=10)
    joy_canvas.create_oval(center - max_radius, center - max_radius, center + max_radius, center + max_radius, fill=app_bg, outline=input_bg, width=2)
    stick = joy_canvas.create_oval(center - 20, center - 20, center + 20, center + 20, fill=accent, outline=accent)
    def move_stick(event):
        global joystick_dx, joystick_dy, is_joystick_moving
        dx, dy = event.x - center, event.y - center; distance = math.hypot(dx, dy)
        if distance > max_radius: dx, dy = dx * (max_radius / distance), dy * (max_radius / distance)
        joy_canvas.coords(stick, center + dx - 20, center + dy - 20, center + dx + 20, center + dy + 20); joystick_dx, joystick_dy, is_joystick_moving = dx, dy, True
    def release_stick(event):
        global joystick_dx, joystick_dy, is_joystick_moving
        joy_canvas.coords(stick, center - 20, center - 20, center + 20, center + 20); joystick_dx, joystick_dy, is_joystick_moving = 0, 0, False
    joy_canvas.bind("<B1-Motion>", move_stick); joy_canvas.bind("<ButtonRelease-1>", release_stick)

    def joystick_engine():
        global joystick_dx, joystick_dy, is_joystick_moving, current_udid
        while True:
            if is_joystick_moving and (joystick_dx != 0 or joystick_dy != 0) and current_udid:
                try:
                    delay = 0.1; clat, clon = float(latitude_entry.get()), float(longitude_entry.get())
                    dist = (15.0 * (math.hypot(joystick_dx, joystick_dy) / max_radius)) * (delay / 3600); ang = math.atan2(-joystick_dy, joystick_dx)
                    nlat = clat + ((dist * math.sin(ang)) / 111.111); nlon = clon + ((dist * math.cos(ang)) / (111.111 * math.cos(math.radians(clat))))
                    latitude_entry.delete(0, tk.END); latitude_entry.insert(0, f"{nlat:.6f}"); longitude_entry.delete(0, tk.END); longitude_entry.insert(0, f"{nlon:.6f}")
                    live_lat_label.config(text=f"LAT: {nlat:.6f}"); live_lon_label.config(text=f"LON: {nlon:.6f}"); update_location_bg(nlat, nlon)
                except Exception: pass
                time.sleep(delay)
            else: time.sleep(0.1)
    threading.Thread(target=joystick_engine, daemon=True).start()

    root.mainloop()

if __name__ == "__main__":
    main()