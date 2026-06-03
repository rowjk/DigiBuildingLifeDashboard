import os
import gzip
import json
import uuid
import datetime
import hashlib
import httpx
import math
import pandas as pd
import streamlit as st
import streamlit_antd_components as sac
from streamlit_js_eval import get_geolocation
from streamlit_autorefresh import st_autorefresh
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from database import get_session, Announcement, Restaurant, AdminUser, hash_password
import base64

# Base64 encode images for floating button and manual refresh button
back_to_top_base64 = ""
update_btn_base64 = ""
try:
    if os.path.exists("BackToTop.png"):
        with open("BackToTop.png", "rb") as img_file:
            back_to_top_base64 = base64.b64encode(img_file.read()).decode("utf-8")
    if os.path.exists("UPDATE.png"):
        with open("UPDATE.png", "rb") as img_file:
            update_btn_base64 = base64.b64encode(img_file.read()).decode("utf-8")
except Exception:
    pass

def strip_html(html_str):
    return "".join(line.strip() for line in html_str.strip().split("\n"))

def haversine_distance(lat1, lon1, lat2, lon2):
    try:
        lat1, lon1, lat2, lon2 = map(float, [lat1, lon1, lat2, lon2])
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        return c * 6371000  # in meters
    except Exception:
        return 999999.0

@st.cache_data(ttl=86400)
def google_geocode_or_search(query):
    if not query:
        return None
    api_key = os.getenv("GOOGLE_PLACES_API_KEY")
    # Predefined locales fallback
    predefined = {
        "台北車站": (25.0478, 121.5170),
        "捷運昆陽站": (25.0502, 121.5933),
        "捷運港墘站": (25.0798, 121.5751),
        "內湖好市多": (25.0617, 121.5796),
        "統一數位大樓": (25.059727, 121.589632),
        "南港車站": (25.052187, 121.606775),
        "台北101": (25.033976, 121.564539)
    }
    for k, v in predefined.items():
        if k in query:
            return v

    if api_key:
        url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
        params = {
            "input": query,
            "inputtype": "textquery",
            "fields": "geometry",
            "key": api_key
        }
        try:
            with httpx.Client(verify=False, timeout=3.0) as client:
                r = client.get(url, params=params)
                if r.status_code == 200:
                    data = r.json()
                    if data.get("candidates"):
                        loc = data["candidates"][0]["geometry"]["location"]
                        return float(loc["lat"]), float(loc["lng"])
        except Exception:
            pass

    # Free Nominatim geocoding fallback
    try:
        url = f"https://nominatim.openstreetmap.org/search"
        headers = {"User-Agent": "LifeDashboard/1.2"}
        params = {"q": query, "format": "json", "limit": 1}
        with httpx.Client(verify=False, timeout=3.0) as client:
            r = client.get(url, headers=headers, params=params)
            if r.status_code == 200:
                data = r.json()
                if data:
                    return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass
    return None

@st.cache_data(ttl=3600)
def fetch_google_place_details(restaurant_name, lat, lng):
    api_key = os.getenv("GOOGLE_PLACES_API_KEY")
    if api_key:
        try:
            # 1. Find Place to get Place ID
            find_url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
            find_params = {
                "input": restaurant_name,
                "inputtype": "textquery",
                "locationbias": f"point:{lat},{lng}",
                "fields": "place_id",
                "key": api_key
            }
            with httpx.Client(verify=False, timeout=3.0) as client:
                r_find = client.get(find_url, params=find_params)
                if r_find.status_code == 200:
                    find_data = r_find.json()
                    if find_data.get("candidates"):
                        place_id = find_data["candidates"][0]["place_id"]
                        
                        # 2. Get Details
                        details_url = "https://maps.googleapis.com/maps/api/place/details/json"
                        details_params = {
                            "place_id": place_id,
                            "fields": "name,rating,reviews,opening_hours,formatted_phone_number,website",
                            "key": api_key,
                            "language": "zh-TW"
                        }
                        r_details = client.get(details_url, params=details_params)
                        if r_details.status_code == 200:
                            det_data = r_details.json().get("result", {})
                            
                            # Parse details
                            rating = det_data.get("rating", 4.0)
                            reviews = []
                            for rev in det_data.get("reviews", [])[:3]:
                                reviews.append({
                                    "author": rev.get("author_name", "Google 顧客"),
                                    "rating": rev.get("rating", 5),
                                    "text": rev.get("text", "美味推薦！"),
                                    "time": rev.get("relative_time_description", "最近")
                                })
                            
                            op_hours = det_data.get("opening_hours", {})
                            open_now = op_hours.get("open_now")
                            weekday_text = op_hours.get("weekday_text", [])
                            
                            return {
                                "rating": rating,
                                "reviews": reviews,
                                "open_now": open_now,
                                "weekday_text": weekday_text,
                                "phone": det_data.get("formatted_phone_number", "無提供"),
                                "website": det_data.get("website", ""),
                                "is_mock": False
                            }
        except Exception:
            pass

    # Fallback to Mock Data
    open_now = True
    current_hour = datetime.datetime.now().hour
    if current_hour < 11 or current_hour > 21:
        open_now = False
        
    mock_reviews = [
        {"author": "James Chen", "rating": 5, "text": f"這家餐廳的服務很棒，環境乾淨！餐點份量十足，特別是招牌菜色非常好吃，極力推薦！", "time": "1 週前"},
        {"author": "林小姐", "rating": 4, "text": f"這家店的口味很棒，每到中午人都很多。是上班族午餐的優質選擇，出餐速度也很快！", "time": "3 天前"},
        {"author": "張先生", "rating": 4, "text": "味道很道地，價格親民。CP值極高！下次會想再來嘗試其他餐點。", "time": "2 週前"}
    ]
    
    weekday_text = [
        "星期一: 11:00 – 21:00",
        "星期二: 11:00 – 21:00",
        "星期三: 11:00 – 21:00",
        "星期四: 11:00 – 21:00",
        "星期五: 11:00 – 21:00",
        "星期六: 11:00 – 21:00",
        "星期日: 休息"
    ]
    
    return {
        "rating": 4.2,
        "reviews": mock_reviews,
        "open_now": open_now,
        "weekday_text": weekday_text,
        "phone": "02-2792-XXXX",
        "website": "https://maps.google.com",
        "is_mock": True
    }

# Load environment variables
load_dotenv()

# Set page configuration
st.set_page_config(
    page_title="統一數位大樓生活資訊平台 (Life Dashboard)",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Top Anchor for Back to Top Button
st.markdown("<div id='linkto_top'></div>", unsafe_allow_html=True)

# ----------------- Theme Switcher configuration -----------------
with st.sidebar:
    st.markdown("### 🎨 主題風格切換")
    selected_theme = sac.segmented(
        items=[
            sac.SegmentedItem(label="📰 新聞紙經典", icon="newspaper"),
            sac.SegmentedItem(label="🌙 優雅深色", icon="moon-stars"),
            sac.SegmentedItem(label="🌲 北歐極簡", icon="tree"),
            sac.SegmentedItem(label="⏳ 暖陽沙黃", icon="sun")
        ],
        align="center",
        color="dark",
        size="sm"
    )

# Map selected theme to CSS Variables
theme_vars = {
    "📰 新聞紙經典": {
        "bg-color": "#F7F4EF",
        "text-color": "#111111",
        "border-color": "#111111",
        "card-bg": "transparent",
        "accent-color": "#000000",
        "font-header": "'Fraunces', Georgia, serif",
        "font-body": "'Inter', system-ui, sans-serif",
        "radius": "0px",
        "border-style": "1px solid var(--border-color)",
        "hr-style": "3px double var(--border-color)",
        "box-shadow": "none",
        "alert-bg": "#FDF2F2",
        "alert-border": "#CC0000",
        "metric-value-color": "#111111",
        "scrollbar-thumb": "#111111"
    },
    "🌙 優雅深色": {
        "bg-color": "#0F172A",
        "text-color": "#F8FAFC",
        "border-color": "#334155",
        "card-bg": "#1E293B",
        "accent-color": "#38BDF8",
        "font-header": "'Inter', system-ui, sans-serif",
        "font-body": "'Inter', system-ui, sans-serif",
        "radius": "8px",
        "border-style": "1px solid var(--border-color)",
        "hr-style": "1px solid var(--border-color)",
        "box-shadow": "0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -2px rgba(0,0,0,0.1)",
        "alert-bg": "#311C1C",
        "alert-border": "#EF4444",
        "metric-value-color": "#38BDF8",
        "scrollbar-thumb": "#475569"
    },
    "🌲 北歐極簡": {
        "bg-color": "#ECEFF4",
        "text-color": "#2E3440",
        "border-color": "#D8DEE9",
        "card-bg": "#FFFFFF",
        "accent-color": "#5E81AC",
        "font-header": "'Inter', system-ui, sans-serif",
        "font-body": "'Inter', system-ui, sans-serif",
        "radius": "12px",
        "border-style": "none",
        "hr-style": "2px solid #E5E9F0",
        "box-shadow": "0 10px 15px -3px rgba(0,0,0,0.05), 0 4px 6px -4px rgba(0,0,0,0.05)",
        "alert-bg": "#F5F2EB",
        "alert-border": "#5E81AC",
        "metric-value-color": "#5E81AC",
        "scrollbar-thumb": "#D8DEE9"
    },
    "⏳ 暖陽沙黃": {
        "bg-color": "#F5F2EB",
        "text-color": "#3C2F2F",
        "border-color": "#E6DFD3",
        "card-bg": "#FAF8F5",
        "accent-color": "#D4A373",
        "font-header": "'Fraunces', Georgia, serif",
        "font-body": "'Inter', system-ui, sans-serif",
        "radius": "4px",
        "border-style": "1px solid var(--border-color)",
        "hr-style": "2px dashed var(--border-color)",
        "box-shadow": "2px 2px 0px var(--border-color)",
        "alert-bg": "#FDF6EC",
        "alert-border": "#E6A23C",
        "metric-value-color": "#D4A373",
        "scrollbar-thumb": "#D4A373"
    }
}

selected_theme = selected_theme or "📰 新聞紙經典"
cfg = theme_vars.get(selected_theme, theme_vars["📰 新聞紙經典"])

# ----------------- CSS Custom Styling -----------------
st.markdown(f"""
<style>
    /* 匯入襯線與無襯線 Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,700;0,9..144,900;1,9..144,400&family=Inter:wght@400;500;600;700&family=Outfit:wght@400;600;800&display=swap');

    :root {{
        --bg-color: {cfg['bg-color']};
        --text-color: {cfg['text-color']};
        --border-color: {cfg['border-color']};
        --card-bg: {cfg['card-bg']};
        --accent-color: {cfg['accent-color']};
        --font-header: {cfg['font-header']};
        --font-body: {cfg['font-body']};
        --radius: {cfg['radius']};
        --border-style: {cfg['border-style']};
        --hr-style: {cfg['hr-style']};
        --box-shadow: {cfg['box-shadow']};
        --alert-bg: {cfg['alert-bg']};
        --alert-border: {cfg['alert-border']};
        --metric-value-color: {cfg['metric-value-color']};
        --scrollbar-thumb: {cfg['scrollbar-thumb']};
    }}

    /* 覆寫 Streamlit 全域底色與字體 */
    .stApp {{
        background-color: var(--bg-color) !important;
        color: var(--text-color) !important;
        font-family: var(--font-body), sans-serif;
    }}
    
    /* 調整主容器邊界 */
    .block-container {{
        padding-top: 2rem !important;
        padding-bottom: 2rem !important;
        max-width: 1200px;
    }}

    /* 報紙標題樣式 */
    h1 {{
        font-family: var(--font-header) !important;
        font-weight: 900 !important;
        color: var(--text-color) !important;
        border-bottom: none !important;
        padding-bottom: 0px !important;
        margin-bottom: 0px !important;
        letter-spacing: -0.03em !important;
        line-height: 1.2 !important;
    }}
    
    h1 span.title-subtitle {{
        font-size: 80% !important; /* 縮小 20% */
        display: block !important;
        margin-top: 6px !important;
        text-transform: uppercase !important;
        font-weight: 700 !important;
        letter-spacing: 0.05em !important;
    }}

    h2, h3, .stSubheader {{
        font-family: var(--font-header) !important;
        font-weight: 700 !important;
        color: var(--text-color) !important;
        border-bottom: var(--border-style) !important;
        padding-bottom: 6px !important;
        margin-top: 2rem !important;
        margin-bottom: 1.2rem !important;
    }}

    /* 刪除 Streamlit 預設元件的圓角與陰影 */
    div[data-testid="stMetricValue"] {{
        font-family: var(--font-header) !important;
        font-weight: 900 !important;
        color: var(--metric-value-color) !important;
    }}
    
    /* YouBike 等資訊卡片：化身為報紙欄欄位 */
    .metric-card {{
        background-color: var(--card-bg) !important;
        border-radius: var(--radius) !important;
        padding: 15px !important;
        border: var(--border-style) !important;
        box-shadow: var(--box-shadow) !important;
        margin-bottom: 15px !important;
    }}
    
    .metric-label {{
        font-size: 0.85rem !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: var(--text-color) !important;
        opacity: 0.8;
        font-family: var(--font-body);
    }}
    
    .metric-value {{
        font-size: 1.8rem !important;
        font-family: var(--font-header) !important;
        font-weight: 900 !important;
        color: var(--metric-value-color);
    }}

    /* 天氣卡片：由炫目漸層改為極簡新聞專欄風格 */
    .weather-card {{
        background: var(--card-bg) !important;
        color: var(--text-color) !important;
        border-radius: var(--radius) !important;
        padding: 20px !important;
        border: var(--border-style) !important;
        box-shadow: var(--box-shadow) !important;
        margin-bottom: 20px !important;
    }}
    
    .weather-title {{
        font-family: var(--font-header) !important;
        font-size: 1.1rem !important;
        font-weight: bold !important;
        border-bottom: 1px dashed var(--border-color);
        padding-bottom: 8px;
        margin-bottom: 12px !important;
    }}
    
    .weather-temp {{
        font-family: var(--font-header) !important;
        font-size: 3rem !important;
        font-weight: 900 !important;
        line-height: 1 !important;
        margin-bottom: 10px;
    }}
    
    .weather-details {{
        font-size: 0.95rem !important;
        line-height: 1.6 !important;
    }}

    /* 調整警告橫幅 (st.warning / st.error) 符合報紙社論插頁風格 */
    .stAlert {{
        border-radius: var(--radius) !important;
        border: 1px solid var(--alert-border) !important;
        background-color: var(--alert-bg) !important;
        color: var(--alert-border) !important;
    }}

    /* 表格與 Dataframe 風格化 */
    div[data-testid="stTable"], .element-container iframe {{
        border: var(--border-style) !important;
        border-radius: var(--radius) !important;
    }}
    
    /* 側邊欄風格同步 */
    section[data-testid="stSidebar"] {{
        background-color: var(--bg-color) !important;
        filter: brightness(0.95);
        border-right: 1px solid var(--border-color) !important;
    }}
    
    /* 自訂雙線條 */
    hr {{
        border: none !important;
        border-top: var(--hr-style) !important;
        opacity: 1 !important;
        margin: 0.5rem 0 1.5rem 0 !important;
    }}

    /* Streamlit 按鈕風格 */
    div.stButton > button {{
        font-family: var(--font-header) !important;
        font-weight: 700 !important;
        background-color: var(--card-bg) !important;
        color: var(--text-color) !important;
        border: 2px solid var(--border-color) !important;
        padding: 8px 16px !important;
        border-radius: var(--radius) !important;
        transition: all 0.1s ease !important;
        box-shadow: var(--box-shadow) !important;
    }}
    div.stButton > button:hover {{
        background-color: var(--text-color) !important;
        color: var(--bg-color) !important;
        border: 2px solid var(--text-color) !important;
    }}

    /* Streamlit 輸入框與選單風格 */
    div[data-testid="stTextInput"] input, div[data-testid="stSelectbox"] select, div[data-testid="stSelectbox"] div[role="button"] {{
        border-radius: var(--radius) !important;
        border: 1px solid var(--border-color) !important;
        background-color: var(--card-bg) !important;
        color: var(--text-color) !important;
        font-family: var(--font-body) !important;
    }}
    div[data-baseweb="select"] {{
        border-radius: var(--radius) !important;
        border: 1px solid var(--border-color) !important;
        background-color: var(--card-bg) !important;
    }}

    /* 公告捲動容器與項目 */
    .announcement-container {{
        max-height: 380px !important;
        overflow-y: auto !important;
        border: var(--border-style) !important;
        border-radius: var(--radius) !important;
        padding: 12px !important;
        background-color: transparent !important;
        margin-bottom: 20px !important;
    }}
    .announcement-card {{
        padding: 15px !important;
        margin-bottom: 12px !important;
        border: var(--border-style) !important;
        border-radius: var(--radius) !important;
        background-color: var(--card-bg) !important;
        box-shadow: var(--box-shadow) !important;
        font-family: var(--font-body) !important;
        font-size: 0.95rem !important;
        line-height: 1.6 !important;
    }}
    .announcement-card:last-child {{
        margin-bottom: 0px !important;
    }}
    .announcement-card.urgent {{
        background-color: var(--alert-bg) !important;
        color: var(--alert-border) !important;
        border: 2px solid var(--alert-border) !important;
    }}
    .announcement-card.normal {{
        background-color: var(--card-bg) !important;
        color: var(--text-color) !important;
    }}
    .announcement-header {{
        font-family: var(--font-header) !important;
        font-weight: bold !important;
        font-size: 1.05rem !important;
        margin-bottom: 8px !important;
        border-bottom: 1px dashed var(--border-color);
        padding-bottom: 4px;
    }}
    .announcement-card.urgent .announcement-header {{
        border-bottom: 1px dashed var(--alert-border) !important;
    }}

    /* 報紙表格樣式 */
    .news-table-container {{
        max-height: 320px !important;
        overflow-y: auto !important;
        border: var(--border-style) !important;
        border-radius: var(--radius) !important;
        margin-bottom: 20px !important;
    }}
    .news-table {{
        width: 100% !important;
        border-collapse: collapse !important;
        font-family: var(--font-body) !important;
        font-size: 0.95rem !important;
    }}
    .news-table th {{
        background-color: var(--bg-color) !important;
        filter: brightness(0.95);
        color: var(--text-color) !important;
        border-bottom: 2px solid var(--border-color) !important;
        padding: 10px !important;
        font-family: var(--font-header) !important;
        font-weight: 700 !important;
        text-align: left !important;
        position: sticky !important;
        top: 0 !important;
        z-index: 10 !important;
    }}
    .news-table td {{
        padding: 10px !important;
        border-bottom: 1px solid var(--border-color) !important;
        color: var(--text-color);
    }}
    .news-table tr:last-child td {{
        border-bottom: none !important;
    }}
    .news-table tbody tr:hover {{
        background-color: var(--card-bg) !important;
        filter: brightness(0.98);
    }}

    /* 自訂捲動軸樣式 */
    ::-webkit-scrollbar {{
        width: 8px !important;
        height: 8px !important;
    }}
    ::-webkit-scrollbar-track {{
        background: var(--bg-color) !important;
    }}
    ::-webkit-scrollbar-thumb {{
        background: var(--scrollbar-thumb) !important;
        border-radius: var(--radius) !important;
    }}
    ::-webkit-scrollbar-thumb:hover {{
        opacity: 0.8;
    }}

    /* 顏色與字體特規樣式 */
    .text-blue {{
        color: #0000AA !important;
    }}
    .text-green {{
        color: #00AA00 !important;
    }}
    .text-red {{
        color: #CC0000 !important;
    }}
    /* 暗色模式下調整顏色以增強可讀性 */
    .stApp[style*="--bg-color: #0F172A"] .text-blue {{
        color: #38BDF8 !important;
    }}
    .stApp[style*="--bg-color: #0F172A"] .text-green {{
        color: #34D399 !important;
    }}
    .stApp[style*="--bg-color: #0F172A"] .text-red {{
        color: #F87171 !important;
    }}

    .font-bold {{
        font-weight: bold !important;
    }}

    /* 回到最上方按鈕 */
    .back-to-top-btn img {{
        width: 50px;
        height: 50px;
        cursor: pointer;
        border: 2px solid var(--border-color);
        background-color: var(--card-bg);
        padding: 5px;
        transition: all 0.1s ease;
        box-shadow: var(--box-shadow);
        border-radius: var(--radius);
    }}
    .back-to-top-btn img:hover {{
        transform: scale(1.1);
        background-color: var(--text-color);
        border-color: var(--text-color);
        filter: invert(1) !important;
    }}

    /* 資料更新按鈕 */
    .refresh-btn img {{
        width: 50px;
        height: 50px;
        cursor: pointer;
        border: 2px solid var(--border-color);
        background-color: var(--card-bg);
        padding: 4px;
        transition: all 0.1s ease;
        box-shadow: var(--box-shadow);
        border-radius: var(--radius);
    }}
    .refresh-btn img:hover {{
        transform: scale(1.1);
        background-color: var(--text-color);
        border-color: var(--text-color);
        filter: invert(1) !important;
    }}

    /* SAC Components 樣式對齊 */
    .ant-segmented {{
        background-color: var(--card-bg) !important;
        color: var(--text-color) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: var(--radius) !important;
    }}
    .ant-segmented-item-selected {{
        background-color: var(--text-color) !important;
        color: var(--bg-color) !important;
        border-radius: var(--radius) !important;
    }}
    
    /* Streamlit 摺疊面板樣式調整 */
    .streamlit-expanderHeader {{
        background-color: var(--card-bg) !important;
        color: var(--text-color) !important;
        border: var(--border-style) !important;
        border-radius: var(--radius) !important;
        font-family: var(--font-header) !important;
    }}
    .streamlit-expanderContent {{
        background-color: var(--card-bg) !important;
        color: var(--text-color) !important;
        border: var(--border-style) !important;
        border-top: none !important;
        border-radius: 0 0 var(--radius) var(--radius) !important;
    }}
</style>
""", unsafe_allow_html=True)

# ----------------- Time-based Auto-Refresh -----------------
# Trigger refresh every 60 seconds
count = st_autorefresh(interval=60000, key="dashboard_refresher")

# ----------------- Manual Refresh Query Param Handler -----------------
if "refresh" in st.query_params:
    st.query_params.clear()
    try:
        fetch_weather.clear()
        fetch_taipei_gov_announcements.clear()
        fetch_youbike_data.clear()
        fetch_bus_arrivals.clear()
        google_geocode_or_search.clear()
        fetch_google_place_details.clear()
    except Exception:
        pass
    st.rerun()

# ----------------- Global Memory Cache Helper Functions -----------------

def get_district_from_coords(lat, lng, loc_name=""):
    if "南港" in loc_name:
        return "南港區"
    if "101" in loc_name or "信義" in loc_name:
        return "信義區"
    if "港墘" in loc_name or "內湖" in loc_name or "石潭" in loc_name or "統一" in loc_name:
        return "內湖區"
    if "台北車站" in loc_name or "中正" in loc_name:
        return "中正區"
        
    districts = {
        "內湖區": (25.0688, 121.5909),
        "南港區": (25.0433, 121.6186),
        "信義區": (25.0302, 121.5678),
        "中正區": (25.0421, 121.5198),
        "大安區": (25.0264, 121.5434),
        "中山區": (25.0685, 121.5433),
        "松山區": (25.0562, 121.5644),
        "萬華區": (25.0268, 121.4962),
        "士林區": (25.0922, 121.5245),
        "北投區": (25.1321, 121.5011),
        "大同區": (25.0645, 121.5133),
        "文山區": (24.9881, 121.5701)
    }
    
    min_dist = 999999.0
    guessed_district = "內湖區"
    for name, coords in districts.items():
        d = haversine_distance(lat, lng, coords[0], coords[1])
        if d < min_dist:
            min_dist = d
            guessed_district = name
    return guessed_district

# 1. Weather Data (TTL = 30 mins)
@st.cache_data(ttl=1800)
def fetch_weather(district_name):
    api_key = os.getenv("CWA_API_KEY")
    if not api_key:
        raise ValueError("缺少中央氣象署 API 金鑰 (CWA_API_KEY)")
        
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-D0047-061"
    params = {
        "Authorization": api_key,
        "locationName": district_name
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
        
    all_stations = []
    for item in data:
        sna = item.get("sna", "")
        # Remove YouBike2.0_ prefix for display
        clean_name = sna.replace("YouBike2.0_", "")
        
        sbi = item.get("available_rent_bikes") if item.get("available_rent_bikes") is not None else item.get("sbi", 0)
        bemp = item.get("available_return_bikes") if item.get("available_return_bikes") is not None else item.get("bemp", 0)
        update_time = item.get("updateTime") or item.get("mday") or "N/A"
        lat = item.get("latitude")
        lng = item.get("longitude")
        
        all_stations.append({
            "sna": clean_name,
            "sbi": sbi,
            "bemp": bemp,
            "update_time": update_time,
            "lat": float(lat) if lat is not None else None,
            "lng": float(lng) if lng is not None else None
        })
        
    return all_stations

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
            for s in stops_json["BusInfo"]:
                stops_dict[int(s["Id"])] = {
                    "nameZh": s["nameZh"],
                    "routeId": int(s["routeId"]),
                    "goBack": int(s["goBack"]),
                    "lat": float(s["latitude"]) if s.get("latitude") is not None else None,
                    "lng": float(s["longitude"]) if s.get("longitude") is not None else None
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
def fetch_bus_arrivals(target_stop_ids_tuple):
    stops_dict, routes_dict = fetch_bus_static_data()
    estimates_url = "https://tcgbusfs.blob.core.windows.net/blobbus/GetEstimateTime.gz"
    
    target_stop_ids = set(target_stop_ids_tuple)
    
    with httpx.Client(verify=False, timeout=3.0) as client:
        r = client.get(estimates_url)
        if r.status_code != 200:
            raise RuntimeError(f"無法取得公車動態資料 ({r.status_code})")
            
        estimates_json = json.loads(gzip.decompress(r.content).decode('utf-8'))
        
        arrivals = []
        for est in estimates_json["BusInfo"]:
            stop_id = int(est["StopID"])
            if stop_id in target_stop_ids and stop_id in stops_dict:
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

# Predefined landmark coordinates for quick selection
predefined_landmarks = {
    "統一數位大樓 (內湖石潭路155號)": (25.059727, 121.589632),
    "捷運昆陽站": (25.050227, 121.593327),
    "捷運港墘站": (25.079800, 121.575100),
    "內湖好市多": (25.061700, 121.579600),
    "台北車站": (25.047800, 121.517000),
    "南港車站": (25.052187, 121.606775),
    "台北101 / 信義商圈": (25.033976, 121.564539),
    "內科園區 (湖濱路)": (25.075000, 121.583000),
}

# Coordinate State Setup
if "user_lat" not in st.session_state:
    st.session_state["user_lat"] = 25.059727
if "user_lng" not in st.session_state:
    st.session_state["user_lng"] = 121.589632
if "loc_name" not in st.session_state:
    st.session_state["loc_name"] = "統一數位大樓 (內湖石潭路155號)"

current_lat = st.session_state["user_lat"]
current_lng = st.session_state["user_lng"]
current_loc_name = st.session_state["loc_name"]

# Geopositioning helpers
district_name = get_district_from_coords(current_lat, current_lng, current_loc_name)

# Cache Warnings Helper
warning_messages = []

# Fetch All Data Streams with Defensive Fallbacks
# 1. Weather
try:
    weather = fetch_weather(district_name)
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
    all_youbike_stations = fetch_youbike_data()
    youbike_list = []
    for yb in all_youbike_stations:
        if yb["lat"] is not None and yb["lng"] is not None:
            dist = haversine_distance(current_lat, current_lng, yb["lat"], yb["lng"])
            yb["distance_meter"] = int(dist)
            youbike_list.append(yb)
            
    # Sort by distance
    youbike_list.sort(key=lambda x: x["distance_meter"])
    youbike_list = youbike_list[:3]
except Exception as e:
    youbike_list = get_mock_youbike_data()
    for idx, item in enumerate(youbike_list):
        item["distance_meter"] = (idx + 1) * 120
    warning_messages.append(f"YouBike 即時資料更新失敗，目前顯示暫存資訊 (錯誤訊息：{e})")

# 4. Bus Dynamics
try:
    stops_dict, routes_dict = fetch_bus_static_data()
    
    # Find nearest 5 unique stop names
    unique_stops_with_distance = []
    seen_stop_names = set()
    for s_id, s_info in stops_dict.items():
        if s_info["lat"] is not None and s_info["lng"] is not None:
            dist = haversine_distance(current_lat, current_lng, s_info["lat"], s_info["lng"])
            name = s_info["nameZh"]
            if name not in seen_stop_names:
                unique_stops_with_distance.append((name, dist))
                seen_stop_names.add(name)
                
    unique_stops_with_distance.sort(key=lambda x: x[1])
    closest_stop_names = [x[0] for x in unique_stops_with_distance[:5]]
    
    # Collect StopIDs for these stop names
    target_stop_ids = []
    for s_id, s_info in stops_dict.items():
        if s_info["nameZh"] in closest_stop_names:
            target_stop_ids.append(s_id)
            
    bus_list = fetch_bus_arrivals(tuple(target_stop_ids))
    
    stop_distance_map = {}
    for name, dist in unique_stops_with_distance:
        stop_distance_map[name] = int(dist)
        
    for bus in bus_list:
        bus["distance_meter"] = stop_distance_map.get(bus["stop"], 999)
        
    bus_list.sort(key=lambda x: (x["distance_meter"], x["route"]))
except Exception as e:
    bus_list = get_mock_bus_arrivals()
    for item in bus_list:
        item["distance_meter"] = 180
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
    st.markdown("<h1 style='margin:0;'>統一數位大樓生活資訊平台<span class='title-subtitle'>(LIFE DASHBOARD)</span></h1>", unsafe_allow_html=True)
with col_header_right:
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.markdown(strip_html(f"""
    <div style="text-align: right; font-family: 'Inter', sans-serif; font-size: 0.9rem; color: #555555; line-height: 1.6; margin-top: 8px; margin-bottom: 8px;">
        <b>系統時間</b>：{now_str}<br/>
        ⏱️ 網頁每 60 秒自動重新載入 ({count})
    </div>
    <div style="text-align: right; margin-top: 6px;">
        <a href="?refresh=1" target="_self" class="refresh-btn">
            <img src="data:image/png;base64,{update_btn_base64}" alt="資料更新" />
        </a>
    </div>
    """), unsafe_allow_html=True)

st.markdown("---")

# ----------------- Positioning System UI -----------------
st.subheader("📍 平台中心定位設定")
col_pos_mode, col_pos_val = st.columns([1, 2])

with col_pos_mode:
    pos_mode = sac.segmented(
        items=[
            sac.SegmentedItem(label="📍 常用地標", icon="geo-alt"),
            sac.SegmentedItem(label="🔍 地址搜尋", icon="search"),
            sac.SegmentedItem(label="🛰️ GPS 定位", icon="radar")
        ],
        align="left",
        color="dark",
        size="sm",
        key="pos_mode_selector"
    )

with col_pos_val:
    if pos_mode == "📍 常用地標":
        landmark_list = list(predefined_landmarks.keys())
        default_idx = 0
        if st.session_state["loc_name"] in landmark_list:
            default_idx = landmark_list.index(st.session_state["loc_name"])
        selected_landmark = st.selectbox("請選擇地標作為定位點", landmark_list, index=default_idx)
        if selected_landmark and selected_landmark != st.session_state["loc_name"]:
            st.session_state["user_lat"], st.session_state["user_lng"] = predefined_landmarks[selected_landmark]
            st.session_state["loc_name"] = selected_landmark
            st.rerun()
            
    elif pos_mode == "🔍 地址搜尋":
        col_search_input, col_search_btn = st.columns([3, 1])
        with col_search_input:
            search_query = st.text_input("輸入地址或地名 (例如: 內湖大潤發)", value="", placeholder="輸入地標...", key="addr_search_query")
        with col_search_btn:
            st.write("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            run_search = st.button("搜尋", key="run_search_btn")
            
        if run_search and search_query:
            coords = google_geocode_or_search(search_query)
            if coords:
                st.session_state["user_lat"], st.session_state["user_lng"] = coords
                st.session_state["loc_name"] = f"搜尋: {search_query}"
                st.rerun()
            else:
                st.error("找不到該位置，請確認拼字或改用其他關鍵字。")
                
    elif pos_mode == "🛰️ GPS 定位":
        st.write("📡 正在向瀏覽器要求 GPS 權限...")
        loc_data = get_geolocation()
        if loc_data:
            if 'error' in loc_data:
                st.warning(f"無法取得 GPS 定位：{loc_data['error'].get('message', '未知錯誤')}")
            else:
                lat_gps = loc_data['coords']['latitude']
                lng_gps = loc_data['coords']['longitude']
                if abs(st.session_state["user_lat"] - lat_gps) > 0.0001 or abs(st.session_state["user_lng"] - lng_gps) > 0.0001:
                    st.session_state["user_lat"] = lat_gps
                    st.session_state["user_lng"] = lng_gps
                    st.session_state["loc_name"] = "瀏覽器 GPS 定位"
                    st.rerun()
        else:
            st.info("請在瀏覽器彈出視窗中允許位置存取權限。")

st.markdown(f"**目前中心定位點**：{st.session_state['loc_name']} `({st.session_state['user_lat']:.6f}, {st.session_state['user_lng']:.6f})`")
st.markdown("---")

# Parse temperature and precipitation values for visual threshold highlighting
temp_class = ""
apparent_temp_class = ""
pop_class = ""
if weather:
    def parse_temp_num(t_str):
        try:
            clean_str = "".join(c for c in str(t_str) if c.isdigit() or c in ['.', '-'])
            return float(clean_str) if clean_str else None
        except Exception:
            return None

    def get_temp_class(val):
        if val is None:
            return ""
        if val >= 30:
            return "text-red"
        elif val < 20:
            return "text-blue"
        else:
            return "text-green"

    temp_val = parse_temp_num(weather.get('temp'))
    apparent_temp_val = parse_temp_num(weather.get('apparent_temp'))
    pop_val = parse_temp_num(weather.get('pop'))
    
    temp_class = get_temp_class(temp_val)
    apparent_temp_class = get_temp_class(apparent_temp_val)
    
    if pop_val is not None:
        pop_class = "text-blue" if pop_val <= 30 else "text-red"

# Today's Weather Section
st.subheader(f"☀️ 今日即時天氣 ({district_name})")
st.markdown(strip_html(f"""
<div class="weather-card">
    <div class="weather-title">定位點：{st.session_state['loc_name']}</div>
    <div class="weather-temp {temp_class}">{weather['temp']}</div>
    <div class="weather-details">
        <b>天氣現象</b>：{weather['desc']}<br/>
        <b>體感溫度</b>：<span class="{apparent_temp_class}">{weather['apparent_temp']}</span><br/>
        <b>降雨機率</b>：<span class="{pop_class}">{weather['pop']}</span><br/>
        <small style="opacity: 0.8;">更新時間：{weather['time']}</small>
    </div>
</div>
"""), unsafe_allow_html=True)

# Announcements Section (with Scrollbar)
st.subheader("📢 最新公告")
if all_news:
    ann_cards_html = []
    for news in all_news:
        card_class = "urgent" if news["is_urgent"] else "normal"
        title_prefix = "🚨【緊急】" if news["is_urgent"] else "📌"
        card_html = strip_html(f"""
        <div class="announcement-card {card_class}">
            <div class="announcement-header">{title_prefix} {news['title']}</div>
            <div style="font-size: 0.8rem; color: #555555; margin-bottom: 8px;">來源：{news['source']} | 發布時間：{news['created_at']}</div>
            <div>{news['content']}</div>
        </div>
        """)
        ann_cards_html.append(card_html)
    
    st.markdown(strip_html(f"""
    <div class="announcement-container">
        {"".join(ann_cards_html)}
    </div>
    """), unsafe_allow_html=True)
else:
    st.write("目前無任何公告")

# YouBike Section
st.subheader(f"🚲 YouBike 2.0 即時站點看板（距 {st.session_state['loc_name'][:10]}... 最近）")
if youbike_list:
    cols_yb = st.columns(min(len(youbike_list), 3))
    for idx, yb in enumerate(youbike_list[:3]):
        with cols_yb[idx]:
            sbi_val = int(yb['sbi']) if yb['sbi'] is not None else 0
            bemp_val = int(yb['bemp']) if yb['bemp'] is not None else 0
            sbi_color_class = "text-red" if sbi_val <= 2 else "text-blue"
            bemp_color_class = "text-red" if bemp_val <= 2 else "text-green"
            dist_m = yb.get('distance_meter', '?')
            dist_label = f"{dist_m} 公尺" if isinstance(dist_m, int) else "N/A"
            st.markdown(strip_html(f"""
            <div class="metric-card">
                <div style="font-weight: bold; font-size: 0.95rem; color: var(--text-color); font-family: var(--font-header); border-bottom: 1px dashed var(--border-color); padding-bottom: 5px; margin-bottom: 8px;">{yb['sna']}</div>
                <div style="font-size: 0.75rem; color: var(--accent-color); margin-bottom: 8px;">📍 距離中心點約 {dist_label}</div>
                <div style="display: flex; justify-content: space-between; margin-top: 10px;">
                    <div>
                        <span class="metric-label">可借車</span><br/>
                        <span class="metric-value {sbi_color_class}">{yb['sbi']}</span>
                    </div>
                    <div>
                        <span class="metric-label">可還車</span><br/>
                        <span class="metric-value {bemp_color_class}">{yb['bemp']}</span>
                    </div>
                </div>
                <div style="font-size: 0.75rem; color: var(--text-color); opacity: 0.6; margin-top: 8px;">更新：{yb['update_time']}</div>
            </div>
            """), unsafe_allow_html=True)
else:
    st.write("目前無鄰近 YouBike 2.0 站點資料")

# Bus Arrivals Section (with Scrollbar)
st.subheader(f"🚌 大台北公車即時到站動態（鄰近 {st.session_state['loc_name'][:10]}... 站牌）")
if bus_list:
    # 排序：先依預估到站時間（raw_time）最小排序，負值（末班車/尚未發車等）排最後，再依路線編號排序
    def bus_sort_key(b):
        rt = b.get('raw_time', 99999)
        # 負值代表特殊狀態（尚未發車/末班車已過等），排到最後
        sort_time = rt if rt >= 0 else (99999 + abs(rt))
        try:
            route_num = int("".join(filter(str.isdigit, str(b['route']))) or "99999")
        except Exception:
            route_num = 99999
        return (sort_time, route_num)

    sorted_bus_list = sorted(bus_list, key=bus_sort_key)

    bus_rows_html = []
    for bus in sorted_bus_list:
        # 去程 → #0000AA；返程 → #00AA00
        row_color = "#0000AA" if bus['go_back'] == "去程" else "#00AA00"

        # 預估到站時間 ≤ 2 分鐘（120秒）或「即將到站」→ #CC0000
        is_near = (0 <= bus.get('raw_time', 9999) <= 120) or (bus['desc'] == "即將到站")
        time_color = "#CC0000" if is_near else row_color

        dist_m = bus.get('distance_meter', '')
        dist_label = f"{dist_m}m" if isinstance(dist_m, int) else ""

        row_html = strip_html(f"""
        <tr>
            <td style="color:{row_color}; font-weight:bold;">{bus['route']}</td>
            <td style="color:{row_color};">{bus['stop']}<br/><small style="opacity:0.65;">{dist_label}</small></td>
            <td style="color:{row_color};">{bus['go_back']}</td>
            <td style="color:{time_color}; {'font-weight:bold;' if is_near else ''}">{bus['desc']}</td>
        </tr>
        """)
        bus_rows_html.append(row_html)

    st.markdown(strip_html(f"""
    <div class="news-table-container">
        <table class="news-table">
            <thead>
                <tr>
                    <th>路線</th>
                    <th>站牌名稱</th>
                    <th>去返程</th>
                    <th>預估到站時間</th>
                </tr>
            </thead>
            <tbody>
                {"".join(bus_rows_html)}
            </tbody>
        </table>
    </div>
    """), unsafe_allow_html=True)
else:
    st.write("目前無公車到站資訊")

st.markdown("---")

# Row 3: Lunch Recommendations (Full Width)
st.subheader("🍲 周邊午餐推薦 Top 10（含 Google Places 評論）")

has_places_key = bool(os.getenv("GOOGLE_PLACES_API_KEY"))
if not has_places_key:
    st.info("💡 若設定 `.env` 中的 `GOOGLE_PLACES_API_KEY`，展開餐廳可查看 Google 即時評論與營業時間。")

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
    results = query_res.order_by(Restaurant.google_rating.desc(), Restaurant.review_count.desc()).limit(10).all()
else:
    results = query_res.order_by(Restaurant.distance_meter.asc()).limit(10).all()

if results:
    for rank, r in enumerate(results, 1):
        price_str = "¥" * r.price_level
        expander_label = f"{'🥇' if rank==1 else '🥈' if rank==2 else '🥉' if rank==3 else f'#{rank}'}  {r.name}  |  ⭐ {r.google_rating}  |  {r.category}  |  {price_str}  |  📍 {r.distance_meter} 公尺"
        with st.expander(expander_label, expanded=False):
            # Fetch Google Places details
            with st.spinner(f"正在查詢 {r.name} 的 Google Places 資料..."):
                place_details = fetch_google_place_details(r.name, current_lat, current_lng)
            
            c1, c2 = st.columns([1, 2])
            with c1:
                if place_details["open_now"] is True:
                    st.markdown("🟢 **目前營業中**")
                elif place_details["open_now"] is False:
                    st.markdown("🔴 **目前休息中**")
                else:
                    st.markdown("⚪ 營業狀態未知")
                st.markdown(f"**Google 評分**: ⭐ {place_details['rating']} / 5")
                st.markdown(f"**餐廳類型**: {r.category}  |  **價位**: {price_str}")
                st.markdown(f"**評論數**: {r.review_count} 則")
                st.markdown(f"**距離中心點**: 約 {r.distance_meter} 公尺")
                if place_details.get("is_mock"):
                    st.caption("⚠️ 以下為模擬資料（需設定 Google Places API 金鑰以取得即時資訊）")
                maps_url = f"https://www.google.com/maps/search/{r.name.replace(' ', '+')}+台北"
                st.markdown(f"[🗺️ 在 Google Maps 上開啟]({maps_url})")
                
            with c2:
                if place_details["weekday_text"]:
                    with st.expander("📅 每週營業時間", expanded=False):
                        for day_info in place_details["weekday_text"]:
                            st.caption(day_info)
                
                if place_details["reviews"]:
                    st.markdown("**💬 最新顧客評論**")
                    for rev in place_details["reviews"]:
                        stars = "⭐" * int(rev.get("rating", 5))
                        st.markdown(strip_html(f"""
                        <div style="border-left: 3px solid var(--accent-color); padding: 8px 12px; margin-bottom: 10px; background-color: var(--card-bg); border-radius: 0 var(--radius) var(--radius) 0;">
                            <div style="font-size: 0.85rem; font-weight: bold;">{rev['author']} {stars} <span style="opacity:0.6; font-weight:normal;">{rev['time']}</span></div>
                            <div style="font-size: 0.88rem; margin-top: 4px; line-height: 1.5;">{rev['text']}</div>
                        </div>
                        """), unsafe_allow_html=True)
                else:
                    st.caption("暫無評論資料")
else:
    st.write("無符合篩選條件的餐廳")

st.markdown("---")

# Row 4: 周邊地圖 Map Section (Full Width)
st.subheader("🗺️ 周邊生活機能地圖")
# Embedded Google Maps iframe for 台北市內湖區石潭路155號
iframe_src = "https://maps.google.com/maps?q=%E5%8F%B0%E5%8C%97%E5%B8%82%E5%85%A7%E6%B9%96%E5%8D%80%E7%9F%B3%E6%BD%AD%E8%B7%AF155%E8%99%9F&t=&z=16&ie=UTF8&iwloc=&output=embed"
st.components.v1.html(
    f'<iframe width="100%" height="450" frameborder="0" style="border:0;" src="{iframe_src}" allowfullscreen></iframe>',
    height=460
)

# Footer Section
today_str = datetime.date.today().strftime("%Y-%m-%d")
st.markdown(strip_html(f"""
<div style="border-top: 3px double #111111; padding-top: 20px; margin-top: 40px; padding-bottom: 20px; text-align: center; font-family: 'Inter', sans-serif; font-size: 0.85rem; color: #555555; line-height: 1.6;">
    <div>© 2026 統一數位大樓生活資訊平台 (Life Dashboard) 版權所有</div>
    <div>版本資訊：v1.2.0 | 更新日期：{today_str}</div>
    <div style="margin-top: 6px; font-family: 'Fraunces', Georgia, serif; font-weight: 900; color: #111111; font-size: 0.95rem;">Powered with Gemini & Antigravity 2.0 By James wu</div>
    <div style="margin-top: 10px;">
        <a href="https://www.linkedin.com/in/james-wenkaiwu/" target="_blank" style="color: #111111; text-decoration: underline; margin-right: 15px; font-weight: bold;">LinkedIn</a>
        <a href="https://github.com/rowjk" target="_blank" style="color: #111111; text-decoration: underline; font-weight: bold;">GitHub</a>
    </div>
</div>
"""), unsafe_allow_html=True)

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

# Back to Top floating button
if back_to_top_base64:
    st.markdown(strip_html(f"""
    <div style="position: fixed; bottom: 30px; right: 30px; z-index: 99999;">
        <a href="#linkto_top" target="_self" class="back-to-top-btn">
            <img src="data:image/png;base64,{back_to_top_base64}" alt="Back to Top" />
        </a>
    </div>
    """), unsafe_allow_html=True)
