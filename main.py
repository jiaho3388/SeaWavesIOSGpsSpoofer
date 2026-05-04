import socket
import subprocess
import sys
import logging
import time
import json
import re
import threading
import math
import os
import urllib.request
import tkinter as tk
from tkinter import messagebox, font, ttk, filedialog
# --- 請加在原本的 import 下方 ---
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
import uvicorn
import asyncio
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO)

# ==============================================================================
# ========================= [Web 全息雷達通訊塔] ===============================
# ==============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def get_dashboard():
    # 讀取前端網頁
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())
    
@app.get("/api/pois")
async def get_pois():
    """讀取靜態戰略物資點 (Wayfarer POIs) 並派發給前端雷達"""
    if os.path.exists("pois.json"):
        with open("pois.json", "r", encoding="utf-8") as f:
            return json.loads(f.read())
    return {"pois": []}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logging.info("🌐 前端全息地圖已連線！")
    
    async def send_radar():
        global force_map_center # <--- 宣告 global
        while True:
            try:
                # --- [新增這一段] 處理鏡頭跳躍請求 ---
                if force_map_center:
                    await websocket.send_text(json.dumps({
                        "type": "map_center", 
                        "lat": force_map_center["lat"], 
                        "lon": force_map_center["lon"]
                    }))
                    force_map_center = None # 發送完就清除信號
                # ------------------------------------
                
                # 將原版的 device_coords (lat, lon) 轉換給網頁
                fleet_data = {}
                for udid, coords in device_coords.items():
                    name = next((d['name'] for d in connected_devices if d['udid'] == udid), "Unknown Ship")
                    fleet_data[name] = {"lat": coords[0], "lon": coords[1]}
                
                await websocket.send_text(json.dumps({"type": "radar_update", "fleet": fleet_data}))
                await asyncio.sleep(0.3)
            except Exception: break

    async def receive_commands():
        while True:
            try:
                cmd = json.loads(await websocket.receive_text())
                if cmd.get("action") == "teleport":
                    target_lat, target_lon = float(cmd["lat"]), float(cmd["lon"])
                    # 呼叫你原本寫好的 set_device_location 函數！
                    for u in connected_devices:
                        udid = u["udid"]
                        set_device_location(udid, target_lat, target_lon)
                        device_coords[udid] = (target_lat, target_lon)
            except Exception: break

    await asyncio.gather(asyncio.create_task(send_radar()), asyncio.create_task(receive_commands()))

def run_fastapi():
    # 背景啟動伺服器，不阻擋 Tkinter
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    server.run()
# ==============================================================================
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

connection_status_label = None
tunnel_status_label = None 
engine_status_label = None 
device_dropdown = None 

joystick_dx = 0
joystick_dy = 0
is_joystick_moving = False

# 自動導航狀態鎖
is_routing = False

# [升級] 多機同步變數、引擎池與獨立座標記憶體
sync_var = None
engines = {}       # 格式: { "UDID": ContinuousLocationEngine_Instance }
device_coords = {} # 格式: { "UDID": (lat, lon) }
force_map_center = None  # 用來觸發地圖視角跳躍的信號

# 動態雷達 UI 儲存庫
radar_labels = {}  # 格式: { "UDID": {"frame": tk.Frame, "name": tk.Label, "coords": tk.Label} }
radar_container = None

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
                # --- 在它下面補上這三行，賦予台中初始座標 ---
                for d in connected_devices:
                    if d["udid"] not in device_coords:
                        device_coords[d["udid"]] = (24.145161, 120.670531)
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
            file.write(f"{latitude_entry.get()},{longitude_entry.get()}")
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
    global longitude_entry, latitude_entry
    filepath = filedialog.askopenfilename(title="選擇座標檔案", filetypes=(("Text Files", "*.txt"), ("All Files", "*.*")))
    if not filepath: return
    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            lat, lon = parse_smart_coordinates(file.read())
            if lat is not None and lon is not None:
                latitude_entry.delete(0, tk.END); latitude_entry.insert(0, f"{lat:.6f}")
                longitude_entry.delete(0, tk.END); longitude_entry.insert(0, f"{lon:.6f}")
                messagebox.showinfo("Success", "座標載入成功！(待命降落)")
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

# [核心更新] 將目標座標派發給指定 UDID 的專屬引擎
def set_device_location(udid, lat, lon):
    global engines
    if udid not in engines or not engines[udid].is_alive():
        if udid in engines: engines[udid].stop()
        ios_major_version = get_safe_ios_version(udid)
        engines[udid] = ContinuousLocationEngine(udid, ios_major_version)
        engines[udid].start()
    engines[udid].update_target(lat, lon)

def safe_exit():
    global tunnel_process, engines, is_routing
    is_routing = False
    
    for e in engines.values():
        e.stop()
        
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
    global longitude_entry, latitude_entry, current_udid, is_routing, sync_var, device_coords
    
    if not current_udid and not (sync_var and sync_var.get()): 
        return messagebox.showerror("Error", "請先選擇設備或開啟多機連動！")
        
    try:
        is_routing = False 
        longitude, latitude = float(longitude_entry.get()), float(latitude_entry.get())
        if not validate_coordinates(longitude, latitude): return messagebox.showerror("Error", "座標範圍錯誤")
        
        if current_udid and get_safe_ios_version(current_udid) < 17 and not mount_developer_disk_image():
            return messagebox.showerror("Error", "掛載 Developer Disk Image 失敗。")
            
        target_udids = [d['udid'] for d in connected_devices] if sync_var.get() else ([current_udid] if current_udid else [])
        
        for u in target_udids:
            set_device_location(u, latitude, longitude)
            device_coords[u] = (latitude, longitude) # 更新該設備的獨立記憶體
            
        global force_map_center
        force_map_center = {"lat": latitude, "lon": longitude}
        
    except ValueError: messagebox.showerror("Error", "請輸入有效數字。")

# ==============================================================================
# ========================= [v2.4.1 Fleet Command UI] ==========================
# ==============================================================================
def create_card(parent, title, bg_color, fg_color, font):
    card = tk.Frame(parent, bg=bg_color, padx=15, pady=15)
    tk.Label(card, text=title, font=font, bg=bg_color, fg=fg_color, anchor="w").pack(fill="x", pady=(0, 10))
    return card

def main():
    app_bg = '#121212'; card_bg = '#1e1e1e'; input_bg = '#2d2d30'; accent = '#0a84ff'; success = '#32d74b'; warning = '#ff453a'; text_main = '#ffffff'; text_muted = '#8e8e93'   

    global longitude_entry, latitude_entry, target_lon_entry, target_lat_entry, speed_entry
    global info_label, connection_status_label, tunnel_status_label, engine_status_label, device_dropdown
    global joystick_dx, joystick_dy, is_joystick_moving
    global sync_var, radar_container, radar_labels

    start_tunneld_engine()
    threading.Thread(target=monitor_device_connection, daemon=True).start()

    threading.Thread(target=run_fastapi, daemon=True).start()

    root = tk.Tk()
    root.title("Rei's iOS Location Simulator Pro v2.4.1 (Command Center)")
    root.protocol("WM_DELETE_WINDOW", safe_exit)
    root.configure(bg=app_bg)
    
    ui_font = "Microsoft JhengHei UI"
    f_title = font.Font(family=ui_font, size=16, weight="bold")
    f_card_title = font.Font(family=ui_font, size=12, weight="bold")
    f_main = font.Font(family=ui_font, size=11)
    f_small = font.Font(family=ui_font, size=10)
    f_radar_small = font.Font(family="Consolas", size=14, weight="bold")

    window_width, window_height = 850, 850
    center_y = max(0, int((root.winfo_screenheight() / 2) - (window_height / 2) - 50))
    root.geometry(f"{window_width}x{window_height}+100+{center_y}")

    style = ttk.Style()
    style.theme_use('clam')
    style.configure('TCombobox', fieldbackground=input_bg, background=card_bg, foreground=text_main, borderwidth=0)
    style.map('TCombobox', fieldbackground=[('readonly', input_bg)], selectbackground=[('readonly', accent)])

    header_frame = tk.Frame(root, bg=app_bg, pady=10)
    header_frame.pack(fill="x", padx=20)
    tk.Label(header_frame, text="Rei's iOS Location Simulator", font=f_title, bg=app_bg, fg=text_main).pack(side="left")
    tk.Label(header_frame, text="Command Center Edition", font=f_small, bg=app_bg, fg='#ff4fc1').pack(side="left", padx=10)

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

    sync_var = tk.BooleanVar(value=False)
    sync_cb = tk.Checkbutton(status_card, text="🚀 Fleet Sync (多機同步連動)", variable=sync_var, font=f_main, bg=card_bg, fg='#ff4fc1', selectcolor=input_bg, activebackground=card_bg, activeforeground='#ff4fc1')
    sync_cb.pack(fill="x", pady=(10, 0), anchor="w")

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
            total = len(connected_devices)
            connection_status_label.config(text=f"🎯 連線: {dev['name'] if dev else 'Unknown'} (共偵測 {total} 台)", fg=success)
        else: connection_status_label.config(text="❌ 未鎖定任何設備", fg=warning)
        
        if sync_var.get():
            engine_status_label.config(text=f"⚙️ 引擎: 艦隊模式啟動 ({len(connected_devices)} 台連動)", fg='#ff4fc1')
        else:
            engine_status_label.config(text="⚙️ 引擎: Pure Python (單機極速)", fg='#4fc1ff')
            
        tunnel_status_label.config(text="🌐 Tunnel: 運作中", fg=success) if tunnel_active else tunnel_status_label.config(text="🌐 Tunnel: 已停止", fg=warning)
        root.after(1000, update_status_labels)
    update_status_labels()

    # [UI 升級] 動態生成與管理的多機雷達陣列
    radar_card = create_card(left_col, "FLEET RADAR (實時設備座標)", card_bg, text_muted, f_small); radar_card.pack(fill="x", pady=10)
    radar_container = tk.Frame(radar_card, bg=card_bg)
    radar_container.pack(fill="x")

    def refresh_radar_ui():
        global radar_labels, connected_devices, device_coords, current_udid, sync_var
        
        if not connected_devices:
            for widget in radar_container.winfo_children(): widget.destroy()
            radar_labels.clear()
            tk.Label(radar_container, text="No devices connected...", font=f_small, bg=card_bg, fg=text_muted).pack(pady=10)
        else:
            # 清除 "No devices" 標籤
            for widget in radar_container.winfo_children():
                if isinstance(widget, tk.Label) and widget.cget("text") == "No devices connected...": widget.destroy()

            # 新增未顯示的設備 UI
            for dev in connected_devices:
                udid = dev['udid']
                if udid not in radar_labels:
                    f = tk.Frame(radar_container, bg=input_bg, pady=5, padx=10)
                    f.pack(fill="x", pady=3)
                    lbl_name = tk.Label(f, text=dev['name'], font=f_small, bg=input_bg, fg=text_main, anchor="w")
                    lbl_name.pack(fill="x")
                    lbl_coords = tk.Label(f, text="LAT: --.------   LON: --.------", font=f_radar_small, bg=input_bg, fg=accent, anchor="w")
                    lbl_coords.pack(fill="x")
                    radar_labels[udid] = {'frame': f, 'name': lbl_name, 'coords': lbl_coords}
            
            # 移除已斷線的設備 UI
            active_udids = [d['udid'] for d in connected_devices]
            for udid in list(radar_labels.keys()):
                if udid not in active_udids:
                    radar_labels[udid]['frame'].destroy()
                    del radar_labels[udid]

            # 更新文字與座標
            for dev in connected_devices:
                udid = dev['udid']
                coords = device_coords.get(udid, None)
                lat_str = f"{coords[0]:.6f}" if coords else "--.------"
                lon_str = f"{coords[1]:.6f}" if coords else "--.------"
                
                # 顏色邏輯：如果是艦隊同步模式用粉紫色，否則主控設備用藍色，其他設備用白色
                if sync_var.get(): color = '#ff4fc1'
                elif udid == current_udid: color = accent
                else: color = text_main
                
                radar_labels[udid]['name'].config(text=dev['name'], fg=color)
                radar_labels[udid]['coords'].config(text=f"LAT: {lat_str}   LON: {lon_str}")
                
        root.after(300, refresh_radar_ui) # 每 0.3 秒刷新一次 UI
    refresh_radar_ui()

    # [卡片] 自動導航 
    nav_container = tk.Frame(left_col, bg=card_bg); nav_container.pack(fill="x", pady=(0, 10))
    def toggle_nav():
        if nav_content.winfo_ismapped(): nav_content.pack_forget(); nav_toggle_btn.config(text="▶  NAVIGATION (自動導航)")
        else: nav_content.pack(fill="x", padx=15, pady=(0, 15)); nav_toggle_btn.config(text="▼  NAVIGATION (自動導航)")
    nav_toggle_btn = tk.Button(nav_container, text="▶  NAVIGATION (自動導航)", font=f_card_title, bg=card_bg, fg=accent, borderwidth=0, anchor="w", padx=15, pady=15, command=toggle_nav); nav_toggle_btn.pack(fill="x")
    nav_content = tk.Frame(nav_container, bg=card_bg)

    def calculate_eta(*args):
        try:
            global current_udid, device_coords
            # ETA 以當前選定的主控設備座標來預估
            slat, slon = device_coords.get(current_udid, (float(latitude_entry.get()), float(longitude_entry.get())))
            dist = get_distance(slat, slon, float(target_lat_entry.get()), float(target_lon_entry.get())) / 1000
            if info_label.winfo_exists():
                info_label.config(text=f"距離: {dist:.2f} km | 預估: {(dist/float(speed_entry.get())*60 if float(speed_entry.get())>0 else 0):.1f} 分鐘", fg=text_main)
        except ValueError: pass

    def sync_teleport_coords():
        target_lat_entry.delete(0, tk.END)
        target_lat_entry.insert(0, latitude_entry.get())
        target_lon_entry.delete(0, tk.END)
        target_lon_entry.insert(0, longitude_entry.get())
        calculate_eta()

    sync_btn = tk.Button(nav_content, text="🔽 載入 TELEPORT (降落點) 座標", font=f_small, bg=input_bg, fg=accent, borderwidth=0, pady=3, command=sync_teleport_coords)
    sync_btn.pack(fill="x", pady=(0, 8))

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

    def stop_custom_walk():
        global is_routing
        if is_routing:
            is_routing = False

    def start_custom_walk():
        global is_routing, sync_var, current_udid, device_coords
        if not current_udid and not (sync_var and sync_var.get()): 
            return messagebox.showerror("Error", "請先選擇設備或開啟多機連動！")
        if is_routing: return messagebox.showinfo("Info", "導航已經在執行中！")
        try:
            target_udids = [d['udid'] for d in connected_devices] if sync_var.get() else ([current_udid] if current_udid else [])
            
            # 記錄每台設備的起點座標
            start_coords = {}
            for u in target_udids:
                start_coords[u] = device_coords.get(u, (float(latitude_entry.get()), float(longitude_entry.get())))
            
            elat, elon = float(target_lat_entry.get()), float(target_lon_entry.get())
            speed = float(speed_entry.get())
            if speed <= 0: return
            
            # 總時間依照主控設備的距離來計算
            ref_lat, ref_lon = start_coords.get(current_udid, list(start_coords.values())[0])
            dist_m = get_distance(ref_lat, ref_lon, elat, elon)
            total_duration = dist_m / (speed * (1000 / 3600)) 
            
            if total_duration <= 0: return
            is_routing = True 
            
            def walk_loop():
                global is_routing, device_coords
                start_btn.config(state="disabled", bg=input_bg)
                start_time = time.time()
                
                while is_routing:
                    elapsed = time.time() - start_time
                    if elapsed >= total_duration: break 
                    progress = elapsed / total_duration
                    
                    # 計算每台設備當前的進度，並派發引擎
                    for u in target_udids:
                        slat, slon = start_coords[u]
                        clat = slat + (elat - slat) * progress
                        clon = slon + (elon - slon) * progress
                        device_coords[u] = (clat, clon)
                        set_device_location(u, clat, clon)
                    
                    def update_ui(e, tot):
                        if info_label.winfo_exists():
                            info_label.config(text=f"導航中: {((e/tot)*100):.1f}% | {int(e)//60:02d}:{int(e)%60:02d}")
                    
                    info_label.after(0, update_ui, elapsed, total_duration)
                    time.sleep(0.5) 
                    
                if is_routing: 
                    for u in target_udids:
                        device_coords[u] = (elat, elon)
                        set_device_location(u, elat, elon)
                    def finish_ui():
                        if info_label.winfo_exists():
                            info_label.config(text="艦隊已全數抵達終點！", fg=success)
                            start_btn.config(state="normal", bg=accent)
                    info_label.after(0, finish_ui)
                else: 
                    def abort_ui():
                        if info_label.winfo_exists():
                            info_label.config(text="導航已強制中止！", fg=warning)
                            start_btn.config(state="normal", bg=accent)
                    info_label.after(0, abort_ui)
                
                is_routing = False 

            threading.Thread(target=walk_loop, daemon=True).start()
        except ValueError: messagebox.showerror("Error", "輸入無效。")
        
    route_btn_frame = tk.Frame(nav_content, bg=card_bg)
    route_btn_frame.pack(fill="x", pady=(5, 0))
    
    start_btn = tk.Button(route_btn_frame, text="START ROUTE", font=f_main, bg=accent, fg=text_main, borderwidth=0, pady=5, command=start_custom_walk)
    start_btn.pack(side="left", fill="x", expand=True, padx=(0, 2))
    
    stop_btn = tk.Button(route_btn_frame, text="END ROUTE", font=f_main, bg=warning, fg=text_main, borderwidth=0, pady=5, command=stop_custom_walk)
    stop_btn.pack(side="left", fill="x", expand=True, padx=(2, 0))

    tk.Button(left_col, text="EXIT SYSTEM", font=f_card_title, bg=warning, fg=text_main, borderwidth=0, pady=10, command=safe_exit).pack(side="bottom", fill="x")

    # --- 右欄 (Right Column) : 操作 ---
    right_col = tk.Frame(main_container, bg=app_bg)
    right_col.pack(side="right", fill="both", expand=True, padx=(10, 0))

    # [卡片] 資料管理 
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

    # [卡片] 虛擬搖桿
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
        global joystick_dx, joystick_dy, is_joystick_moving, current_udid, sync_var, device_coords
        while True:
            has_target = current_udid or (sync_var and sync_var.get())
            if is_joystick_moving and (joystick_dx != 0 or joystick_dy != 0) and has_target:
                try:
                    delay = 0.1
                    target_udids = [d['udid'] for d in connected_devices] if sync_var.get() else ([current_udid] if current_udid else [])
                    
                    for u in target_udids:
                        clat, clon = device_coords.get(u, (float(latitude_entry.get()), float(longitude_entry.get())))
                        dist = (15.0 * (math.hypot(joystick_dx, joystick_dy) / max_radius)) * (delay / 3600)
                        ang = math.atan2(-joystick_dy, joystick_dx)
                        nlat = clat + ((dist * math.sin(ang)) / 111.111)
                        nlon = clon + ((dist * math.cos(ang)) / (111.111 * math.cos(math.radians(clat))))
                        
                        device_coords[u] = (nlat, nlon)
                        set_device_location(u, nlat, nlon)
                except Exception: pass
                time.sleep(delay)
            else: time.sleep(0.1)
    threading.Thread(target=joystick_engine, daemon=True).start()

    for e in [longitude_entry, latitude_entry, target_lon_entry, target_lat_entry, speed_entry]:
        e.bind("<KeyRelease>", calculate_eta)

    root.mainloop()

if __name__ == "__main__":
    main()