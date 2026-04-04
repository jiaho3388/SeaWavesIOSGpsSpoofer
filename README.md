# Rei's iOS Location Simulator Pro (v1.0.0)

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

這是一款專為 iOS 設備設計的高階位置模擬工具，具備自動導航、虛擬搖桿與多設備切換功能。

## 🌟 核心特色
* **Rei's Dark Mode UI**: 極致暗黑風格介面，專為長時間開發與測試設計。
* **Dual-Engine Support**: 整合 `tunneld` 背景引擎，解決 iOS 17+ 的連線限制。
* **Smart Device Detection**: 自動偵測多台 iPhone，支援免重啟熱切換。
* **Collapsible Modules**: 導航與搖桿面板可自由收摺，維持介面清爽。
* **Scrollable Engine**: 支援滑鼠滾輪，完美適應各種螢幕解析度。

## 🛠️ 前置需求
1. **Python 3.10+**
2. **iTunes (Windows 版)**: 確保驅動程式正常運作。
3. **pymobiledevice3**: 請在終端機輸入 `pip install pymobiledevice3` 來安裝。
4. **管理員權限**: 啟動 `tunneld` 需以系統管理員身分執行。

## 🚀 快速開始
1. 將 iPhone 接上電腦並開啟「開發者模式」。
2. 執行 `python main.py`。
3. 於上方選單確認鎖定目標設備。
4. 設定座標或使用搖桿開始冒險。

## 📂 版本紀錄
* **v1.0.0 (當前版本)**: 穩定版。基於 `subprocess` 封裝，整合多設備管理與折疊 UI。

## 👨‍💻 關於專案與開發
此 iOS 虛擬定位模擬系統由 **海浪 (Rei)** 主導開發與維護。
本專案在架構設計與程式實作過程中，採用 **Gemini 3.1 Pro** 作為技術輔助工具，旨在結合現代化 AI 技術提升開發效率，建構一套穩定、優雅且易於擴充的自動化解決方案。

## ⚖️ 授權
本專案採用 MIT License 授權。