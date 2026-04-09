# 🌍 Rei's iOS Location Simulator Pro (Command Center Edition)

![Python Version](https://img.shields.io/badge/Python-3.8%2B-blue)
![iOS Support](https://img.shields.io/badge/iOS-16%20%7C%2017%20%7C%2026%2B-success)
![Engine](https://img.shields.io/badge/Engine-Pure%20Python%20Async-orange)

專為 Hardcore 玩家與開發者打造的 **iOS 終極地理位置模擬器** 與 **雙棲艦隊戰情室 (Fleet Command)**。

徹底拋棄傳統 subprocess 呼叫的延遲，採用 **純 Python 異步 (Async) 引擎** 直接綁定 Apple 底層 DVT 服務，並完美穿透 iOS 17/18 甚至最新的 iOS 26+ RSD (Remote Service Discovery) 隧道限制，達成 **0.1 秒極低延遲** 的電競級操作體驗。

無論是 LBS AR 遊戲（如 Pikmin Bloom、MHN 等）的單兵極速空投，還是多設備的同步連動測試，Rei's Simulator 都能提供最頂級的火力支援。

---

## ✨ 核心特點 (Features)

* ⚡ **0.1 秒極致無延遲**：直接對話 `DvtProvider` 與 `LocationSimulation`，告別舊版 3 秒指令延遲。
* 🛡️ **全版本 iOS 防彈支援**：向下相容 iOS 16，向上穿透 iOS 17/18 甚至最新的 iOS 26+ RSD 網路架構。
* 🖥️ **Command Center 戰情室 UI**：現代化暗色系 (Dark Mode) 雙欄卡片佈局，優化「載入檔案 -> 單點降落」的極速動線。
* 📡 **動態即時雷達 (FLEET RADAR)**：UI 座標與底層引擎徹底脫鉤，自動生成多設備專屬雷達面板，實時監控每一寸移動。
* 🚀 **Fleet Sync 多機連動**：支援 Engine Pool (引擎池) 架構，一鍵廣播降落、導航、搖桿訊號至所有連線設備。
* 🎯 **艦隊收束系統 (Fleet Convergence)**：即使設備起點散落各地，自動巡航也能基於絕對時間軸運算，確保所有設備「同時、精準」抵達指定終點。
* 🎮 **電競級虛擬搖桿 (Virtual Joystick)**：即時推算向量角度，提供極度滑順的無縫微操移動。

---

## 🛠️ 環境建置 (Installation)

在 Windows 環境下編譯 Apple 底層的 lzfse 壓縮演算法需要 C++ 編譯器支援，請確保你已安裝 **[Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)**。

**[Step 1]** 建立並啟動虛擬環境 (Virtual Environment)：

> **python -m venv .venv**
> **.\.venv\Scripts\activate**

**[Step 2]** 升級基礎編譯套件並安裝核心依賴庫：

> **python -m pip install --upgrade pip setuptools wheel**
> **pip install pymobiledevice3**

---

## 🚀 啟動指南 (Quick Start)

1.  將你的 iPhone / iPad 透過 USB 連接至電腦，並解鎖選擇「**信任此電腦**」。
2.  啟動虛擬環境後，直接執行主程式（請確保終端機擁有管理員權限，以利背景服務順利運行）：

> **python main.py**

3.  程式會自動在背景啟動 `tunneld` 守護行程，並自動掃描所有連接的設備。
4.  在左側選單 **TARGET DEVICE** 鎖定你的目標設備（若需控制多台，請勾選 `Fleet Sync` 開關），即可開始佈署！

---

## 🎮 戰術面板操作說明 (Tactical Operations)

* 📍 **TELEPORT (單點降落)**
    輸入精確經緯度，點擊 `ENGAGE TELEPORT` 瞬間空降。支援將常用座標透過 `Save Data` 儲存，或用 `Load Data` 載入待命。
* 🗺️ **NAVIGATION (自動巡航)**
    輸入目標座標與時速 (km/h)，點擊 `🔽 載入 TELEPORT 座標` 即可一鍵拉取數值。底層引擎會基於絕對時間進行精準配速。遇到緊急狀況可隨時點擊 `END ROUTE` 進行緊急煞車。
* 🕹️ **VIRTUAL JOYSTICK (虛擬搖桿)**
    使用滑鼠拖曳藍色推桿，即時控制人物走位。拖曳距離越遠，移動時速越高，實現無縫的微操走位。

---

## 📌 版本歷程 (Changelog)

關於詳細的架構重構、引擎擴缸與開發過程的踩坑紀錄，請參閱本專案的 **CHANGELOG.md**。

---

## ⚠️ 免責聲明 (Disclaimer)

本專案僅供學術研究、App 開發測試與個人地理資訊系統 (GIS) 實驗使用。請勿將其用於任何違反遊戲服務條款 (TOS) 或破壞遊戲平衡之行為。作者對因不當使用本工具而造成的帳號封鎖、設備異常或相關法律問題概不負責。

**Developed by 海浪**