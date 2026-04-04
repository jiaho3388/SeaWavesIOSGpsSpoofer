# 🌍 Rei's iOS Location Simulator Pro 

![Python Version](https://img.shields.io/badge/Python-3.8%2B-blue)
![iOS Support](https://img.shields.io/badge/iOS-16%20%7C%2017%20%7C%2026%2B-success)
![Engine](https://img.shields.io/badge/Engine-Pure%20Python%20Async-orange)

專為 Hardcore 玩家與開發者打造的 **iOS 終極地理位置模擬器**。
徹底拋棄傳統 `subprocess` 呼叫的延遲，採用 **純 Python 異步 (Async) 引擎** 直接綁定 Apple 底層 DVT 服務，並完美穿透 iOS 17/26+ 的 RSD (Remote Service Discovery) 隧道限制，達成 **0.1 秒極低延遲** 的電競級操作體驗。

完美適用於 LBS AR 遊戲（如 Pikmin Bloom 等）的精準步數與軌跡控制。

---

## ✨ 核心特點 (Features)

* ⚡ **0.1 秒極致無延遲**：直接對話 `DvtProvider` 與 `LocationSimulation`，告別舊版 3 秒指令延遲。
* 🛡️ **全版本 iOS 防彈支援**：向下相容 iOS 16，向上穿透 iOS 17 甚至最新的 iOS 26+ RSD 網路架構。
* 🖥️ **Pro Dashboard 2.0**：現代化暗色系 (Dark Mode) 雙欄卡片 UI，優化「載入檔案 -> 單點降落」的極速動線。
* 🎮 **電競級虛擬搖桿 (Virtual Joystick)**：即時推算向量角度，提供極度滑順的無縫移動。
* 🚶‍♂️ **自動巡航系統 (Auto-Navigation)**：自訂目標座標與時速 (km/h)，自動計算 ETA 並即時更新軌跡。

---

## 🛠️ 環境建置 (Installation)

在 Windows 環境下編譯 Apple 底層的 `lzfse` 壓縮演算法需要 C++ 編譯器支援，請確保你已安裝 **[Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)**。

建立並啟動虛擬環境 (Virtual Environment)：

    python -m venv .venv
    .\.venv\Scripts\activate

升級基礎編譯套件並安裝核心依賴庫：

    python -m pip install --upgrade pip setuptools wheel
    pip install pymobiledevice3

---

## 🚀 啟動指南 (Usage)

1. 將你的 iPhone 透過 USB 連接至電腦，並信任此電腦。
2. 啟動虛擬環境後，直接執行主程式：

    python main.py

3. 程式會自動在背景啟動 `tunneld` 守護行程，並自動掃描連接的設備。
4. 在左側選單鎖定你的 iPhone 後，即可開始操作！

---

## 📌 版本歷程
詳細的架構重構與踩坑紀錄請見 [CHANGELOG.md](CHANGELOG.md)。