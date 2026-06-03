import os
import gzip
import json
import uuid
import datetime
import hashlib
import httpx
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from database import get_session, Announcement, Restaurant, AdminUser, hash_password

# Load environment variables
load_dotenv()

# Set page configuration
st.set_page_config(
    page_title="統一數位大樓生活資訊平台 (Life Dashboard)",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ----------------- CSS Custom Styling -----------------
st.markdown("""
<style>
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 15px;
        border: 1px solid #dee2e6;
        margin-bottom: 10px;
    }
    .metric-label {
        font-size: 0.9rem;
        color: #6c757d;
    }
    .metric-value {
        font-size: 1.6rem;
        font-weight: bold;
        color: #212529;
    }
    .weather-card {
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        color: white;
        border-radius: 8px;
        padding: 20px;
        margin-bottom: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .weather-title {
        font-size: 1.2rem;
        font-weight: bold;
        margin-bottom: 10px;
    }
    .weather-temp {
        font-size: 2.5rem;
        font-weight: bold;
    }
    .weather-details {
        font-size: 0.95rem;
        margin-top: 5px;
    }
</style>
""", unsafe_allow_html=True)

# ----------------- Time-based Auto-Refresh -----------------
# Trigger refresh every 60 seconds
count = st_autorefresh(interval=60000, key="dashboard_refresher")

# ----------------- Global Memory Cache Helper Functions -----------------

# 1. Weather Data (TTL = 30 mins)
@st.cache_data(ttl=1800)
def fetch_weather():
    api_key = os.getenv("CWA_API_KEY")
    if not api_key:
        raise ValueError("缺少中央氣象署 API 金鑰 (CWA_API_KEY)")
        
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-D0047-061"
    params = {
        "Authorization": api_key,
        "locationName": "內湖區"
    }
    
    # We bypass SSL verification if CWA certificate is missing Subject Key Identifier
    with httpx.Client(verify=False, timeout=3.0) as client:
        r = client.get(url, params=params)
        if r.status_code != 200:
            raise RuntimeError(f"CWA API 回傳狀態碼 {r.status_code}")
        
        data = r.json()
        location_data = data["records"]["Locations"][0]["Location"][0]
        elements = location_data["WeatherElement"]
        
        weather_info = {
            "temp": "N/A",
            "apparent_temp": "N/A",
            "pop": "N/A",
            "desc": "N/A",
            "time": datetime.datetime.now().strftime("%H:%M:%S")
        }
        
        for el in elements:
            name = el["ElementName"]
            first_val_dict = el["Time"][0]["ElementValue"][0]
            if name == "溫度":
                weather_info["temp"] = f"{first_val_dict.get('Temperature', 'N/A')}°C"
            elif name == "體感溫度":
                weather_info["apparent_temp"] = f"{first_val_dict.get('ApparentTemperature', 'N/A')}°C"
            elif "降雨機率" in name:
                weather_info["pop"] = f"{first_val_dict.get('ProbabilityOfPrecipitation', 'N/A')}%"
            elif name == "天氣現象":
                weather_info["desc"] = first_val_dict.get("Weather", "N/A")
                
        return weather_info

# 2. Taipei Gov Announcements (TTL = 10 mins)
@st.cache_data(ttl=600)
def fetch_taipei_gov_announcements():
    import re
    import html
    
    # Dataset ID for Taipei City announcements (Latest News)
    dataset_id = "1a97fef5-dc98-4b6b-8694-5d6b3f6f2442"
    detail_url = f"https://data.taipei/dataset/detail?id={dataset_id}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    resource_url = None
    with httpx.Client(verify=False, timeout=5.0) as client:
        # 1. Fetch the dataset detail page to scrape the direct API URL
        try:
            r_page = client.get(detail_url, headers=headers)
            if r_page.status_code == 200:
                match = re.search(r'<script[^>]*id=["\']__NUXT_DATA__["\'][^>]*>(.*?)</script>', r_page.text, re.DOTALL)
                if match:
                    data = json.loads(match.group(1))
                    for item in data:
                        if isinstance(item, str) and ("OpenData.aspx" in item or "/OpenData" in item or "opendata" in item):
                            if item.startswith("http://") or item.startswith("https://"):
                                resource_url = item
                                break
        except Exception:
            pass

        # Fallback to the known static URL if dynamic scraping fails
        if not resource_url:
            resource_url = "https://www.gov.taipei/OpenData.aspx?SN=78702647C7A5B61B"
            
        # 2. Download announcements JSON from resource URL
        r_file = client.get(resource_url, headers=headers)
        if r_file.status_code != 200:
            raise RuntimeError(f"下載公告檔案失敗 ({r_file.status_code})")
            
        content = r_file.text.lstrip('\ufeff')
        news_list = json.loads(content)
        
        parsed_news = []
        for item in news_list[:5]:
            title = html.unescape(item.get("title", ""))
            # API uses "內容" for content
            content_text = html.unescape(item.get("內容", "") or item.get("content", ""))
            
            # Check for disaster keywords
            is_urgent = any(kw in title for kw in ["停班", "停課", "颱風", "地震", "災害"])
            
            # API uses "日期時間" for datetime
            raw_date = item.get("日期時間") or item.get("pubDate") or ""
            if raw_date:
                try:
                    display_date = raw_date.replace("T", " ")[:16]
                except Exception:
                    display_date = raw_date
            else:
                display_date = datetime.datetime.now().strftime("%Y-%m-%d")
                
            parsed_news.append({
                "title": title,
                "content": content_text[:150] + "..." if len(content_text) > 150 else content_text,
                "is_urgent": is_urgent,
                "source": "TaipeiGov",
                "created_at": display_date
            })
        return parsed_news

# 3. YouBike 2.0 (TTL = 5 mins)
@st.cache_data(ttl=300)
def fetch_youbike_data():
    # Correct active endpoint
    primary_url = "https://tcgbusfs.blob.core.windows.net/dotapp/youbike/v2/youbike_immediate.json"
    backup_url = "https://tcgbusfs.blob.core.windows.net/dotshare/youbike/youbike_immediate.json"
    
    data = None
    with httpx.Client(verify=False, timeout=3.0) as client:
        try:
            r = client.get(primary_url)
            if r.status_code == 200:
                data = r.json()
        except Exception:
            pass
            
        if data is None:
            # Fallback to backup
            r = client.get(backup_url)
            if r.status_code == 200:
                data = r.json()
                
    if not data:
        raise RuntimeError("無法連線 YouBike API 伺服器")
        
    target_stations = ["統一數位大樓", "石潭路", "成功路", "新湖"]
    filtered_stations = []
    
    for item in data:
        sna = item.get("sna", "")
        # Remove YouBike2.0_ prefix for display
        clean_name = sna.replace("YouBike2.0_", "")
        
        if any(ts in clean_name for ts in target_stations):
            # API might return available_rent_bikes/available_return_bikes or sbi/bemp
            sbi = item.get("available_rent_bikes") if item.get("available_rent_bikes") is not None else item.get("sbi", 0)
            bemp = item.get("available_return_bikes") if item.get("available_return_bikes") is not None else item.get("bemp", 0)
            update_time = item.get("updateTime") or item.get("mday") or "N/A"
            
            filtered_stations.append({
                "sna": clean_name,
                "sbi": sbi,
                "bemp": bemp,
                "update_time": update_time
            })
            
    return filtered_stations

# 4. Bus Static Stop/Route mapping (TTL = 24 hours)
@st.cache_data(ttl=86400)
def fetch_bus_static_data():
    stops_url = "https://tcgbusfs.blob.core.windows.net/blobbus/GetStop.gz"
    routes_url = "https://tcgbusfs.blob.core.windows.net/blobbus/GetRoute.gz"
    
    stops_dict = {}
    routes_dict = {}
    
    with httpx.Client(verify=False, timeout=5.0) as client:
        # Load stops
        r_stops = client.get(stops_url)
        if r_stops.status_code == 200:
            stops_json = json.loads(gzip.decompress(r_stops.content).decode('utf-8'))
            target_stop_names = ["石潭成功路口", "新湖一路口", "南京金莊路口", "石潭金豐街口"]
            for s in stops_json["BusInfo"]:
                for name in target_stop_names:
                    if name in s["nameZh"]:
                        stops_dict[int(s["Id"])] = {
                            "nameZh": s["nameZh"],
                            "routeId": int(s["routeId"]),
                            "goBack": int(s["goBack"])
                        }
                        
        # Load routes
        r_routes = client.get(routes_url)
        if r_routes.status_code == 200:
            routes_json = json.loads(gzip.decompress(r_routes.content).decode('utf-8'))
            for rt in routes_json["BusInfo"]:
                routes_dict[int(rt["Id"])] = rt["nameZh"]
                
    return stops_dict, routes_dict

# 5. Bus Estimates (TTL = 1 min)
@st.cache_data(ttl=60)
def fetch_bus_arrivals():
    stops_dict, routes_dict = fetch_bus_static_data()
    estimates_url = "https://tcgbusfs.blob.core.windows.net/blobbus/GetEstimateTime.gz"
    
    with httpx.Client(verify=False, timeout=3.0) as client:
        r = client.get(estimates_url)
        if r.status_code != 200:
            raise RuntimeError(f"無法取得公車動態資料 ({r.status_code})")
            
        estimates_json = json.loads(gzip.decompress(r.content).decode('utf-8'))
        
        arrivals = []
        for est in estimates_json["BusInfo"]:
            stop_id = int(est["StopID"])
            if stop_id in stops_dict:
                stop_info = stops_dict[stop_id]
                route_name = routes_dict.get(int(est["RouteID"]), f"路線 {est['RouteID']}")
                est_time = int(est["EstimateTime"])
                
                # Formatting remaining time
                if est_time >= 0:
                    est_desc = f"{est_time // 60} 分鐘" if est_time > 0 else "即將到站"
                elif est_time == -1:
                    est_desc = "尚未發車"
                elif est_time == -2:
                    est_desc = "交管不停靠"
                elif est_time == -3:
                    est_desc = "末班車已過"
                elif est_time == -4:
                    est_desc = "今日未營運"
                else:
                    est_desc = "無資料"
                    
                arrivals.append({
                    "route": route_name,
                    "stop": stop_info["nameZh"],
                    "go_back": "去程" if stop_info["goBack"] == 0 else "返程",
                    "desc": est_desc,
                    "raw_time": est_time
                })
                
        return arrivals

# ----------------- Mock Fallback Datasets -----------------
def get_mock_weather():
    return {
        "temp": "26°C",
        "apparent_temp": "28°C",
        "pop": "30%",
        "desc": "多雲午後短暫陣雨 (暫存)",
        "time": datetime.datetime.now().strftime("%H:%M:%S")
    }

def get_mock_taipei_announcements():
    return [
        {
            "title": "【災害防救】北市府因應強烈颱風接近，宣布明日全市停止上班上課",
            "content": "根據中央氣象署最新颱風預報資訊，本市已達停班停課標準，為保障市民生命安全，明日 (6/4) 停止上班上課。請市民減少外出防範災害。",
            "is_urgent": True,
            "source": "TaipeiGov",
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d")
        },
        {
            "title": "臺北市基隆路地下道車載與號誌更新工程施工管制說明",
            "content": "台北市工務局宣布，將自本月 10 日起夜間管制基隆路部分車道，請夜間通勤用路人提前改道行駛並配合交通疏導。",
            "is_urgent": False,
            "source": "TaipeiGov",
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d")
        }
    ]

def get_mock_youbike_data():
    return [
        {"sna": "捷運石潭站 (石潭路)", "sbi": 12, "bemp": 18, "update_time": "暫存資料"},
        {"sna": "石潭金豐街口 (統一數位大樓)", "sbi": 5, "bemp": 25, "update_time": "暫存資料"},
        {"sna": "新湖一路口 (民權東路)", "sbi": 8, "bemp": 12, "update_time": "暫存資料"}
    ]

def get_mock_bus_arrivals():
    return [
        {"route": "204", "stop": "新湖一路口", "go_back": "去程", "desc": "5 分鐘", "raw_time": 300},
        {"route": "207", "stop": "新湖一路口", "go_back": "返程", "desc": "即將到站", "raw_time": 0},
        {"route": "藍50", "stop": "石潭成功路口", "go_back": "去程", "desc": "12 分鐘", "raw_time": 720},
        {"route": "617", "stop": "南京金莊路口", "go_back": "返程", "desc": "尚未發車", "raw_time": -1}
    ]

# ----------------- UI Rendering Implementation -----------------

# Cache Warnings Helper
warning_messages = []

# Fetch All Data Streams with Defensive Fallbacks
# 1. Weather
try:
    weather = fetch_weather()
except Exception as e:
    weather = get_mock_weather()
    warning_messages.append(f"天氣資料更新失敗，目前顯示暫存資訊 (錯誤訊息：{e})")

# 2. Taipei Gov Announcements
taipei_news = []
try:
    taipei_news = fetch_taipei_gov_announcements()
except Exception as e:
    taipei_news = get_mock_taipei_announcements()
    warning_messages.append(f"北市府API無資料或無法連線(錯誤訊息：{e})")

# 3. YouBike
try:
    youbike_list = fetch_youbike_data()
except Exception as e:
    youbike_list = get_mock_youbike_data()
    warning_messages.append(f"YouBike 即時資料更新失敗，目前顯示暫存資訊 (錯誤訊息：{e})")

# 4. Bus Dynamics
try:
    bus_list = fetch_bus_arrivals()
except Exception as e:
    bus_list = get_mock_bus_arrivals()
    warning_messages.append(f"公車動態資料更新失敗，目前顯示暫存資訊 (錯誤訊息：{e})")

# 5. Local Announcements from SQLite
db = get_session()
local_news = db.query(Announcement).order_by(Announcement.created_at.desc()).all()
all_news = []

# Merge Taipei Gov news and Local SQLite news
for item in taipei_news:
    all_news.append(item)
for item in local_news:
    all_news.append({
        "title": item.title,
        "content": item.content,
        "is_urgent": item.is_urgent,
        "source": item.source,
        "created_at": item.created_at.strftime("%Y-%m-%d %H:%M")
    })

# Check if there is any urgent announcement
has_urgent_announcement = any(news["is_urgent"] for news in all_news)

# --- Streamlit Layout ---

# Display Warnings at the very top
if warning_messages:
    for msg in warning_messages:
        st.warning(msg)

# Display Red Urgent Banner if any is_urgent is True
if has_urgent_announcement:
    st.error("🚨 【緊急災害與防災公告】目前存在緊急狀態，請查閱下方緊急公告內容！")

# Header Section
col_header_left, col_header_right = st.columns([3, 1])
with col_header_left:
    st.title("🏢 統一數位大樓生活資訊平台 (Life Dashboard)")
with col_header_right:
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.write(f"**系統時間**：{now_str}")
    # Compute countdown
    st.write(f"⏱️ 網頁每 60 秒自動重新載入 ({count})")

st.markdown("---")

# Row 1: Weather (Left) & Announcements (Right)
row1_left, row1_right = st.columns([1, 1])

with row1_left:
    st.subheader("☀️ 今日即時天氣 (內湖區)")
    st.markdown(f"""
    <div class="weather-card">
        <div class="weather-title">台北市內湖區石潭路 155 號</div>
        <div class="weather-temp">{weather['temp']}</div>
        <div class="weather-details">
            <b>天氣現象</b>：{weather['desc']}<br/>
            <b>體感溫度</b>：{weather['apparent_temp']}<br/>
            <b>降雨機率</b>：{weather['pop']}<br/>
            <small style="opacity: 0.8;">更新時間：{weather['time']}</small>
        </div>
    </div>
    """, unsafe_allow_html=True)

with row1_right:
    st.subheader("📢 最新與緊急公告區")
    for news in all_news[:5]:
        card_type = "st.error" if news["is_urgent"] else "st.info"
        title_prefix = "🚨【緊急】" if news["is_urgent"] else "📌"
        
        with st.container():
            if news["is_urgent"]:
                st.error(f"**{title_prefix} {news['title']}** ({news['source']} - {news['created_at']})\n\n{news['content']}")
            else:
                st.info(f"**{title_prefix} {news['title']}** ({news['source']} - {news['created_at']})\n\n{news['content']}")

st.markdown("---")

# Row 2: YouBike (Left) & Bus Arrivals (Right)
row2_left, row2_right = st.columns([1, 1])

with row2_left:
    st.subheader("🚲 YouBike 2.0 即時站點看板")
    if youbike_list:
        cols_yb = st.columns(min(len(youbike_list), 3))
        for idx, yb in enumerate(youbike_list[:3]):
            with cols_yb[idx]:
                st.markdown(f"""
                <div class="metric-card">
                    <div style="font-weight: bold; font-size: 1rem; color: #0d6efd;">{yb['sna']}</div>
                    <div style="display: flex; justify-content: space-between; margin-top: 10px;">
                        <div>
                            <span class="metric-label">可借車</span><br/>
                            <span class="metric-value" style="color: #2e7d32;">{yb['sbi']}</span>
                        </div>
                        <div>
                            <span class="metric-label">可還車</span><br/>
                            <span class="metric-value" style="color: #c62828;">{yb['bemp']}</span>
                        </div>
                    </div>
                    <div style="font-size: 0.75rem; color: #6c757d; margin-top: 8px;">{yb['update_time']}</div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.write("目前無鄰近 YouBike 2.0 站點資料")

with row2_right:
    st.subheader("🚌 大台北公車即時到站動態")
    if bus_list:
        # Format list as a nice Pandas DataFrame for presentation
        bus_df = pd.DataFrame(bus_list)
        # Rename columns for layout
        bus_df_show = bus_df.rename(columns={
            "route": "路線",
            "stop": "站牌名稱",
            "go_back": "去返程",
            "desc": "預估到站時間"
        })[["路線", "站牌名稱", "去返程", "預估到站時間"]]
        st.dataframe(bus_df_show, use_container_width=True, hide_index=True)
    else:
        st.write("目前無公車到站資訊")

st.markdown("---")

# Row 3: Lunch Recommendations (Full Width)
st.subheader("🍲 石潭路大樓周邊午餐推薦 Top 10")
# Category Filters
category_options = ["全部", "便當", "麵食", "日式", "韓式", "美式", "健康餐"]
sort_options = ["評分高低 (Google Rating)", "距離近遠 (Distance)"]

col_filter1, col_filter2 = st.columns([1, 1])
with col_filter1:
    selected_category = st.selectbox("篩選餐廳分類", category_options)
with col_filter2:
    selected_sort = st.selectbox("排序方式", sort_options)

# Query database for restaurants
query_res = db.query(Restaurant)
if selected_category != "全部":
    query_res = query_res.filter(Restaurant.category == selected_category)

if "評分" in selected_sort:
    # Sort by rating desc, then reviews desc
    results = query_res.order_by(Restaurant.google_rating.desc(), Restaurant.review_count.desc()).limit(10).all()
else:
    # Sort by distance asc
    results = query_res.order_by(Restaurant.distance_meter.asc()).limit(10).all()

if results:
    res_data = []
    for r in results:
        res_data.append({
            "餐廳名稱": r.name,
            "分類": r.category,
            "Google 評分": f"⭐ {r.google_rating}",
            "評論數": f"{r.review_count} 則",
            "價位": "¥" * r.price_level,
            "步行距離": f"{r.distance_meter} 公尺"
        })
    df_res = pd.DataFrame(res_data)
    st.dataframe(df_res, use_container_width=True, hide_index=True)
else:
    st.write("無符合篩選條件的餐廳")

st.markdown("---")

# Row 4: 周邊地圖 Map Section (Full Width)
st.subheader("🗺️ 周邊生活機能地圖")
# Embedded Google Maps iframe for 台北市內湖區石潭路155號
iframe_src = "https://maps.google.com/maps?q=%E5%8F%B0%E5%8C%97%E5%B8%82%E5%85%A7%E6%B9%96%E5%8D%80%E7%9F%B3%E6%BD%AD%E8%B7%AF155%E8%99%9F&t=&z=16&ie=UTF8&iwloc=&output=embed"
st.components.v1.html(
    f'<iframe width="100%" height="450" frameborder="0" style="border:0; border-radius: 8px;" src="{iframe_src}" allowfullscreen></iframe>',
    height=460
)

# ----------------- Sidebar Admin Panel -----------------
with st.sidebar:
    st.header("⚙️ 系統設定與後台")
    enable_admin = st.checkbox("切換至後台管理", value=False)
    
    if enable_admin:
        st.subheader("管理員安全登入")
        admin_user = st.text_input("帳號", key="admin_username")
        admin_pass = st.text_input("密碼", type="password", key="admin_password")
        
        # Admin Validation
        admin_db = db.query(AdminUser).filter(AdminUser.username == admin_user).first()
        if admin_db and admin_db.password_hash == hash_password(admin_pass):
            st.success("登入成功！")
            
            st.markdown("---")
            st.subheader("🗂️ 公告資料管理 (CRUD)")
            
            # Fetch announcements to pandas
            an_query = db.query(Announcement).all()
            an_data = []
            for item in an_query:
                an_data.append({
                    "id": item.id,
                    "標題": item.title,
                    "內容": item.content,
                    "緊急公告": item.is_urgent,
                    "來源": item.source,
                    "建立時間": item.created_at
                })
            
            df_an = pd.DataFrame(an_data) if an_data else pd.DataFrame(columns=["id", "標題", "內容", "緊急公告", "來源", "建立時間"])
            
            # Data Editor for CRUD
            edited_an = st.data_editor(
                df_an,
                key="announcement_editor",
                num_rows="dynamic",
                disabled=["id", "建立時間"],
                use_container_width=True,
                hide_index=True
            )
            
            # Save Changes button
            if st.button("儲存公告變更"):
                # Handle deletes (missing in edited rows compared to original)
                original_ids = set(df_an["id"]) if not df_an.empty else set()
                edited_ids = set()
                
                # Update / Insert
                for _, row in edited_an.iterrows():
                    r_id = row.get("id")
                    if pd.notna(r_id) and r_id in original_ids:
                        edited_ids.add(r_id)
                        # Update existing
                        db_item = db.query(Announcement).filter(Announcement.id == r_id).first()
                        if db_item:
                            db_item.title = row["標題"]
                            db_item.content = row["內容"]
                            db_item.is_urgent = bool(row["緊急公告"])
                            db_item.source = row["來源"]
                    else:
                        # Insert new
                        new_item = Announcement(
                            title=row["標題"],
                            content=row["內容"],
                            is_urgent=bool(row["緊急公告"]),
                            source=row["來源"] if pd.notna(row["來源"]) else "Admin"
                        )
                        db.add(new_item)
                
                # Delete items that are missing
                for old_id in original_ids - edited_ids:
                    db.query(Announcement).filter(Announcement.id == old_id).delete()
                    
                db.commit()
                st.success("公告變更已成功儲存並同步至資料庫！")
                db.close()
                st.rerun()
                
            st.markdown("---")
            st.subheader("🍱 推薦餐廳管理 (CRUD)")
            
            # Fetch restaurants to pandas
            res_query = db.query(Restaurant).all()
            res_data = []
            for item in res_query:
                res_data.append({
                    "id": item.id,
                    "餐廳名稱": item.name,
                    "分類": item.category,
                    "評分": item.google_rating,
                    "評論數": item.review_count,
                    "價位等級": item.price_level,
                    "距離(公尺)": item.distance_meter,
                    "緯度": item.latitude,
                    "經度": item.longitude
                })
                
            df_res_crud = pd.DataFrame(res_data) if res_data else pd.DataFrame(columns=["id", "餐廳名稱", "分類", "評分", "評論數", "價位等級", "距離(公尺)", "緯度", "經度"])
            
            # Data Editor for CRUD
            edited_res = st.data_editor(
                df_res_crud,
                key="restaurant_editor",
                num_rows="dynamic",
                disabled=["id"],
                use_container_width=True,
                hide_index=True
            )
            
            # Save Changes button
            if st.button("儲存餐廳變更"):
                original_res_ids = set(df_res_crud["id"]) if not df_res_crud.empty else set()
                edited_res_ids = set()
                
                # Update / Insert
                for _, row in edited_res.iterrows():
                    r_id = row.get("id")
                    if pd.notna(r_id) and r_id in original_res_ids:
                        edited_res_ids.add(r_id)
                        # Update
                        db_item = db.query(Restaurant).filter(Restaurant.id == r_id).first()
                        if db_item:
                            db_item.name = row["餐廳名稱"]
                            db_item.category = row["分類"]
                            db_item.google_rating = float(row["評分"])
                            db_item.review_count = int(row["評論數"])
                            db_item.price_level = int(row["價位等級"])
                            db_item.distance_meter = int(row["距離(公尺)"])
                            db_item.latitude = float(row["緯度"]) if pd.notna(row["緯度"]) else None
                            db_item.longitude = float(row["經度"]) if pd.notna(row["經度"]) else None
                    else:
                        # Insert new
                        new_item = Restaurant(
                            name=row["餐廳名稱"],
                            category=row["分類"] if pd.notna(row["分類"]) else "便當",
                            google_rating=float(row["評分"]) if pd.notna(row["評分"]) else 4.0,
                            review_count=int(row["評論數"]) if pd.notna(row["評論數"]) else 100,
                            price_level=int(row["價位等級"]) if pd.notna(row["價位等級"]) else 1,
                            distance_meter=int(row["距離(公尺)"]) if pd.notna(row["距離(公尺)"]) else 100,
                            latitude=float(row["緯度"]) if pd.notna(row["緯度"]) else None,
                            longitude=float(row["經度"]) if pd.notna(row["經度"]) else None
                        )
                        db.add(new_item)
                        
                # Delete items that are missing
                for old_id in original_res_ids - edited_res_ids:
                    db.query(Restaurant).filter(Restaurant.id == old_id).delete()
                    
                db.commit()
                st.success("餐廳資訊已更新並同步至資料庫！")
                db.close()
                st.rerun()
                
        else:
            if admin_user or admin_pass:
                st.error("帳號或密碼錯誤，請重新輸入！")

# Close session
db.close()
