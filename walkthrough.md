# 統一數位大樓生活資訊平台 (Life Dashboard) 實作成果與驗證說明

本專案已完全依照 PRD、您的修正指示（管理員帳密為 `admin`/`admin`、天氣 API 金鑰、北市府 API 連線失敗之錯誤訊息顯示規格）以及**北市府 API 連線修正**、**版本控制 / GitHub 遠端倉庫上傳**、**套用 Newsprint 視覺設計系統**、**標題與間距優化**與**HTML 渲染異常修復與更名**開發並完成交付。

此外，針對最新的 YouBike 2.0 及大台北公車即時到站動態的顏色樣式要求，亦已實作色彩閾值與方向視覺化。

---

## 實作檔案清單

1. **依賴套件配置**：[requirements.txt](file:///c:/Users/james_wu/Documents/Antigravity_Project/統一數位大樓生活資訊平台 (Life Dashboard)/requirements.txt)
   * 包含 `streamlit`、`streamlit-autorefresh`、`sqlalchemy`、`httpx`、`pandas`、`feedparser`、`python-dotenv`。
2. **環境變數設定**：[.env](file:///c:/Users/james_wu/Documents/Antigravity_Project/統一數位大樓生活資訊平台 (Life Dashboard)/.env)
   * 已於本地的 `.env` 檔案中配置 `CWA_API_KEY`，該檔案已被 `.gitignore` 排除，防止金鑰外洩。
3. **資料庫宣告與種子資料**：[database.py](file:///c:/Users/james_wu/Documents/Antigravity_Project/統一數位大樓生活資訊平台 (Life Dashboard)/database.py)
   * 定義 `Announcement`、`Restaurant` 與 `AdminUser` 資料表。
   * 自動建立 `dashboard.db`，並預建一筆管理員（`admin` / `admin`）、3 筆預設公告與 **20 筆周邊精選餐廳資料**。
4. **主程式與介面**：[app.py](file:///c:/Users/james_wu/Documents/Antigravity_Project/統一數位大樓生活資訊平台 (Life Dashboard)/app.py)
   * 整合四大 API，導入防禦性快取與自動降級機制。
   * **全面導入 Newsprint 視覺風格**：引進 Google Fonts (`Fraunces` + `Inter`)，全直角設計，黑白高對比版型，客製化 Streamlit 按鈕、輸入框與警告元件。
   * **標題與間距優化**：移除 `h1` 底部的邊框以消除重複雙線問題，並將右側時間狀態對齊，縮小與底部分線間距。
   * **垂直單欄佈局**：所有區塊均以單欄上下垂直排列。
   * **捲動軸容器與 HTML 渲染修復**：引入 `strip_html` 排除 Markdown 程式碼區塊縮排解析 Bug，使公告區與公車到站表格完美加載為 HTML。將公告區標題更新為「最新公告」。
   * **色彩閾值與方向視覺化**：為 YouBike 數值以及公車去返程與預估到站時間提供動態顏色渲染。
5. **說明文件與優化規畫**：[README.md](file:///c:/Users/james_wu/Documents/Antigravity_Project/統一數位大樓生活資訊平台 (Life Dashboard)/README.md)
   * 安裝、執行與未來優化與擴充計畫的完整說明。
6. **視覺設計規範**：[newsprint_style_guide.md](file:///c:/Users/james_wu/Documents/Antigravity_Project/統一數位大樓生活資訊平台 (Life Dashboard)/newsprint_style_guide.md)
   * 報紙印刷風格的視覺標記與實作指南。
7. **Git 版本控制規則**：[.gitignore](file:///c:/Users/james_wu/Documents/Antigravity_Project/統一數位大樓生活資訊平台 (Life Dashboard)/.gitignore)
   * 排除敏感資訊（`.env`）、本機資料庫（`dashboard.db`）以及快取檔案與暫存腳本。

---

## HTML 渲染修復與更名成果說明

針對您反饋的「頁面壞掉（公告與公車區塊顯示 HTML 原始碼）」以及「公告區更名」需求，我們進行了以下修正：

1. **修復 HTML 渲染異常問題（解決 Markdown 程式碼區塊解析 Bug）**：
   * **異常原因**：由於 Streamlit 的 `st.markdown(..., unsafe_allow_html=True)` 會同時進行 Markdown 解析。在 Python 中寫入多行字串時，若 HTML 標籤（如 `<div>`, `<tr>` 等）前面帶有 4 個以上的空格（即程式碼的縮排），Markdown 解析器會誤判定為 `<pre><code>` 程式碼區塊，進而將 HTML 程式碼當作純文字輸出。
   * **修復方法**：我們在 `app.py` 中引入了全新的輔助函數 `strip_html`：
     ```python
     def strip_html(html_str):
         return "".join(line.strip() for line in html_str.strip().split("\n"))
     ```
     該函數會在渲染前將多行 HTML 的換行符號去除，並抹除每一行的前導空格，將整個 HTML 結構壓縮為單行 contiguous 的純 HTML 字串。
   * **效果**：這徹底消除了 Markdown 解析器的縮排代碼塊判定 Bug，使「最新公告欄」與「公車即時到站表格」能 100% 正確被瀏覽器渲染為 HTML 元件，且保有自訂的 Newsprint 直角捲動軸。
2. **公告區更名**：
   * 依照您的指示，已將該區塊標題由 `📢 最新與緊急公告區` 簡化更名為 `📢 最新公告`。

---

## YouBike 與公車即時資訊色彩閾值視覺化成果說明

針對您新提出的「YouBike 2.0 站點與公車即時到站顏色樣式」需求，我們進行了以下視覺設計更新：

1. **YouBike 2.0 即時站點看板數字顏色調整**：
   * **可借車 (sbi)**：預設字體顏色設為深藍色 (`#0000AA`)。若可借車數 **小於等於 2 輛**，則轉為醒目的紅色 (`#CC0000`) 警示。
   * **可還車 (bemp)**：預設字體顏色設為深綠色 (`#00AA00`)。若可還車數 **小於等於 2 輛**，則轉為紅色 (`#CC0000`) 警示。
2. **大台北公車即時到站動態資料顏色調整**：
   * **去返程方向分色**：若公車的去返程為「去程」，整行資料的文字顏色渲染為深藍色 (`#0000AA`)；若為「返程」，整行資料的文字顏色渲染為深綠色 (`#00AA00`)。
   * **預估到站時間緊急高亮**：若公車預估到站時間 **少於或等於 2 分鐘**（包含「即將到站」），該欄位的值會自動轉為紅色 (`#CC0000`) 加粗字體，提供直覺的趕車提醒。

---

## 標題優化、資料手動更新與回到最上方按鈕成果說明

針對您反饋的最新三項需求，我們已完成以下實作：

1. **移除主標題圖示**：
   * 已將 `app.py` 中 `🏢 統一數位大樓生活資訊平台` 左側的 `🏢` 建築物 emoji 移除，呈現更乾淨專業的新聞紙主標頭。
2. **右上角加入「資料更新」按鈕**：
   * 在右上角系統時間與自動載入倒數提示的下方，新增了使用 `UPDATE.png` 圖示作為按鈕的手動更新連結。該圖示以 Base64 編碼方式直接嵌入 HTML 結構，且其尺寸設定為與「回到最上方」按鈕相同的 `50px * 50px` 大小。
   * **功能邏輯**：點選此按鈕會發送 `?refresh=1` 的網頁查詢參數，當 Streamlit 檢測到此參數時，會主動清除所有第三方 API 的快取資料（天氣、YouBike 2.0、公車即時到站、北市府最新消息公告），接著以 `st.query_params.clear()` 及 `st.rerun()`完成重刷與參數重設，確保您可以即時點選重刷資料且不會陷入重刷循環。
3. **右下角加入「回到最上方」按鈕**：
   * 在網頁的最頂部埋入了不可見的滾動錨點 `<div id='linkto_top'></div>`。
   * 在網頁的右下角固定定位（`position: fixed`）呈現回到最上方按鈕，該按鈕讀取專案目錄下的 `BackToTop.png` 檔案，利用 Base64 編碼技術將二進位圖像直接嵌入 HTML 作為資料 URI (`data:image/png;base64`)，其尺寸為 `50px * 50px`。
   * **懸停與點選效果**：滑鼠移至按鈕上時會自動放大 10%（`scale(1.1)`）並觸發 Newsprint 黑白反白濾鏡效果（`filter: invert(1)`），點選後會將瀏覽器平滑捲動回頁面頂部的錨點。

---

## 今日天氣區塊色彩閾值視覺化成果說明

我們針對「今日即時天氣 (內湖區)」區塊中的 **溫度** 及 **體感溫度** 數值，實作了動態色彩顯示規則，能根據天氣溫度高低自動高亮：

1. **高溫警示（大於等於 30°C）**：
   * 當溫度或體感溫度數值大於等於 `30` 時，數字會以紅色 (`#CC0000`) 呈現，提供直覺的炎熱警示。
2. **適溫顯示（介於 20°C 至 29.x°C）**：
   * 當溫度或體感溫度數值在 `20` 到 `29`（含小數，如 `29.5`）度之間時，數字會以綠色 (`#00AA00`) 呈現，代表氣溫適中舒服。
3. **低溫顯示（小於 20°C）**：
   * 當溫度或體感溫度數值低於 `20` 度時，數字會以藍色 (`#0000AA`) 呈現，提示氣溫偏涼或寒冷。

4. **降雨機率分色（小於等於 30% 顯示藍色，其餘顯示紅色）**：
   * 當降雨機率數值小於或等於 `30` 時，數字會以藍色 (`#0000AA`) 呈現，代表降雨機率低，天氣穩定。
   * 當降雨機率數值大於 `30` 時，數字會以紅色 (`#CC0000`) 呈現，提示出門需帶傘。

這個機制同時適用於氣象署即時 API 數據以及 API 斷網時自動加載的本地 Mock 數據。

---

## 如何在本機運行與測試

1. 在專案根目錄下，開啟終端機並執行以下指令啟動：
   ```bash
   streamlit run app.py
   ```
2. 或直接雙擊 `啟動Life_Dashboard.bat` 啟動服務。
3. 啟動後，瀏覽器會自動開啟並導向本機網址 `http://localhost:8501`。
4. **測試後台管理 (CRUD)**：
   * 展開左方側邊欄，點擊「切換至後台管理」。
   * 輸入帳號 `admin`，密碼 `admin` 登入。
   * 在「公告資料管理」或「推薦餐廳管理」中點選空白行即可新增，或是點選格線進行修改。
   * 修改完成後，點擊對應之「**儲存變更**」按鈕，主畫面將會立即同步更新。
