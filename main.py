import socket
import subprocess
import sys
import logging
import time
import json
import re
import threading
import math
import tkinter as tk
from tkinter import messagebox, font, ttk, filedialog

logging.basicConfig(level=logging.INFO)

# ==============================================================================
# ========================= [全域變數宣告] =================================
# ==============================================================================
device_connected = False
current_location_process = None

# ✨ Tunneld 專用全域變數
tunnel_process = None
tunnel_active = False

# ✨ 多設備切換專用變數
connected_devices = [] 
current_udid = None    

# UI 相關全域變數
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
device_dropdown = None 

# JoyStick 專用全域變數
joystick_dx = 0
joystick_dy = 0
is_joystick_moving = False

# ==============================================================================
# ========================= [核心功能與引擎] ===============================
# ==============================================================================

def start_tunneld_engine():
    global tunnel_process, tunnel_active
    if tunnel_process is not None:
        return

    creationflags = 0
    if sys.platform == "win32":
        creationflags = 0x08000000 # CREATE_NO_WINDOW

        try:
            logging.info("🧹 Cleaning up existing zombie tunneld processes...")
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
        logging.info("🌐 Tunneld background engine started successfully.")
    except Exception as e:
        logging.error(f"🚨 Failed to start tunneld: {e}")
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
                logging.warning("Tunneld process terminated unexpectedly.")

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

def update_location_bg(latitude, longitude):
    global current_location_process, current_udid
    
    if not current_udid:
        logging.warning("尚未選擇任何設備，無法發送座標。")
        return

    # 🧹 [暴力且安全的清理法]：不再使用 PIPE 通道，直接終止舊進程
    if current_location_process is not None:
        try:
            current_location_process.terminate() # 優雅請求終止
            current_location_process.wait(timeout=0.5)
        except:
            try:
                current_location_process.kill()  # 不聽話就直接拔管
            except:
                pass

    command = [
        "pymobiledevice3", "developer", "dvt", "simulate-location", "set",
        "--udid", current_udid, 
        "--", str(latitude), str(longitude)
    ]
    
    try:
        creationflags = 0x08000000 if sys.platform == "win32" else 0
        current_location_process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,  # 👈 核心修復：不開通道，徹底根除 Errno 22
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags
        )
    except Exception as e:
        logging.error(f"🚨 發送定位進程啟動失敗: {e}")

# ==============================================================================

def safe_exit():
    global current_location_process, tunnel_process
    logging.info("Initiating safe exit sequence...")
    
    # 關閉定位發射器
    if current_location_process is not None:
        try:
            current_location_process.terminate()
        except:
            pass
            
    # 關閉 Tunneld 引擎
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
    global longitude_entry, latitude_entry, live_lat_label, live_lon_label
    global current_udid, connected_devices
    
    if not current_udid:
        messagebox.showerror("Error", "請先從上方選單選擇一台目標手機！")
        return

    try:
        longitude = float(longitude_entry.get())
        latitude = float(latitude_entry.get())

        if not validate_coordinates(longitude, latitude):
            messagebox.showerror("Error", "Invalid longitude or latitude range.")
            return

        ios_version = "16.0"
        for d in connected_devices:
            if d["udid"] == current_udid:
                ios_version = d["version"]
                break

        ios_major_version = int(ios_version.split('.')[0])
        if ios_major_version < 17:
            if not mount_developer_disk_image():
                messagebox.showerror("Error", "Failed to mount the Developer Disk Image.")
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
    global connection_status_label, tunnel_status_label, device_dropdown
    global joystick_dx, joystick_dy, is_joystick_moving

    start_tunneld_engine()
    threading.Thread(target=monitor_device_connection, daemon=True).start()

    root = tk.Tk()
    root.title("Rei's iOS Location Simulator Pro")
    root.protocol("WM_DELETE_WINDOW", safe_exit)
    
    ui_font_family = "Microsoft JhengHei UI"
    title_font = font.Font(family=ui_font_family, size=16, weight="bold")
    header_font = font.Font(family=ui_font_family, size=12, weight="bold")
    modern_font = font.Font(family=ui_font_family, size=11)
    label_font = font.Font(family=ui_font_family, size=10)
    radar_font = font.Font(family=ui_font_family, size=14, weight="bold")

    root.configure(bg=main_bg_color)
    
    # ✨ 套用你專屬的視窗大小與位置 (X=50, 靠左顯示)
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

    # ==================== [UI 元件建立] ====================
    tk.Label(main_frame, text="Rei's iOS Location Simulator", font=title_font, bg=main_bg_color, fg=accent_color).pack(pady=(0, 15))

    # [區塊 1：雙引擎狀態與設備選擇]
    status_container = tk.Frame(main_frame, bg=main_bg_color)
    status_container.pack(pady=5)
    
    # 這裡的文字會透過後面的 update 函數動態顯示「鎖定目標」
    connection_status_label = tk.Label(status_container, text="🔍 尋找設備中...", font=label_font, bg=main_bg_color, fg=warning_color)
    connection_status_label.grid(row=0, column=0, padx=10)
    
    tunnel_status_label = tk.Label(status_container, text="🌐 Tunnel: 啟動中...", font=label_font, bg=main_bg_color, fg=text_color)
    tunnel_status_label.grid(row=0, column=1, padx=10)

    tk.Label(status_container, text="選擇目標設備:", font=label_font, bg=main_bg_color, fg=text_color).grid(row=1, column=0, pady=(10,0), sticky="e")
    device_var = tk.StringVar()
    device_dropdown = ttk.Combobox(status_container, textvariable=device_var, state="readonly", font=label_font, width=22)
    device_dropdown.grid(row=1, column=1, pady=(10,0), sticky="w")

    # ✨ [嚴謹化]：切換設備時的明確回饋機制
    def on_device_selected(event):
        global current_udid
        idx = device_dropdown.current()
        if idx >= 0 and idx < len(connected_devices):
            current_udid = connected_devices[idx]["udid"]
            dev_name = connected_devices[idx]["name"]
            logging.info(f"Target switched to UDID: {current_udid}")
            # 彈出視窗給予最強烈的「切換成功」確認感
            messagebox.showinfo("設備切換成功", f"定位發射引擎已重新鎖定目標：\n\n🎯 {dev_name}")
            
    device_dropdown.bind("<<ComboboxSelected>>", on_device_selected)

    def update_status_labels():
        global device_connected, tunnel_active, connected_devices, current_udid
        
        # 1. 動態更新下拉選單
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

        # 2. ✨ [嚴謹化]：讓指示燈精準反映「當前鎖定的目標是誰」
        if device_connected and current_udid:
            # 找出當前 UDID 對應的名稱
            current_target_name = "未知設備"
            for d in connected_devices:
                if d["udid"] == current_udid:
                    current_target_name = d["name"]
                    break
            connection_status_label.config(text=f"🎯 目標: {current_target_name}", fg=success_color)
        else:
            connection_status_label.config(text="❌ 尚未鎖定任何設備", fg=warning_color)
            
        # 3. 更新 Tunnel 狀態
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

    save_as_button = tk.Button(data_ops_frame, text="Save As (儲存座標)", font=modern_font, bg=secondary_color, fg=text_color, borderwidth=0, padx=10, pady=5, command=save_as)
    save_as_button.pack(side="left", expand=True, padx=(0, 5))

    load_button = tk.Button(data_ops_frame, text="Load (讀取座標)", font=modern_font, bg=secondary_color, fg=text_color, borderwidth=0, padx=10, pady=5, command=load)
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

    # ==================== [區塊 4：🚶‍♂️ 折疊式 自動導航] ====================
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

    tk.Label(nav_content, text="Target Longitude (目標經度):", font=label_font, bg=frame_bg_color, fg=text_color).grid(row=0, column=0, sticky="e", pady=5)
    target_lon_entry = tk.Entry(nav_content, font=modern_font, bg='#3c3c3c', fg=text_color, insertbackground=text_color, width=18)
    target_lon_entry.grid(row=0, column=1, padx=10, pady=5)

    tk.Label(nav_content, text="Target Latitude (目標緯度):", font=label_font, bg=frame_bg_color, fg=text_color).grid(row=1, column=0, sticky="e", pady=5)
    target_lat_entry = tk.Entry(nav_content, font=modern_font, bg='#3c3c3c', fg=text_color, insertbackground=text_color, width=18)
    target_lat_entry.grid(row=1, column=1, padx=10, pady=5)

    tk.Label(nav_content, text="Speed (時速 km/h):", font=label_font, bg=frame_bg_color, fg=text_color).grid(row=2, column=0, sticky="e", pady=5)
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
                info_label.config(text=f"距離: {dist_km:.2f} km | 預估時間: {time_mins:.1f} 分鐘", fg=text_color, bg=frame_bg_color)
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
            messagebox.showerror("Error", "請先選擇一台設備！")
            return
            
        try:
            start_lat = float(latitude_entry.get())
            start_lon = float(longitude_entry.get())
            end_lat = float(target_lat_entry.get())
            end_lon = float(target_lon_entry.get())
            speed_kmh = float(speed_entry.get())

            if speed_kmh <= 0:
                messagebox.showwarning("Warning", "Speed must be greater than 0.")
                return

            dist_m = get_distance(start_lat, start_lon, end_lat, end_lon)
            speed_ms = speed_kmh * (1000 / 3600) 
            total_time_s = dist_m / speed_ms
            delay = 3 
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
                    status_text = f"導航中... 進度: {progress_percent:.1f}% | 經過時間: {elapsed_seconds//60:02d}:{elapsed_seconds%60:02d}"
                    info_label.config(text=status_text, fg=text_color, bg=frame_bg_color)
                    
                    time.sleep(delay)
                    
                info_label.config(text="狀態: 已抵達終點！", fg=success_color, bg=frame_bg_color)
                start_walking_button.config(state="normal")

            threading.Thread(target=walk_loop, daemon=True).start()

        except ValueError:
            messagebox.showerror("Error", "Please enter valid numbers.")

    start_walking_button = tk.Button(nav_content, text="Start Walking (開始導航)", font=modern_font, bg=accent_color, fg=text_color, borderwidth=0, padx=10, pady=5, command=start_custom_walk)
    start_walking_button.grid(row=4, column=0, columnspan=2, pady=(15, 0), sticky="ew")

    info_label = tk.Label(nav_content, text="請輸入目標與速度以計算預估時間", font=label_font, bg=frame_bg_color, fg=text_color)
    info_label.grid(row=3, column=0, columnspan=2, pady=5)


    # ==================== [區塊 5：🎮 折疊式 虛擬搖桿] ====================
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
        delay = 3             
        max_speed_kmh = 15.0  

        while True:
            if is_joystick_moving and (joystick_dx != 0 or joystick_dy != 0) and current_udid:
                try:
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

    # [最後區塊：系統操作]
    exit_button = tk.Button(main_frame, text="Exit (安全離開模擬器)", font=modern_font, bg=warning_color, fg=text_color, borderwidth=0, padx=10, pady=10, command=safe_exit)
    exit_button.pack(side="top", fill="x", pady=10)

    root.mainloop()

if __name__ == "__main__":
    main()