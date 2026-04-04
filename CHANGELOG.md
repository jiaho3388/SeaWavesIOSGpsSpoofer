# 變更紀錄 (Changelog)

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