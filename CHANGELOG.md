# 變更紀錄 (Changelog)

---

## [v2.2.1] - 2026-04-05 (Workflow Optimization)
### 🛠️ UI 改進
 - 動線優化：將「DATA MANAGEMENT (資料管理)」移至右欄最上方，緊鄰降落按鈕，實現「載入檔案即降落」的流暢操作。

 - 佈局調整：進一步細化左欄情報與右欄操作的權重，擴大顯示區域。

 - 語法修正：修復上一版本 side 參數重複導致的啟動報錯。

---

## [v2.2.0] - 2026-04-05 (Pro Dashboard UI Upgrade)
### ✨ UI/UX 重構
 - 雙欄位中控台 (Dual-Column Dashboard)：視窗擴展至 850x700，將「情報監控」與「操作控制」完美分離。

 - 現代化扁平卡片 (Card UI)：捨棄傳統 Tkinter LabelFrame 邊框，改用 #1e1e1e 深灰色塊與 #121212 底色創造懸浮層次感。

 - 預設收合設計：將「自動導航」與「虛擬搖桿」設定為預設隱藏，維持版面極致簡潔，需要火力時再點擊展開。

 - 等寬雷達字體：雷達座標數據改用 Consolas 字體，跳動時不再因為字元寬度不同而抖動。

---

## [v2.1.1] - 2026-04-05 (The Async/RSD Breakthrough)
### 🚀 核心引擎進化
 - 純 Python 底層引擎 (Pure Python Engine)：完全捨棄 subprocess 呼叫，直接將 pymobiledevice3 作為 Library 匯入，達成 0.1 秒極低延遲發送。

 - 雙核非同步適應器 (Async/Sync Dual-Core)：導入 asyncio 與 inspect 模組，動態偵測並適應底層 API 的非同步/同步狀態。

 - 萬能 RSD 解析器：全面支援 iOS 17/26 以上的 Remote Service Discovery 隧道，向下相容舊版 tunneld 的 JSON 負載格式差異。

### 🛠️ 錯誤修復
 - 解決 DvtSecureSocketProxy 在新版中被重構為 DvtProvider 與 DtxServiceProvider 導致的匯入崩潰問題。

 - 解決 simulate_location 函數被重構為 async def set 導致的生命週期中斷問題。

 - 解決 LocationSimulation 轉變為非同步上下文管理器 (async with) 導致的連線拒絕錯誤。

---

## [v2.1.1] - 2026-04-05 (The Async/RSD Breakthrough)
### 🚀 新增 (Added)
- **純 Python 底層引擎 (Pure Python Engine)**：完全捨棄 `subprocess` 呼叫，直接將 `pymobiledevice3` 作為 Library 匯入，達成 0.1 秒極低延遲發送。
- **雙核非同步適應器 (Async/Sync Dual-Core)**：導入 `asyncio` 與 `inspect` 模組，動態偵測並適應底層 API 的非同步/同步狀態。
- **萬能 RSD 解析器**：全面支援 iOS 17/26 以上的 Remote Service Discovery 隧道，並向下相容舊版 `tunneld` 的 JSON 負載格式差異。

### 🛠️ 修正 (Fixed)
- 解決 `DvtSecureSocketProxy` 在新版中被重構為 `DvtProvider` 與 `DtxServiceProvider` 導致的匯入崩潰問題。
- 解決 `simulate_location` 函數被重構為 `async def set` 導致的生命週期中斷問題。
- 解決 `LocationSimulation` 轉變為非同步上下文管理器 (`async with`) 導致的連線拒絕錯誤。

---

## [v1.0.0] - Initial Release
- 基於 `subprocess` 封裝的高階位置模擬工具。
- 支援自動導航、虛擬搖桿與多設備熱切換功能。
- 整合 `tunneld` 背景引擎。