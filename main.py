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
# ========================= [核心功能與引擎] ===============================
# ==============================================================================

def get_rsd_info(udid):
    """向 tunneld 請求 RSD 通訊埠 (支援最新 tunnel-address 陣列格式與舊版格式)"""
    try:
        req = urllib.request.Request("http://127.0.0.1:49151/")
        with urllib.request.urlopen(req) as resp:
            raw_data = resp.read().decode('utf-8')
            # 已經抓到蟲了，可以把 DEBUG 註解掉，保持終端機乾淨
            # logging.info(f"🕵️‍♂️ [DEBUG] Tunneld 原始回傳: {raw_data}") 
            
            data = json.loads(raw_data)
            
            # 方案 A: 新版格式 {"UDID": [{"tunnel-address": "...", "tunnel-port": ...}]}
            if isinstance(data, dict):
                for key, val in data.items():
                    # 只要包含你的 UDID 前綴 (00008110) 就命中
                    if udid in key:
                        # 情況 1: 值是列表 (最新版)
                        if isinstance(val, list) and len(val) > 0:
                            target = val[0]
                            host = target.get("tunnel-address") or target.get("rsd_address")
                            port = target.get("tunnel-port") or target.get("rsd_port")
                            return host, port
                        # 情況 2: 值是字典 (中期版本)
                        elif isinstance(val, dict):
                            host = val.get("tunnel-address") or val.get("rsd_address")
                            port = val.get("tunnel-port") or val.get("rsd_port")
                            return host, port
                            
            # 方案 B: 舊版格式 (List)
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
                from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService as DvtService
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

    # 🎯 [終極改寫] 完美接住 LocationSimulation 的 async with 要求
    async def _simulation_loop_async(self, dvt, LocationSimulation):
        import inspect
        import asyncio
        loc_sim = LocationSimulation(dvt)

        # 把核心發射邏輯包裝起來，等連線建立後再呼叫
        async def _core_loop():
            last_lat, last_lon = None, None
            sim_func = getattr(loc_sim, "set", getattr(loc_sim, "simulate_location", None))
            if not sim_func:
                logging.error("🚨 找不到座標發射函數！")
                return
                
            is_async_func = inspect.iscoroutinefunction(sim_func)
            logging.info(f"✅ DVT 專屬通道建立成功！(使用發射器: {sim_func.__name__}) 🚀 開始 0.1s 極速連發")
            
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

        # 🛡️ 動態適應: 檢查發射器是否需要 async with 開啟
        if hasattr(loc_sim, '__aenter__'):
            async with loc_sim:
                await _core_loop()
        elif hasattr(loc_sim, '__enter__'):
            with loc_sim:
                await _core_loop()
        else:
            # 如果它要求 await connect() 的備用方案
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
    if tunnel_process is not None:
        return

    creationflags = 0
    if sys.platform == "win32":
        creationflags = 0x08000000 
        try:
            subprocess.run(["taskkill", "/F", "/IM", "pymobiledevice3.exe", "/T"], 
                           stdout=subprocess.DEVNULL, 
                           stderr=subprocess.DEVNULL, 
                           creationflags=creationflags)
            time.sleep(1) 
        except Exception:
            pass

    command = ["pymobiledevice3", "remote", "tunneld"]
    try:
        tunnel_process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags
        )
        tunnel_active = True
    except Exception as e:
        tunnel_active = False

def strip_ansi_codes(text):
    ansi_escape = re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')
    return ansi_escape.sub('', text)

def monitor_device_connection():
    global device_connected, tunnel_active, tunnel_process, connected_devices
    while True:
        try:
            creationflags = 0x08000000 if sys.platform == "win32" else 0
            result = subprocess.run(["pymobiledevice3", "usbmux", "list"],
                                    capture_output=True, text=True, check=True, timeout=10, creationflags=creationflags)
            clean_output = strip_ansi_codes(result.stdout)
            if clean_output.strip(): 
                devices_json = json.loads(clean_output)
                new_list = []
                for d in devices_json:
                    udid = d.get("Identifier", "")
                    name = d.get("DeviceName", d.get("ProductType", "Unknown Device"))
                    version = d.get("ProductVersion", "16.0")
                    if udid:
                        new_list.append({"name": f"{name} ({udid[:8]}...)", "udid": udid, "version": version})
                
                connected_devices = new_list
                device_connected = len(connected_devices) > 0
            else:
                connected_devices = []
                device_connected = False
        except Exception:
            connected_devices = []
            device_connected = False
        
        if tunnel_process is not None:
            if tunnel_process.poll() is not None:
                tunnel_active = False
                tunnel_process = None

        time.sleep(3)

def mount_developer_disk_image():
    try:
        creationflags = 0x08000000 if sys.platform == "win32" else 0
        result = subprocess.run(["pymobiledevice3", "mounter", "auto-mount"],
                                capture_output=True, text=True, check=True, creationflags=creationflags)
        if result.stderr:
            return False
        return True
    except Exception:
        return False

def save_as():
    global longitude_entry, latitude_entry
    file_path = filedialog.asksaveasfilename(defaultextension=".txt",
                                             filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")])
    if file_path:
        with open(file_path, 'w') as file:
            file.write(f"{longitude_entry.get()},{latitude_entry.get()}")
        messagebox.showinfo("Save As", "Data saved successfully")

def parse_smart_coordinates(coord_str):
    coord_str = coord_str.strip().upper()
    dms_pattern = r'(\d+)[°\s]+(\d+)[\'\s]+([\d.]+)["\s]*([NSEW])'
    dms_matches = re.findall(dms_pattern, coord_str)
    
    if len(dms_matches) == 2:
        lat, lon = None, None
        for match in dms_matches:
            deg, min, sec, direction = match
            dd = float(deg) + float(min) / 60 + float(sec) / 3600
            if direction in ['S', 'W']:
                dd = -dd
            if direction in ['N', 'S']:
                lat = dd
            elif direction in ['E', 'W']:
                lon = dd
        if lat is not None and lon is not None:
            return lat, lon

    try:
        clean_str = re.sub(r'[^\d\.\-\,\s]', '', coord_str)
        parts = re.split(r'[,\s]+', clean_str.strip())
        parts = [p for p in parts if p] 
        if len(parts) >= 2:
            return float(parts[0]), float(parts[1])
    except Exception:
        pass
    return None, None

def load():
    global longitude_entry, latitude_entry, live_lat_label, live_lon_label
    filepath = filedialog.askopenfilename(
        title="選擇座標檔案",
        filetypes=(("Text Files", "*.txt"), ("All Files", "*.*"))
    )
    if not filepath:
        return
    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            content = file.read()
            lat, lon = parse_smart_coordinates(content)
            if lat is not None and lon is not None:
                latitude_entry.delete(0, tk.END)
                latitude_entry.insert(0, f"{lat:.6f}")
                longitude_entry.delete(0, tk.END)
                longitude_entry.insert(0, f"{lon:.6f}")
                
                if live_lat_label and live_lon_label:
                    live_lat_label.config(text=f"緯度 (Lat): {lat:.6f}")
                    live_lon_label.config(text=f"經度 (Lon): {lon:.6f}")
                
                messagebox.showinfo("Success", f"座標載入成功！\n緯度 (Lat): {lat:.6f}\n經度 (Lon): {lon:.6f}")
            else:
                messagebox.showerror("解析失敗", "無法辨識檔案中的座標格式！")
    except Exception as e:
        messagebox.showerror("錯誤", f"讀取檔案時發生錯誤：\n{e}")

def validate_coordinates(longitude, latitude):
    if -180 <= longitude <= 180 and -90 <= latitude <= 90:
        return True
    return False

def get_safe_ios_version(udid):
    ios_version_str = "16.0"
    for d in connected_devices:
        if d["udid"] == udid:
            ios_version_str = d["version"]
            break
    match = re.search(r'^(\d+)', str(ios_version_str))
    return int(match.group(1)) if match else 16

def update_location_bg(latitude, longitude):
    global current_udid, pure_engine, engine_status_label
    
    if not current_udid:
        return

    ios_major_version = get_safe_ios_version(current_udid)

    # ✨ 完美達成 C計畫：全設備統一使用 Pure Python 高頻專線
    if engine_status_label:
        engine_status_label.config(text="⚙️ 引擎: Pure Python (極速 0.1s)", fg='#4fc1ff')

    if pure_engine is None or pure_engine.udid != current_udid or not pure_engine.is_alive():
        if pure_engine:
            pure_engine.stop()
        pure_engine = ContinuousLocationEngine(current_udid, ios_major_version)
        pure_engine.start()
        
    pure_engine.update_target(latitude, longitude)

def safe_exit():
    global tunnel_process, pure_engine
    if pure_engine:
        pure_engine.stop()
    if tunnel_process is not None:
        try:
            tunnel_process.terminate()
            tunnel_process.wait(timeout=2)
        except:
            tunnel_process.kill()
    sys.exit(0)
    
def get_distance(lat1, lon1, lat2, lon2):
    R = 6371000  
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0)**2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def set_location():
    global longitude_entry, latitude_entry, live_lat_label, live_lon_label, current_udid
    if not current_udid:
        messagebox.showerror("Error", "請先從上方選單選擇一台目標手機！")
        return

    try:
        longitude = float(longitude_entry.get())
        latitude = float(latitude_entry.get())

        if not validate_coordinates(longitude, latitude):
            messagebox.showerror("Error", "Invalid longitude or latitude range.")
            return

        ios_major_version = get_safe_ios_version(current_udid)
        if ios_major_version < 17:
            if not mount_developer_disk_image():
                messagebox.showerror("Error", "Failed to mount Developer Disk Image.")
                return

        update_location_bg(latitude, longitude)
        
        if live_lat_label and live_lon_label:
            live_lat_label.config(text=f"緯度 (Lat): {latitude:.6f}")
            live_lon_label.config(text=f"經度 (Lon): {longitude:.6f}")
        
        messagebox.showinfo("Success", "Location set successfully!")
    except ValueError:
        messagebox.showerror("Error", "Invalid input for longitude or latitude.")

# ==============================================================================
# ========================= [Rei's Pro Dark Edition UI] ========================
# ==============================================================================
def main():
    main_bg_color = '#121212'    
    frame_bg_color = '#1e1e1e'   
    accent_color = '#0e639c'     
    secondary_color = '#333333'  
    success_color = '#4CAF50'    
    warning_color = '#dc3545'    
    text_color = '#ffffff'       
    radar_color = '#4fc1ff'      

    global longitude_entry, latitude_entry, target_lon_entry, target_lat_entry, speed_entry
    global live_lat_label, live_lon_label, info_label
    global connection_status_label, tunnel_status_label, engine_status_label, device_dropdown
    global joystick_dx, joystick_dy, is_joystick_moving

    start_tunneld_engine()
    threading.Thread(target=monitor_device_connection, daemon=True).start()

    root = tk.Tk()
    root.title("Rei's iOS Location Simulator Pro v2.0.2")
    root.protocol("WM_DELETE_WINDOW", safe_exit)
    
    ui_font_family = "Microsoft JhengHei UI"
    title_font = font.Font(family=ui_font_family, size=16, weight="bold")
    header_font = font.Font(family=ui_font_family, size=12, weight="bold")
    modern_font = font.Font(family=ui_font_family, size=11)
    label_font = font.Font(family=ui_font_family, size=10)
    radar_font = font.Font(family=ui_font_family, size=14, weight="bold")

    root.configure(bg=main_bg_color)
    
    window_width = 500
    window_height = 800
    screen_height = root.winfo_screenheight()
    center_y = max(0, int((screen_height / 2) - (window_height / 2) - 50))
    root.geometry(f"{window_width}x{window_height}+50+{center_y}")

    style = ttk.Style()
    style.theme_use('clam')
    style.configure('TCombobox', fieldbackground='#3c3c3c', background=secondary_color, foreground=text_color, arrowcolor=text_color)
    style.map('TCombobox', fieldbackground=[('readonly', '#3c3c3c')], selectbackground=[('readonly', accent_color)])

    outer_frame = tk.Frame(root, bg=main_bg_color)
    outer_frame.pack(fill="both", expand=True, padx=10, pady=10) 

    canvas = tk.Canvas(outer_frame, bg=main_bg_color, highlightthickness=0)
    scrollbar = ttk.Scrollbar(outer_frame, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    
    main_frame = tk.Frame(canvas, bg=main_bg_color)
    canvas_window = canvas.create_window((0, 0), window=main_frame, anchor="nw")

    def configure_main_frame(event):
        canvas.configure(scrollregion=canvas.bbox("all"))
    def configure_canvas(event):
        canvas.itemconfig(canvas_window, width=event.width - 15)

    main_frame.bind("<Configure>", configure_main_frame)
    canvas.bind("<Configure>", configure_canvas)

    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    root.bind_all("<MouseWheel>", _on_mousewheel)

    main_frame.config(padx=15, pady=10)

    tk.Label(main_frame, text="Rei's iOS Location Simulator", font=title_font, bg=main_bg_color, fg=accent_color).pack(pady=(0, 15))

    status_container = tk.Frame(main_frame, bg=main_bg_color)
    status_container.pack(pady=5)
    
    connection_status_label = tk.Label(status_container, text="🔍 尋找設備中...", font=label_font, bg=main_bg_color, fg=warning_color)
    connection_status_label.grid(row=0, column=0, padx=10)
    
    tunnel_status_label = tk.Label(status_container, text="🌐 Tunnel: 啟動中...", font=label_font, bg=main_bg_color, fg=text_color)
    tunnel_status_label.grid(row=0, column=1, padx=10)

    engine_status_label = tk.Label(status_container, text="⚙️ 引擎: 待命中", font=label_font, bg=main_bg_color, fg=text_color)
    engine_status_label.grid(row=1, column=0, columnspan=2, pady=(5,0))

    tk.Label(status_container, text="選擇目標設備:", font=label_font, bg=main_bg_color, fg=text_color).grid(row=2, column=0, pady=(10,0), sticky="e")
    device_var = tk.StringVar()
    device_dropdown = ttk.Combobox(status_container, textvariable=device_var, state="readonly", font=label_font, width=22)
    device_dropdown.grid(row=2, column=1, pady=(10,0), sticky="w")

    def on_device_selected(event):
        global current_udid
        idx = device_dropdown.current()
        if idx >= 0 and idx < len(connected_devices):
            current_udid = connected_devices[idx]["udid"]
            dev_name = connected_devices[idx]["name"]
            ios_ver = connected_devices[idx]["version"]
            messagebox.showinfo("鎖定目標", f"目標切換至：\n🎯 {dev_name}\n📱 系統版本: iOS {ios_ver}")
            
    device_dropdown.bind("<<ComboboxSelected>>", on_device_selected)

    def update_status_labels():
        global device_connected, tunnel_active, connected_devices, current_udid
        
        current_vals = list(device_dropdown['values'])
        new_vals = [d['name'] for d in connected_devices]
        
        if current_vals != new_vals:
            device_dropdown['values'] = new_vals
            if new_vals:
                if device_dropdown.get() not in new_vals:
                    device_dropdown.current(0)
                    current_udid = connected_devices[0]['udid']
            else:
                device_dropdown.set('沒有偵測到 iOS 設備')
                current_udid = None

        if device_connected and current_udid:
            current_target_name = "未知設備"
            current_ios_ver = "未知"
            for d in connected_devices:
                if d["udid"] == current_udid:
                    current_target_name = d["name"]
                    current_ios_ver = d["version"]
                    break
            connection_status_label.config(text=f"🎯 目標: {current_target_name} (iOS {current_ios_ver})", fg=success_color)
        else:
            connection_status_label.config(text="❌ 尚未鎖定任何設備", fg=warning_color)
            
        if tunnel_active:
            tunnel_status_label.config(text="🌐 Tunnel: 運作中", fg=success_color)
        else:
            tunnel_status_label.config(text="🌐 Tunnel: 已停止", fg=warning_color)
            
        root.after(1000, update_status_labels)
        
    update_status_labels()

    radar_frame = tk.LabelFrame(main_frame, text="📡 實時雷達看板 (Live Radar)", bg=main_bg_color, fg=text_color, font=header_font)
    radar_frame.pack(fill="x", pady=10)
    radar_frame.config(padx=10, pady=10)

    live_lat_label = tk.Label(radar_frame, text="緯度 (Lat): --.------", font=radar_font, bg=main_bg_color, fg=radar_color)
    live_lat_label.pack(anchor="center", pady=2)
    live_lon_label = tk.Label(radar_frame, text="經度 (Lon): --.------", font=radar_font, bg=main_bg_color, fg=radar_color)
    live_lon_label.pack(anchor="center", pady=2)

    file_ops_frame = tk.LabelFrame(main_frame, text="💾 資料管理 (Data)", bg=main_bg_color, fg=text_color, font=header_font)
    file_ops_frame.pack(fill="x", pady=10)
    file_ops_frame.config(padx=10, pady=10)

    data_ops_frame = tk.Frame(file_ops_frame, bg=main_bg_color)
    data_ops_frame.pack(side="top", fill="x")

    save_as_button = tk.Button(data_ops_frame, text="Save As", font=modern_font, bg=secondary_color, fg=text_color, borderwidth=0, padx=10, pady=5, command=save_as)
    save_as_button.pack(side="left", expand=True, padx=(0, 5))

    load_button = tk.Button(data_ops_frame, text="Load", font=modern_font, bg=secondary_color, fg=text_color, borderwidth=0, padx=10, pady=5, command=load)
    load_button.pack(side="right", expand=True, padx=(5, 0))

    coord_frame = tk.LabelFrame(main_frame, text="📍 座標設定 (Coordinate)", bg=main_bg_color, fg=text_color, font=header_font)
    coord_frame.pack(fill="x", pady=10)
    coord_frame.config(padx=10, pady=10)

    tk.Label(coord_frame, text="Longitude (經度):", font=label_font, bg=main_bg_color, fg=text_color).grid(row=0, column=0, sticky="e", pady=5)
    longitude_entry = tk.Entry(coord_frame, font=modern_font, bg='#3c3c3c', fg=text_color, insertbackground=text_color, width=22)
    longitude_entry.grid(row=0, column=1, padx=10, pady=5)

    tk.Label(coord_frame, text="Latitude (緯度):", font=label_font, bg=main_bg_color, fg=text_color).grid(row=1, column=0, sticky="e", pady=5)
    latitude_entry = tk.Entry(coord_frame, font=modern_font, bg='#3c3c3c', fg=text_color, insertbackground=text_color, width=22)
    latitude_entry.grid(row=1, column=1, padx=10, pady=5)

    set_location_button = tk.Button(coord_frame, text="Set Location (單點降落)", font=modern_font, bg=accent_color, fg=text_color, borderwidth=0, padx=10, pady=5, command=set_location)
    set_location_button.grid(row=2, column=0, columnspan=2, pady=(15, 0), sticky="ew")

    nav_container = tk.Frame(main_frame, bg=main_bg_color)
    nav_container.pack(fill="x", pady=10)

    def toggle_nav():
        if nav_content.winfo_ismapped():
            nav_content.pack_forget()
            nav_toggle_btn.config(text="▶ 🚶‍♂️ 自動導航 (Navigation)")
        else:
            nav_content.pack(fill="x")
            nav_toggle_btn.config(text="▼ 🚶‍♂️ 自動導航 (Navigation)")

    nav_toggle_btn = tk.Button(nav_container, text="▼ 🚶‍♂️ 自動導航 (Navigation)", font=header_font, bg=frame_bg_color, fg=text_color, activebackground=secondary_color, activeforeground=text_color, borderwidth=0, anchor="w", padx=10, pady=8, command=toggle_nav)
    nav_toggle_btn.pack(fill="x")

    nav_content = tk.Frame(nav_container, bg=frame_bg_color, padx=10, pady=10)
    nav_content.pack(fill="x")

    tk.Label(nav_content, text="Target Long:", font=label_font, bg=frame_bg_color, fg=text_color).grid(row=0, column=0, sticky="e", pady=5)
    target_lon_entry = tk.Entry(nav_content, font=modern_font, bg='#3c3c3c', fg=text_color, insertbackground=text_color, width=18)
    target_lon_entry.grid(row=0, column=1, padx=10, pady=5)

    tk.Label(nav_content, text="Target Lat:", font=label_font, bg=frame_bg_color, fg=text_color).grid(row=1, column=0, sticky="e", pady=5)
    target_lat_entry = tk.Entry(nav_content, font=modern_font, bg='#3c3c3c', fg=text_color, insertbackground=text_color, width=18)
    target_lat_entry.grid(row=1, column=1, padx=10, pady=5)

    tk.Label(nav_content, text="Speed (km/h):", font=label_font, bg=frame_bg_color, fg=text_color).grid(row=2, column=0, sticky="e", pady=5)
    speed_entry = tk.Entry(nav_content, font=modern_font, bg='#3c3c3c', fg=text_color, insertbackground=text_color, width=18)
    speed_entry.insert(0, "15") 
    speed_entry.grid(row=2, column=1, padx=10, pady=5)

    def calculate_eta(*args):
        try:
            start_lat = float(latitude_entry.get())
            start_lon = float(longitude_entry.get())
            end_lat = float(target_lat_entry.get())
            end_lon = float(target_lon_entry.get())
            speed_kmh = float(speed_entry.get())

            if speed_kmh > 0:
                dist_m = get_distance(start_lat, start_lon, end_lat, end_lon)
                dist_km = dist_m / 1000
                time_hours = dist_km / speed_kmh
                time_mins = time_hours * 60
                info_label.config(text=f"距離: {dist_km:.2f} km | 預估: {time_mins:.1f} 分鐘", fg=text_color, bg=frame_bg_color)
        except ValueError:
            pass

    longitude_entry.bind("<KeyRelease>", calculate_eta)
    latitude_entry.bind("<KeyRelease>", calculate_eta)
    target_lon_entry.bind("<KeyRelease>", calculate_eta)
    target_lat_entry.bind("<KeyRelease>", calculate_eta)
    speed_entry.bind("<KeyRelease>", calculate_eta)

    def start_custom_walk():
        global current_udid
        if not current_udid:
            messagebox.showerror("Error", "請先選擇設備！")
            return
        try:
            start_lat = float(latitude_entry.get())
            start_lon = float(longitude_entry.get())
            end_lat = float(target_lat_entry.get())
            end_lon = float(target_lon_entry.get())
            speed_kmh = float(speed_entry.get())

            if speed_kmh <= 0: return

            dist_m = get_distance(start_lat, start_lon, end_lat, end_lon)
            speed_ms = speed_kmh * (1000 / 3600) 
            total_time_s = dist_m / speed_ms
            
            # ✨ 導航模式間隔
            delay = 0.5 
            steps = max(1, int(total_time_s / delay))

            def walk_loop():
                start_walking_button.config(state="disabled")
                start_time = time.time()
                for i in range(steps + 1):
                    current_lat = start_lat + (end_lat - start_lat) * (i / steps)
                    current_lon = start_lon + (end_lon - start_lon) * (i / steps)
                    
                    update_location_bg(current_lat, current_lon)
                    
                    latitude_entry.delete(0, tk.END)
                    latitude_entry.insert(0, f"{current_lat:.6f}")
                    longitude_entry.delete(0, tk.END)
                    longitude_entry.insert(0, f"{current_lon:.6f}")
                    
                    live_lat_label.config(text=f"緯度 (Lat): {current_lat:.6f}", fg=radar_color, bg=main_bg_color)
                    live_lon_label.config(text=f"經度 (Lon): {current_lon:.6f}", fg=radar_color, bg=main_bg_color)
                    
                    dist_km = (dist_m / 1000)
                    elapsed_km = (get_distance(start_lat, start_lon, current_lat, current_lon) / 1000)
                    progress_percent = (elapsed_km / dist_km * 100) if dist_km > 0 else 100
                    
                    elapsed_seconds = int(time.time() - start_time)
                    status_text = f"導航中: {progress_percent:.1f}% | {elapsed_seconds//60:02d}:{elapsed_seconds%60:02d}"
                    info_label.config(text=status_text, fg=text_color, bg=frame_bg_color)
                    time.sleep(delay)
                    
                info_label.config(text="狀態: 已抵達終點！", fg=success_color, bg=frame_bg_color)
                start_walking_button.config(state="normal")

            threading.Thread(target=walk_loop, daemon=True).start()
        except ValueError:
            messagebox.showerror("Error", "輸入無效。")

    start_walking_button = tk.Button(nav_content, text="Start Walking (開始導航)", font=modern_font, bg=accent_color, fg=text_color, borderwidth=0, padx=10, pady=5, command=start_custom_walk)
    start_walking_button.grid(row=4, column=0, columnspan=2, pady=(15, 0), sticky="ew")

    info_label = tk.Label(nav_content, text="輸入目標計算時間", font=label_font, bg=frame_bg_color, fg=text_color)
    info_label.grid(row=3, column=0, columnspan=2, pady=5)


    joystick_container = tk.Frame(main_frame, bg=main_bg_color)
    joystick_container.pack(fill="x", pady=10)

    def toggle_joystick():
        if joystick_content.winfo_ismapped():
            joystick_content.pack_forget()
            joystick_toggle_btn.config(text="▶ 🎮 虛擬搖桿 (JoyStick)")
        else:
            joystick_content.pack(fill="x")
            joystick_toggle_btn.config(text="▼ 🎮 虛擬搖桿 (JoyStick)")

    joystick_toggle_btn = tk.Button(joystick_container, text="▼ 🎮 虛擬搖桿 (JoyStick)", font=header_font, bg=frame_bg_color, fg=text_color, activebackground=secondary_color, activeforeground=text_color, borderwidth=0, anchor="w", padx=10, pady=8, command=toggle_joystick)
    joystick_toggle_btn.pack(fill="x")

    joystick_content = tk.Frame(joystick_container, bg=frame_bg_color, padx=10, pady=10)
    joystick_content.pack(fill="x")

    canvas_size = 150
    center = canvas_size // 2
    max_radius = 50

    joystick_canvas = tk.Canvas(joystick_content, width=canvas_size, height=canvas_size, bg=frame_bg_color, highlightthickness=0)
    joystick_canvas.pack(anchor="center", pady=5)

    joystick_canvas.create_oval(center - max_radius, center - max_radius, center + max_radius, center + max_radius, fill=frame_bg_color, outline=secondary_color, width=2)
    stick = joystick_canvas.create_oval(center - 15, center - 15, center + 15, center + 15, fill=accent_color, outline=accent_color)

    def move_stick(event):
        global joystick_dx, joystick_dy, is_joystick_moving
        dx = event.x - center
        dy = event.y - center
        distance = math.hypot(dx, dy)

        if distance > max_radius:
            dx = dx * (max_radius / distance)
            dy = dy * (max_radius / distance)

        joystick_canvas.coords(stick, center + dx - 15, center + dy - 15, center + dx + 15, center + dy + 15)
        
        joystick_dx = dx
        joystick_dy = dy
        is_joystick_moving = True

    def release_stick(event):
        global joystick_dx, joystick_dy, is_joystick_moving
        joystick_canvas.coords(stick, center - 15, center - 15, center + 15, center + 15)
        joystick_dx = 0
        joystick_dy = 0
        is_joystick_moving = False

    joystick_canvas.bind("<B1-Motion>", move_stick)
    joystick_canvas.bind("<ButtonRelease-1>", release_stick)

    def joystick_engine():
        global joystick_dx, joystick_dy, is_joystick_moving, current_udid
        max_speed_kmh = 15.0  

        while True:
            if is_joystick_moving and (joystick_dx != 0 or joystick_dy != 0) and current_udid:
                try:
                    # ✨ 搖桿模式：直接寫死 0.1s 電競級反應
                    delay = 0.1 

                    current_lat = float(latitude_entry.get())
                    current_lon = float(longitude_entry.get())

                    push_ratio = math.hypot(joystick_dx, joystick_dy) / max_radius
                    current_speed = max_speed_kmh * push_ratio
                    dist_km = current_speed * (delay / 3600)

                    angle = math.atan2(-joystick_dy, joystick_dx)
                    dist_x = dist_km * math.cos(angle)
                    dist_y = dist_km * math.sin(angle)

                    delta_lat = dist_y / 111.111
                    delta_lon = dist_x / (111.111 * math.cos(math.radians(current_lat)))

                    new_lat = current_lat + delta_lat
                    new_lon = current_lon + delta_lon

                    latitude_entry.delete(0, tk.END)
                    latitude_entry.insert(0, f"{new_lat:.6f}")
                    longitude_entry.delete(0, tk.END)
                    longitude_entry.insert(0, f"{new_lon:.6f}")

                    live_lat_label.config(text=f"緯度 (Lat): {new_lat:.6f}", fg=radar_color, bg=main_bg_color)
                    live_lon_label.config(text=f"經度 (Lon): {new_lon:.6f}", fg=radar_color, bg=main_bg_color)

                    update_location_bg(new_lat, new_lon)

                except Exception as e:
                    logging.error(f"🚨 Joystick Engine Crash: {e}") 
                time.sleep(delay)
            else:
                time.sleep(0.1)

    threading.Thread(target=joystick_engine, daemon=True).start()

    exit_button = tk.Button(main_frame, text="Exit (安全離開模擬器)", font=modern_font, bg=warning_color, fg=text_color, borderwidth=0, padx=10, pady=10, command=safe_exit)
    exit_button.pack(side="top", fill="x", pady=10)

    root.mainloop()

if __name__ == "__main__":
    main()