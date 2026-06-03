# 台北市區與國道即時路況地理圍欄應用指南

本文件說明如何利用台北市政府與高公局提供的免費公開資料，建立一個**「依據指定地址，自動篩選並顯示附近路況」**的系統架構與實作邏輯。

---

## 🛠️ 開發核心邏輯：如何達成「指定地址顯示附近路況」？

由於路況原始資料（VD、事件）是以**經緯度座標**、**路段代碼 (LinkID)** 或 **國道里程 (Milage)** 呈現，要做到輸入地址查詢，你需要實作以下三個步驟：

1. **地址轉座標 (Geocoding)**：將使用者輸入的地址（例如：`台北市南港區經貿二路1號`），透過 API（如 Google Maps Geocoding API 或內政部 TGOS 免費門牌地址轉換服務）轉換成經緯度座標 $(Lng, Lat)$。
2. **地理圍欄篩選 (Geofencing / Spatial Query)**：
   * **市區道路**：計算該座標與台北市各路段基本資料（Shape 幾何線段）的距離，找出方圓 500 公尺 ~ 1 公里內的所有 `LinkID`。
   * **國道部分**：找出距離該座標最近的國道交流道或特定的里程數區間。
3. **資料比對與呈現**：拿篩選出來的 `LinkID` 或國道里程，去比對下方三個即時路況資料源，過濾出對應的車速與事件顯示在前端畫面或地圖上。

---

## 📊 資料來源規格說明

### 1. 台北市區道路即時車速 (VD)
* **資料格式**：JSON / XML (推薦使用 JSON 格式進行前端或後端解析)
* **動態 URL**：[https://tcgdata.taipei/opendata/datalist/datasetMeta/download?id=1fa2a74c-473d-4009-848e-28ff67839352&rid=006f7ff0-6927-4632-95ed-8e1205322987](https://tcgdata.taipei/opendata/datalist/datasetMeta/download?id=1fa2a74c-473d-4009-848e-28ff67839352&rid=006f7ff0-6927-4632-95ed-8e1205322987)
* **更新頻率**：約 5 分鐘更新一次。
* **核心欄位說明**：
  * `LinkID`：路段代碼（需搭配台北市路段幾何圖資，才能知道該路段的具體經緯度軌跡）。
  * `Speed`：該路段目前的平均車速 (km/h)。
  * `DataTime`：資料產生時間。

### 2. 國道即時車速與車流 (VD)
* **資料格式**：XML
* **動態 URL**：[https://tisvcloud.freeway.gov.tw/data/TX/OdataLiveVD.xml](https://tisvcloud.freeway.gov.tw/data/TX/OdataLiveVD.xml)
* **更新頻率**：每 5 分鐘更新一次。
* **核心欄位說明**：
  * `VDID`：車輛偵測器代碼。
  * `LinkID`：高公局定義之國道路段代碼。
  * `Speed`：當前偵測到的平均車速。
  * *開發提示*：若要與地址連動，需先下載高公局的[靜態 VD 設備位置定義檔](https://tisvcloud.freeway.gov.tw/data/TX/OdataVD.xml)，從中取得各 `VDID` 的經緯度座標或對應的國道名稱與里程（例如：國道1號 16.5K），才能進行距離計算。

### 3. 國道即時路況事件
* **資料格式**：XML
* **動態 URL**：[https://tisvcloud.freeway.gov.tw/data/TX/OdataLiveEvent.xml](https://tisvcloud.freeway.gov.tw/data/TX/OdataLiveEvent.xml)
* **更新頻率**：即時更新（有事件即寫入）。
* **核心欄位說明**：
  * `RoadName`：國道名稱（篩選「國道1號」或「國1」）。
  * `Milage`：事件發生的里程位置（例如：`23.5` 代表 23.5K 處）。
  * `Direction`：方向（北上/南下/雙向）。
  * `EventType`：事件類型（車禍、施工、散落物、回堵等）。
  * `Description`：詳細事件文字描述。

---

## 💻 推薦系統架構與實作建議

為了避免前端直接去呼叫上述 URL 導致**跨網域限制 (CORS)** 以及**效能瓶頸**，強烈建議採用「後端快取、前端查詢」的架構：

```
[ 使用者輸入地址 ] 
       │
       ▼
[ 前端網頁 / App ] ───(1. 地址轉經緯度)───> [ Geocoding API ]
       │                                         │
       │(2. 帶入座標查詢附近路況)                 ▼
       ▼                                    (取得 Lng, Lat)
[ 您的後端伺服器 (Node.js / Python) ]
       │
       ├─ (3. 比對空間資料庫，撈出方圓 1KM 內的 LinkID / 國道里程)
       │
       └─ (4. 從記憶體快取中，撈出這些 LinkID 的即時 Speed & Event)
       │
       ▼
[ 回傳過濾後的即時路況給前端呈現 ]
```

### ⚙️ 後端背景排程 (Cron Job)
* 撰寫一支背景程式，**每 5 分鐘**去下載並解析上述 3 個動態 URL。
* 將解析完的即時車速與事件，暫存於記憶體資料庫（如 Redis 或快取物件中），供前端即時查詢。不要每次使用者查地址就去撈一次官方 URL，以免被官方封鎖 IP。

### 🌍 如何計算兩點之間的距離？ (哈弗辛公式 Haversine Formula)
在後端比對座標與路段或偵測器距離時，如果沒有使用空間資料庫（如 PostGIS），可以用以下公式計算兩點間的直線距離：

$$\Delta Lat = Lat_2 - Lat_1$$
$$\Delta Lng = Lng_2 - Lng_1$$
$$a = \sin^2\left(\frac{\Delta Lat}{2}\right) + \cos(Lat_1) \cdot \cos(Lat_2) \cdot \sin^2\left(\frac{\Delta Lng}{2}\right)$$
$$c = 2 \cdot \operatorname{atan2}\left(\sqrt{a}, \sqrt{1-a}\right)$$
$$d = R \cdot c$$

*(其中 $R$ 為地球平均半徑，約 6371 公里；$d$ 即為兩點間的實際距離)*。藉此找出距離指定地址最近的 VD 觀測點與路況事件。
