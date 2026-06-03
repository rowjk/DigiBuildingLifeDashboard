# 統一數位大樓生活資訊平台 (Life Dashboard) 實作成果與驗證說明

本專案已完全依照 PRD、您的修正指示（管理員帳密為 `admin`/`admin`、天氣 API 金鑰以及北市府 API 連線失敗之錯誤訊息顯示規格）開發完成。

---

## 實作檔案清單

1. **依賴套件配置**：[requirements.txt](file:///c:/Users/james_wu/Documents/Antigravity_Project/統一數位大樓生活資訊平台 (Life Dashboard)/requirements.txt)
   * 包含 `streamlit`、`streamlit-autorefresh`、`sqlalchemy`、`httpx`、`pandas`、`feedparser`、`python-dotenv`。
2. **環境變數設定**：[.env](file:///c:/Users/james_wu/Documents/Antigravity_Project/統一數位大樓生活資訊平台 (Life Dashboard)/.env)
   * 已於本地的 `.env` 檔案中配置 `CWA_API_KEY`，該檔案已被 `.gitignore` 排除，防止金鑰外洩。
3. **資料庫宣告與種子資料**：[database.py](file:///c:/Users/james_wu/Documents/Antigravity_Project/統一數位大樓生活資訊平台 (Life Dashboard)/database.py)
   * 定義 `Announcement`、`Restaurant` 與 `AdminUser` 資料表。
   * 自定義 SHA256 密碼雜湊加密函數（加鹽處理）。
   * 自動建立 `dashboard.db`，並預建一筆管理員（`admin` / `admin`）、3 筆預設公告與 **20 筆周邊精選餐廳資料**。
4. **主程式與介面**：[app.py](file:///c:/Users/james_wu/Documents/Antigravity_Project/統一數位大樓生活資訊平台 (Life Dashboard)/app.py)
   * 整合四大 API（天氣、公車、YouBike、公告）後端快取（TTL 分別為 30分/1分/5分/10分），保護 API 流量。
   * 導入防禦性設計：API 逾時設定為 3.0 秒並略過 SSL 驗證，若失敗則使用 Mock 資料降級，並在畫面上方呈現對應之警報。
   * 設計 RWD 主畫面佈局（天氣、最新消息、YouBike、公車、午餐 Top 10、Google 地圖）。
   * 側邊欄實作管理員登入，驗證成功後展開可直接 CRUD 的數據編輯器 (`st.data_editor`)。
5. **說明文件**：[README.md](file:///c:/Users/james_wu/Documents/Antigravity_Project/統一數位大樓生活資訊平台 (Life Dashboard)/README.md)
   * 本機部署與運行說明。

---

## 防禦性與降級設計驗證成果

* **SSL 凭證問題排除**：在請求 `data.taipei` 及大台北公車 API 時，程式均已強制指定 `verify=False` 略過憑證檢驗，確保不會因憑證缺失拋出連線失敗錯誤。
* **北市府公告 API 錯誤降級**：
  * 當 API 連線失敗或找不到資料集時，警報橫幅已設定為符合您要求的規格：
    `北市府API無資料或無法連線(錯誤訊息：{error_message})`。
  * 系統會自動改用 Mock 北市府公告，其中包含一筆「停班停課」災害公告，成功觸發最上方紅色的緊急防災警告橫幅（st.error）。
* **公車到站即時對應**：
  * 後端在啟動時會快取靜態 `GetStop.gz` 及 `GetRoute.gz`。
  * 每分鐘動態下載 `GetEstimateTime.gz` 在記憶體中對應，成功過濾出指定的四個站點（南京金莊路口、新湖一路口、石潭成功路口、石潭金豐街口）並將 `RouteID` 翻譯為清晰的公車路線名稱。
* **YouBike 2.0 站點**：
  * 主動請求最新 YouBike 2.0 欄位結構（`available_rent_bikes` / `available_return_bikes`），無痛過濾出內湖科技園區週邊指定站點。

---

## 如何在本機運行與測試

1. 在專案根目錄下，開啟終端機並執行以下指令啟動：
   ```bash
   streamlit run app.py
   ```
2. 啟動後，瀏覽器會自動開啟 `http://localhost:8501`。
3. **測試後台管理 (CRUD)**：
   * 展開左方側邊欄，點擊「切換至後台管理」。
   * 輸入帳號 `admin`，密碼 `admin` 登入。
   * 在「公告資料管理」或「推薦餐廳管理」中點選空白行即可新增，或是點選格線進行修改。
   * 修改完成後，點擊對應之「**儲存變更**」按鈕，主畫面將會立即同步更新。
