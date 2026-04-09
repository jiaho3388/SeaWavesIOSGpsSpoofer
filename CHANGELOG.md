# 🌊 SeaWaves iOS GPS Spoofer - 完整變更紀錄 (Changelog)

---

## [v2.4.1] Command Center Edition - 2026-04-09
* **[重構]** 拔除全域單一座標，引入 `device_coords` 陣列記憶體，每一台設備擁有獨立的實時座標狀態。
* **[新增]** 動態 FLEET RADAR UI：自動偵測連線設備數量，即時生成對應數量的雷達面板，互不干擾。
* **[新增]** 艦隊收束系統 (Fleet Convergence)：支援將位於不同起點的多台設備，透過自動導航同時精準收束至同一終點。

## [v2.4.0] Fleet Edition - 2026-04-09
* **[重構]** 引擎擴缸，實作「多執行緒引擎池 (Engine Pool)」，支援同時對多台 iOS 設備開啟獨立 DVT 隧道。
* **[新增]** 加入「🚀 Fleet Sync (多機同步連動)」開關。TELEPORT、自動導航、虛擬搖桿皆可一鍵廣播至所有連線設備。

## [v2.3.5] - 2026-04-09
* **[修正]** 解決自動導航 Time Drift (時間差) 問題，引擎改採 `time.time()` 絕對時間軸插值計算，確保時速 100% 吻合設定值。
* **[修正]** 修復 `save_data` 存檔時 Latitude 與 Longitude 寫入反轉的 Bug。
* **[新增]** 自動導航面板新增「🔽 載入 TELEPORT 座標」一鍵同步按鈕，提升操作流暢度。

## [v2.3.4] - 2026-04-09
* **[優化]** 視窗高度擴展至 800px，優化儀表板佈局呼吸空間。
* **[修正]** 修復 `Load Data` 時會誤觸發 LIVE RADAR 更新的視覺 Bug（現已改為僅子彈上膛，不改變當前真實雷達）。

## [v2.3.3] - 2026-04-09
* **[新增]** 實裝 `END ROUTE` 緊急煞車按鈕，支援自動導航途中隨時強制中斷並解鎖 UI。

## [v2.3.1 ~ v2.3.2] - 2026-04-09
* **[重構]** 將「UI 輸入框」與「底層真實座標」徹底脫鉤，解決搖桿與導航互相覆蓋數值的 Bug。
* **[修正]** 修復因 UI 載入順序問題導致的 `<KeyRelease>` 事件綁定錯誤 (`AttributeError`)。

## [v2.2.1] Workflow Optimization - 2026-04-05
* **[優化]** 動線優化：將「DATA MANAGEMENT (資料管理)」移至右欄最上方，緊鄰降落按鈕，實現「載入檔案即降落」的流暢操作。
* **[優化]** 佈局調整：進一步細化左欄情報與右欄操作的權重，擴大顯示區域。
* **[修正]** 語法修正：修復上一版本 `side` 參數重複導致的啟動報錯。

## [v2.2.0] Pro Dashboard UI Upgrade - 2026-04-05
* **[重構]** 雙欄位中控台 (Dual-Column Dashboard)：視窗擴展至 850x700，將「情報監控」與「操作控制」完美分離。
* **[新增]** 現代化扁平卡片 (Card UI)：捨棄傳統 Tkinter LabelFrame 邊框，改用 `#1e1e1e` 深灰色塊與 `#121212` 底色創造懸浮層次感。
* **[優化]** 預設收合設計：將「自動導航」與「虛擬搖桿」設定為預設隱藏，維持版面極致簡潔，需要火力時再點擊展開。
* **[優化]** 等寬雷達字體：雷達座標數據改用 Consolas 字體，跳動時不再因為字元寬度不同而抖動。

## [v2.1.1] The Async/RSD Breakthrough - 2026-04-05
* **[核心]** 純 Python 底層引擎 (Pure Python Engine)：完全捨棄 `subprocess` 呼叫，直接將 `pymobiledevice3` 作為 Library 匯入，達成 0.1 秒極低延遲發送。
* **[核心]** 雙核非同步適應器 (Async/Sync Dual-Core)：導入 `asyncio` 與 `inspect` 模組，動態偵測並適應底層 API 的非同步/同步狀態。
* **[新增]** 萬能 RSD 解析器：全面支援 iOS 17/26 以上的 Remote Service Discovery 隧道，並向下相容舊版 `tunneld` 的 JSON 負載格式差異。
* **[修正]** 解決 `DvtSecureSocketProxy` 在新版中被重構為 `DvtProvider` 與 `DtxServiceProvider` 導致的匯入崩潰問題。
* **[修正]** 解決 `simulate_location` 函數被重構為 `async def set` 導致的生命週期中斷問題。
* **[修正]** 解決 `LocationSimulation` 轉變為非同步上下文管理器 (`async with`) 導致的連線拒絕錯誤。

## [v1.0.0] Initial Release
* **[發布]** 基於 `subprocess` 封裝的高階位置模擬工具。
* **[新增]** 支援自動導航、虛擬搖桿與多設備熱切換功能。
* **[新增]** 整合 `tunneld` 背景引擎。