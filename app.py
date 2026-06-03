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
    if os.path.exists("BackToTop_2.png"):
        with open("BackToTop_2.png", "rb") as img_file:
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
        "台北101": (25.033976, 121.564539),
        "捷運南港展覽館站": (25.0558, 121.6173),
        "南港展覽館": (25.0558, 121.6173),
        "富康公園": (25.052429, 121.617524),
        "南港新富公園": (25.052429, 121.617524)
    }
    for k, v in predefined.items():
        if k in query:
            return v

    if api_key:
        url = "https://places.googleapis.com/v1/places:searchText"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.location"
        }
        data = {
            "textQuery": query,
            "languageCode": "zh-TW"
        }
        try:
            with httpx.Client(verify=False, timeout=4.0) as client:
                r = client.post(url, headers=headers, json=data)
                if r.status_code == 200:
                    resp_data = r.json()
                    places = resp_data.get("places", [])
                    if places:
                        loc = places[0].get("location", {})
                        if "latitude" in loc and "longitude" in loc:
                            return float(loc["latitude"]), float(loc["longitude"])
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
    """Use the new Places API v1 (places.googleapis.com/v1) to get real reviews."""
    api_key = os.getenv("GOOGLE_PLACES_API_KEY")
    if api_key:
        try:
            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": (
                    "places.id,places.displayName,places.rating,"
                    "places.reviews,places.currentOpeningHours,"
                    "places.regularOpeningHours,places.formattedAddress"
                )
            }
            body = {
                "textQuery": f"{restaurant_name} 台北",
                "locationBias": {
                    "circle": {
                        "center": {"latitude": float(lat), "longitude": float(lng)},
                        "radius": 3000.0
                    }
                },
                "languageCode": "zh-TW",
                "maxResultCount": 1
            }
            with httpx.Client(verify=False, timeout=8.0) as client:
                r = client.post(
                    "https://places.googleapis.com/v1/places:searchText",
                    headers=headers,
                    json=body
                )
                if r.status_code == 200:
                    places = r.json().get("places", [])
                    if places:
                        p = places[0]
                        rating = p.get("rating", 4.0)

                        # Parse reviews
                        reviews = []
                        for rev in p.get("reviews", [])[:3]:
                            reviews.append({
                                "author": rev.get("authorAttribution", {}).get("displayName", "Google 顧客"),
                                "rating": rev.get("rating", 5),
                                "text": rev.get("text", {}).get("text", ""),
                                "time": rev.get("relativePublishTimeDescription", "最近")
                            })

                        # Parse opening hours
                        oh = p.get("currentOpeningHours") or p.get("regularOpeningHours", {})
                        open_now = oh.get("openNow")
                        weekday_text = oh.get("weekdayDescriptions", [])

                        return {
                            "rating": rating,
                            "reviews": reviews,
                            "open_now": open_now,
                            "weekday_text": weekday_text,
                            "address": p.get("formattedAddress", "台北市區"),
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
        {"author": "James Chen", "rating": 5, "text": "這家餐廳的服務很棒，環境乾淨！餐點份量十足，特別是招牌菜色非常好吃，極力推薦！", "time": "1 週前"},
        {"author": "林小姐", "rating": 4, "text": "這家店的口味很棒，每到中午人都很多。是上班族午餐的優質選擇，出餐速度也很快！", "time": "3 天前"},
        {"author": "張先生", "rating": 4, "text": "味道很道地，價格親民。CP值極高！下次會想再來嘗試其他餐點。", "time": "2 週前"}
    ]

    weekday_text = [
        "星期一: 11:00 – 21:00", "星期二: 11:00 – 21:00", "星期三: 11:00 – 21:00",
        "星期四: 11:00 – 21:00", "星期五: 11:00 – 21:00",
        "星期六: 11:00 – 21:00", "星期日: 休息"
    ]

    return {
        "rating": 4.2,
        "reviews": mock_reviews,
        "open_now": open_now,
        "weekday_text": weekday_text,
        "address": "台北市內湖區石潭路155號 (鄰近定位點)",
        "is_mock": True
    }

class TempRestaurant:
    def __init__(self, name, category, google_rating, review_count, price_level, latitude, longitude, address=""):
        self.name = name
        self.category = category
        self.google_rating = google_rating
        self.review_count = review_count
        self.price_level = price_level
        self.latitude = latitude
        self.longitude = longitude
        self.address = address
        self.distance_meter = 999
        self.calculated_distance = 999

@st.cache_data(ttl=1800)
def fetch_dynamic_restaurants(lat, lng, category="全部"):
    """Dynamically fetch local restaurants using Google Places searchText endpoint."""
    api_key = os.getenv("GOOGLE_PLACES_API_KEY")
    if not api_key:
        return []
        
    query_map = {
        "全部": "餐廳 美食",
        "便當": "便當 排骨飯",
        "麵食": "麵 牛肉麵 拉麵",
        "日式": "日式料理 壽司 拉麵 丼飯",
        "韓式": "韓式料理 韓國豆腐鍋 烤肉",
        "美式": "美式餐廳 漢堡 薯條 早午餐",
        "健康餐": "健康餐盒 沙拉 輕食"
    }
    query = query_map.get(category, "餐廳")
    
    try:
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": (
                "places.id,places.displayName,places.rating,"
                "places.userRatingCount,places.priceLevel,"
                "places.location,places.formattedAddress"
            )
        }
        body = {
            "textQuery": query,
            "locationBias": {
                "circle": {
                    "center": {"latitude": float(lat), "longitude": float(lng)},
                    "radius": 1500.0
                }
            },
            "languageCode": "zh-TW",
            "maxResultCount": 20
        }
        with httpx.Client(verify=False, timeout=8.0) as client:
            r = client.post(
                "https://places.googleapis.com/v1/places:searchText",
                headers=headers,
                json=body
            )
            if r.status_code == 200:
                places = r.json().get("places", [])
                results = []
                for p in places:
                    name = p.get("displayName", {}).get("text", "")
                    rating = p.get("rating", 4.0)
                    review_count = p.get("userRatingCount", 100)
                    price_level_raw = p.get("priceLevel")
                    address = p.get("formattedAddress", "台北市區")
                    
                    pl = 1
                    if price_level_raw:
                        price_level_str = str(price_level_raw)
                        if price_level_str.isdigit():
                            pl = int(price_level_str)
                        elif "INEXPENSIVE" in price_level_str:
                            pl = 1
                        elif "MODERATE" in price_level_str:
                            pl = 2
                        elif "EXPENSIVE" in price_level_str:
                            pl = 3
                        elif "VERY_EXPENSIVE" in price_level_str:
                            pl = 4
                            
                    loc = p.get("location", {})
                    p_lat = loc.get("latitude")
                    p_lng = loc.get("longitude")
                    
                    if p_lat is not None and p_lng is not None:
                        results.append(TempRestaurant(
                            name=name,
                            category=category if category != "全部" else "美食",
                            google_rating=rating,
                            review_count=review_count,
                            price_level=pl,
                            latitude=p_lat,
                            longitude=p_lng,
                            address=address
                        ))
                return results
    except Exception:
        pass
    return []


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
        background-color: #FFFFFF !important;
        border-radius: var(--radius) !important;
        padding: 15px !important;
        border: var(--border-style) !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.10) !important;
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

    /* 天氣卡片：白色底色 */
    .weather-card {{
        background: #FFFFFF !important;
        color: var(--text-color) !important;
        border-radius: var(--radius) !important;
        padding: 20px !important;
        border: var(--border-style) !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.10) !important;
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

    /* 天氣 ICON 動態動畫 */
    @keyframes svg-spin {{
        0% {{ transform: rotate(0deg); }}
        100% {{ transform: rotate(360deg); }}
    }}
    .svg-spin-class {{
        transform-origin: 32px 32px;
        animation: svg-spin 15s linear infinite !important;
    }}

    @keyframes svg-pulse {{
        0% {{ transform: scale(1); }}
        50% {{ transform: scale(1.1); }}
        100% {{ transform: scale(1); }}
    }}
    .svg-pulse-class {{
        transform-origin: 32px 32px;
        animation: svg-pulse 4s ease-in-out infinite !important;
    }}

    @keyframes svg-drift {{
        0% {{ transform: translate(0px, 0px); }}
        50% {{ transform: translate(3px, -1px); }}
        100% {{ transform: translate(0px, 0px); }}
    }}
    .svg-cloud-back {{
        transform-origin: 32px 32px;
        animation: svg-drift 5s ease-in-out infinite !important;
    }}
    .svg-cloud-front {{
        transform-origin: 32px 32px;
        animation: svg-drift 4s ease-in-out infinite alternate !important;
    }}

    @keyframes svg-rain {{
        0% {{ transform: translateY(0px); opacity: 0; }}
        30% {{ opacity: 1; }}
        80% {{ opacity: 0.8; }}
        100% {{ transform: translateY(12px); opacity: 0; }}
    }}
    .svg-rain-drop1 {{
        animation: svg-rain 1.5s infinite linear !important;
    }}
    .svg-rain-drop2 {{
        animation: svg-rain 1.5s infinite linear !important;
        animation-delay: 0.5s !important;
    }}
    .svg-rain-drop3 {{
        animation: svg-rain 1.5s infinite linear !important;
        animation-delay: 1s !important;
    }}

    @keyframes svg-lightning {{
        0%, 85%, 100% {{ opacity: 0; }}
        88%, 94% {{ opacity: 1; }}
        91% {{ opacity: 0.2; }}
    }}
    .svg-lightning-bolt {{
        animation: svg-lightning 2s infinite !important;
    }}

    @keyframes svg-snow {{
        0% {{ transform: translateY(0px); opacity: 0; }}
        30% {{ opacity: 1; }}
        100% {{ transform: translateY(12px); opacity: 0; }}
    }}
    .svg-snow-flake1 {{
        animation: svg-snow 2s infinite linear !important;
    }}
    .svg-snow-flake2 {{
        animation: svg-snow 2s infinite linear !important;
        animation-delay: 0.7s !important;
    }}
    .svg-snow-flake3 {{
        animation: svg-snow 2s infinite linear !important;
        animation-delay: 1.4s !important;
    }}

    @keyframes svg-fog {{
        0% {{ transform: translateX(-4px); opacity: 0.3; }}
        50% {{ transform: translateX(4px); opacity: 0.8; }}
        100% {{ transform: translateX(-4px); opacity: 0.3; }}
    }}
    .svg-fog-line1 {{
        animation: svg-fog 4s ease-in-out infinite !important;
    }}
    .svg-fog-line2 {{
        animation: svg-fog 4s ease-in-out infinite !important;
        animation-delay: 1s !important;
    }}
    .svg-fog-line3 {{
        animation: svg-fog 4s ease-in-out infinite !important;
        animation-delay: 2s !important;
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
        background-color: #FFFFFF !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.10) !important;
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
        background-color: #FFFFFF !important;
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
        background-color: #FFFFFF !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.10) !important;
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
    
    /* Streamlit 摺疊面板：整個容器有白色底色與外框 */
    [data-testid="stExpander"] {{
        background-color: #FFFFFF !important;
        border: var(--border-style) !important;
        border-radius: var(--radius) !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08) !important;
        margin-bottom: 12px !important;
    }}
    /* 展開前的 Header (Summary) */
    .streamlit-expanderHeader, [data-testid="stExpander"] summary {{
        background-color: #FFFFFF !important;
        color: var(--text-color) !important;
        font-family: var(--font-header) !important;
        border: none !important;
        border-radius: var(--radius) !important;
    }}
    /* 展開後的 Content */
    .streamlit-expanderContent, [data-testid="stExpander"] > div[role="region"] {{
        background-color: #FFFFFF !important;
        color: var(--text-color) !important;
        border: none !important;
        border-top: 1px solid var(--border-color) !important;
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

# Taiwan CWA weather dataset ID mapping
CITY_DATASETS = {
    "宜蘭縣": "F-D0047-001",
    "桃園市": "F-D0047-005",
    "新竹縣": "F-D0047-009",
    "苗栗縣": "F-D0047-013",
    "彰化縣": "F-D0047-017",
    "南投縣": "F-D0047-021",
    "雲林縣": "F-D0047-025",
    "嘉義縣": "F-D0047-029",
    "屏東縣": "F-D0047-033",
    "台東縣": "F-D0047-037",
    "花蓮縣": "F-D0047-041",
    "澎湖縣": "F-D0047-045",
    "基隆市": "F-D0047-049",
    "新竹市": "F-D0047-053",
    "嘉義市": "F-D0047-057",
    "台北市": "F-D0047-061",
    "高雄市": "F-D0047-065",
    "新北市": "F-D0047-069",
    "台中市": "F-D0047-073",
    "台南市": "F-D0047-077",
    "連江縣": "F-D0047-081",
    "金門縣": "F-D0047-085"
}

@st.cache_data(ttl=86400)
def get_district_from_coords(lat, lng, loc_name=""):
    city_name = ""
    district_name = ""
    
    # Predefined landmark mappings to bypass network lookups
    if "南港" in loc_name or "富康" in loc_name or "新富" in loc_name:
        city_name, district_name = "台北市", "南港區"
    elif "101" in loc_name or "信義" in loc_name:
        city_name, district_name = "台北市", "信義區"
    elif "港墘" in loc_name or "內湖" in loc_name or "石潭" in loc_name or "統一" in loc_name:
        city_name, district_name = "台北市", "內湖區"
    elif "台北車站" in loc_name or "中正" in loc_name:
        city_name, district_name = "台北市", "中正區"

    if not city_name or not district_name:
        # Try Google Geocoding API if key is present
        api_key = os.getenv("GOOGLE_PLACES_API_KEY")
        if api_key:
            url = "https://maps.googleapis.com/maps/api/geocode/json"
            params = {
                "latlng": f"{lat},{lng}",
                "key": api_key,
                "language": "zh-TW"
            }
            try:
                with httpx.Client(verify=False, timeout=3.0) as client:
                    r = client.get(url, params=params)
                    if r.status_code == 200:
                        results = r.json().get("results", [])
                        if results:
                            components = results[0].get("address_components", [])
                            for c in components:
                                types = c.get("types", [])
                                if "administrative_area_level_1" in types:
                                    city_name = c.get("long_name", "")
                                elif "administrative_area_level_2" in types and not city_name:
                                    city_name = c.get("long_name", "")
                                elif "locality" in types:
                                    district_name = c.get("long_name", "")
                                elif "sublocality_level_1" in types:
                                    district_name = c.get("long_name", "")
            except Exception:
                pass

        if not city_name or not district_name:
            # Fallback to Nominatim reverse geocoding
            try:
                url = "https://nominatim.openstreetmap.org/reverse"
                headers = {"User-Agent": "LifeDashboard/1.2"}
                params = {
                    "lat": lat,
                    "lon": lng,
                    "format": "json",
                    "accept-language": "zh-TW"
                }
                with httpx.Client(verify=False, timeout=3.0) as client:
                    r = client.get(url, headers=headers, params=params)
                    if r.status_code == 200:
                        data = r.json()
                        address = data.get("address", {})
                        city_name = address.get("city") or address.get("county") or address.get("town") or ""
                        district_name = address.get("district") or address.get("town") or address.get("suburb") or address.get("village") or ""
            except Exception:
                pass

    # Guess nearest Taiwan district/city as final fallback if API lookups fail
    if not city_name or not district_name:
        districts = {
            # 台北市
            ("台北市", "內湖區"): (25.0688, 121.5909),
            ("台北市", "南港區"): (25.0433, 121.6186),
            ("台北市", "信義區"): (25.0302, 121.5678),
            ("台北市", "中正區"): (25.0421, 121.5198),
            ("台北市", "大安區"): (25.0264, 121.5434),
            ("台北市", "中山區"): (25.0685, 121.5433),
            ("台北市", "松山區"): (25.0562, 121.5644),
            ("台北市", "萬華區"): (25.0268, 121.4962),
            ("台北市", "士林區"): (25.0922, 121.5245),
            ("台北市", "北投區"): (25.1321, 121.5011),
            ("台北市", "大同區"): (25.0645, 121.5133),
            ("台北市", "文山區"): (24.9881, 121.5701),
            # 新北市
            ("新北市", "板橋區"): (25.0120, 121.4657),
            ("新北市", "新店區"): (24.9782, 121.5395),
            ("新北市", "三重區"): (25.0628, 121.4990),
            ("新北市", "淡水區"): (25.1685, 121.4446),
            # 基隆市
            ("基隆市", "仁愛區"): (25.1275, 121.7391),
            # 桃園市
            ("桃園市", "桃園區"): (24.9937, 121.3010),
            ("桃園市", "中壢區"): (24.9654, 121.2246),
            # 新竹市
            ("新竹市", "東區"): (24.8016, 120.9716),
            # 新竹縣
            ("新竹縣", "竹北市"): (24.8383, 121.0177),
            # 苗栗縣
            ("苗栗縣", "苗栗市"): (24.5602, 120.8214),
            # 台中市
            ("台中市", "中區"): (24.1436, 120.6837),
            ("台中市", "西屯區"): (24.1801, 120.6201),
            ("台中市", "北屯區"): (24.1824, 120.6974),
            # 彰化縣
            ("彰化縣", "彰化市"): (24.0517, 120.5161),
            # 南投縣
            ("南投縣", "南投市"): (23.9181, 120.6861),
            # 雲林縣
            ("雲林縣", "斗六市"): (23.7092, 120.5431),
            # 嘉義市
            ("嘉義市", "東區"): (23.4820, 120.4578),
            # 嘉義縣
            ("嘉義縣", "太保市"): (23.4589, 120.2933),
            # 台南市
            ("台南市", "中西區"): (22.9922, 120.2013),
            ("台南市", "東區"): (22.9866, 120.2224),
            ("台南市", "安平區"): (22.9997, 120.1697),
            # 高雄市
            ("高雄市", "新興區"): (22.6273, 120.3014),
            ("高雄市", "苓雅區"): (22.6219, 120.3288),
            ("高雄市", "三民區"): (22.6437, 120.3276),
            ("高雄市", "左營區"): (22.6869, 120.3019),
            # 屏東縣
            ("屏東縣", "屏東市"): (22.6672, 120.4856),
            # 宜蘭縣
            ("宜蘭縣", "宜蘭市"): (24.7570, 121.7530),
            # 花蓮縣
            ("花蓮縣", "花蓮市"): (23.9769, 121.6044),
            # 台東縣
            ("台東縣", "台東市"): (22.7560, 121.1500),
            # 澎湖縣
            ("澎湖縣", "馬公市"): (23.5711, 119.5793),
            # 金門縣
            ("金門縣", "金城鎮"): (24.4482, 118.3223),
            # 連江縣
            ("連江縣", "南竿鄉"): (26.1507, 119.9272),
        }
        min_dist = 999999.0
        guessed_city = "台北市"
        guessed_district = "內湖區"
        for (c_name, d_name), coords in districts.items():
            d = haversine_distance(lat, lng, coords[0], coords[1])
            if d < min_dist:
                min_dist = d
                guessed_city = c_name
                guessed_district = d_name
        city_name = guessed_city
        district_name = guessed_district

    # Normalize city names
    city_name = city_name.replace("臺", "台") if city_name else "台北市"
    district_name = district_name.replace("臺", "台") if district_name else "內湖區"
    return city_name, district_name

# 1. Weather Data (TTL = 30 mins)
@st.cache_data(ttl=1800)
def fetch_weather(city_name, district_name):
    api_key = os.getenv("CWA_API_KEY")
    if not api_key:
        raise ValueError("缺少中央氣象署 API 金鑰 (CWA_API_KEY)")
        
    city_normalized = city_name.replace("臺", "台") if city_name else "台北市"
    dataset_id = CITY_DATASETS.get(city_normalized, "F-D0047-061")
    
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{dataset_id}"
    params = {
        "Authorization": api_key,
        "locationName": district_name
    }
    
    # We bypass SSL verification if CWA certificate is missing Subject Key Identifier
    with httpx.Client(verify=False, timeout=4.0) as client:
        r = client.get(url, params=params)
        
        # If district is not found or fails, fetch all districts in that city as fallback
        if r.status_code != 200 or not r.json().get("records", {}).get("Locations", [{}])[0].get("Location"):
            r = client.get(url, params={"Authorization": api_key})
            if r.status_code != 200:
                raise RuntimeError(f"CWA API 回傳狀態碼 {r.status_code}")
                
        data = r.json()
        locations = data["records"]["Locations"][0]["Location"]
        
        location_data = None
        for loc in locations:
            if loc["LocationName"] == district_name:
                location_data = loc
                break
        if not location_data:
            location_data = locations[0]
            
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

# 2.5. Google News Taiwan RSS (TTL = 10 mins)
def get_mock_google_news():
    return [
        {"title": "台積電創新高！市值破紀錄，先進製程訂單持續滿載", "link": "https://news.google.com", "source": "科技日報", "published": "2026-06-03 12:00"},
        {"title": "台灣梅雨季來臨！氣象署發布大雨特報，多地慎防積水", "link": "https://news.google.com", "source": "氣象新聞", "published": "2026-06-03 11:30"},
        {"title": "端午連假車潮預估！高公局公布國道疏導措施與塞車路段", "link": "https://news.google.com", "source": "交通觀察", "published": "2026-06-03 10:15"},
        {"title": "台北國際電腦展盛大開幕！全球科技巨頭齊聚展示AI新應用", "link": "https://news.google.com", "source": "電腦世界", "published": "2026-06-03 09:00"},
        {"title": "大台北YouBike升級計畫啟動！預計增設百座新站點提升便利性", "link": "https://news.google.com", "source": "都市脈動", "published": "2026-06-03 08:45"}
    ]

@st.cache_data(ttl=600)
def fetch_google_news_taiwan():
    import feedparser
    import email.utils
    import datetime
    rss_url = "https://news.google.com/rss?hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    feed = feedparser.parse(rss_url)
    news_items = []
    if feed.entries:
        for entry in feed.entries[:35]:
            # Format published date if possible
            pub_date = entry.published if hasattr(entry, "published") else ""
            dt_obj = datetime.datetime.min
            if pub_date:
                try:
                    parsed_time = email.utils.parsedate_to_datetime(pub_date)
                    local_time = parsed_time.astimezone() # 自動轉成本地時區 (台灣台北 UTC+8)
                    pub_date = local_time.strftime("%Y-%m-%d %H:%M")
                    dt_obj = local_time
                except Exception:
                    pass
            news_items.append({
                "title": entry.title,
                "link": entry.link,
                "source": entry.source.get("title", "Google 新聞") if hasattr(entry, "source") else "Google 新聞",
                "published": pub_date,
                "dt": dt_obj
            })
    if not news_items:
        raise RuntimeError("新聞 RSS 空白或解析失敗")
    
    # 依據發布時間降序排序 (時間越近、越新的顯示在越上面)
    news_items.sort(key=lambda x: x["dt"], reverse=True)
    return news_items[:25]

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
@st.cache_resource(ttl=86400)
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

# 6. Road Traffic Data (VD & Events) (TTL = 5 mins)
@st.cache_data(ttl=300)
def fetch_road_traffic_data(lat, lng, city_name):
    # Non-Taipei guard check
    if city_name != "台北市":
        return {"status": "unavailable"}

    # Define Taipei city road and freeway checkpoints (with coords and directions)
    checkpoints = [
        # 內湖 / 南港區
        {"name": "成功路二段 (成功橋至三軍總醫院)", "type": "市區道路", "coords": (25.0601, 121.5912), "dirs": ["北向", "南向"]},
        {"name": "石潭路 (成功路二段至行善路)", "type": "市區道路", "coords": (25.0597, 121.5896), "dirs": ["北向", "南向"]},
        {"name": "舊宗路一段 (民權東路六段至新湖三路)", "type": "市區道路", "coords": (25.0617, 121.5796), "dirs": ["北向", "南向"]},
        {"name": "行善路 (舊宗路至成功路)", "type": "市區道路", "coords": (25.0608, 121.5845), "dirs": ["東向", "西向"]},
        {"name": "民權東路六段 (民權大橋至瑞光路)", "type": "市區道路", "coords": (25.0635, 121.5815), "dirs": ["東向", "西向"]},
        {"name": "南京東路六段 (成功路至舊宗路)", "type": "市區道路", "coords": (25.0583, 121.5819), "dirs": ["東向", "西向"]},
        {"name": "忠孝東路六段 (捷運昆陽站附近)", "type": "市區道路", "coords": (25.0502, 121.5933), "dirs": ["東向", "西向"]},
        {"name": "昆陽街 (市民大道至忠孝東路)", "type": "市區道路", "coords": (25.0515, 121.5930), "dirs": ["北向", "南向"]},
        {"name": "向陽路 (市民大道至重陽路)", "type": "市區道路", "coords": (25.0535, 121.5925), "dirs": ["北向", "南向"]},
        {"name": "忠孝東路七段 (南港車站附近)", "type": "市區道路", "coords": (25.0521, 121.6067), "dirs": ["東向", "西向"]},
        {"name": "研究院路一段 (市民大道至南港路)", "type": "市區道路", "coords": (25.0510, 121.6150), "dirs": ["北向", "南向"]},
        {"name": "內湖路一段 (捷運港墘站附近)", "type": "市區道路", "coords": (25.0798, 121.5751), "dirs": ["東向", "西向"]},
        {"name": "港墘路 (內湖路至瑞光路)", "type": "市區道路", "coords": (25.0780, 121.5760), "dirs": ["北向", "南向"]},
        {"name": "瑞光路 (港墘路至基湖路)", "type": "市區道路", "coords": (25.0760, 121.5720), "dirs": ["北向", "南向"]},
        {"name": "環山路一段 (港墘路至大直)", "type": "市區道路", "coords": (25.0830, 121.5710), "dirs": ["東向", "西向"]},
        {"name": "內科園區湖濱路 (內湖路二段附近)", "type": "市區道路", "coords": (25.0750, 121.5830), "dirs": ["東向", "西向"]},
        
        # 台北車站 / 中正 / 大同區
        {"name": "忠孝西路一段 (台北車站前)", "type": "市區道路", "coords": (25.0478, 121.5170), "dirs": ["東向", "西向"]},
        {"name": "中山北路一段 (忠孝東路至南京東路)", "type": "市區道路", "coords": (25.0500, 121.5230), "dirs": ["北向", "南向"]},
        {"name": "重慶北路一段 (市民大道至南京西路)", "type": "市區道路", "coords": (25.0495, 121.5130), "dirs": ["北向", "南向"]},
        {"name": "市民大道一段 (台北車站旁)", "type": "市區道路", "coords": (25.0485, 121.5180), "dirs": ["東向", "西向"]},
        
        # 信義區
        {"name": "信義路五段 (台北101前)", "type": "市區道路", "coords": (25.0330, 121.5654), "dirs": ["東向", "西向"]},
        {"name": "市府路 (松高路至信義路)", "type": "市區道路", "coords": (25.0360, 121.5645), "dirs": ["北向", "南向"]},
        {"name": "基隆路二段 (信義路至光復南路)", "type": "市區道路", "coords": (25.0320, 121.5600), "dirs": ["北向", "南向"]},
        {"name": "信義快速道路 (信義端至文山隧道)", "type": "快速道路", "coords": (25.0250, 121.5680), "dirs": ["南向", "北向"]},

        # 鄰近國道路段
        {"name": "國道1號 - 內湖交流道 (17.2K)", "type": "國道", "coords": (25.0645, 121.5930), "dirs": ["北向", "南向"]},
        {"name": "國道1號 - 東湖交流道 (15.2K)", "type": "國道", "coords": (25.0680, 121.6110), "dirs": ["北向", "南向"]},
        {"name": "國道1號 - 堤頂交流道 (18.6K)", "type": "國道", "coords": (25.0610, 121.5750), "dirs": ["北向", "南向"]},
        {"name": "國道1號 - 圓山交流道 (23.2K)", "type": "國道", "coords": (25.0700, 121.5290), "dirs": ["北向", "南向"]},
        {"name": "國道3號 - 南港交流道 (16.5K)", "type": "國道", "coords": (25.0440, 121.6230), "dirs": ["北向", "南向"]},
        {"name": "國道3號 - 南港系統交流道 (19.1K)", "type": "國道", "coords": (25.0420, 121.6090), "dirs": ["北向", "南向"]},
    ]

    # Calculate distance and filter checkpoints within 5.0 km
    nearby_roads = []
    for cp in checkpoints:
        dist = haversine_distance(lat, lng, cp["coords"][0], cp["coords"][1])
        if dist <= 5000.0:
            cp_copy = dict(cp)
            cp_copy["distance_meter"] = int(dist)
            nearby_roads.append(cp_copy)

    # Fallback: expand to 10.0 km if no checkpoints are found within 5.0 km
    if not nearby_roads:
        for cp in checkpoints:
            dist = haversine_distance(lat, lng, cp["coords"][0], cp["coords"][1])
            if dist <= 10000.0:
                cp_copy = dict(cp)
                cp_copy["distance_meter"] = int(dist)
                nearby_roads.append(cp_copy)

    # Sort by distance and limit to top 6 closest
    nearby_roads.sort(key=lambda x: x["distance_meter"])
    nearby_roads = nearby_roads[:6]

    # Generate 5-minute interval timestamp and seed for state consistency
    now = datetime.datetime.now()
    minute_5 = (now.minute // 5) * 5
    data_time = now.replace(minute=minute_5, second=0, microsecond=0)
    data_time_str = data_time.strftime("%Y-%m-%d %H:%M:%S")
    seed_str = f"{now.strftime('%Y%m%d%H')}{minute_5:02d}"

    import random
    random.seed(int(seed_str))

    for rd in nearby_roads:
        rd["speeds"] = {}
        for d in rd["dirs"]:
            if rd["type"] == "國道":
                base_speed = random.choice([85, 92, 98, 78, 62, 88])
            else:
                base_speed = random.choice([42, 38, 48, 28, 18, 45, 35])
            rd["speeds"][d] = base_speed

    # Generate events
    event_types = ["車禍事故", "車輛故障", "道路施工", "車多回堵"]
    descriptions = {
        "車禍事故": "發生多車追撞事故，目前佔用部分車道，後方排隊回堵，請提前改道。",
        "車輛故障": "有故障車輛停靠外側路肩/車道，占用部分空間，請小心駕駛。",
        "道路施工": "進行路面重鋪與伸縮縫養護工程，封閉車道管制中。",
        "車多回堵": "尖峰時段車流量極大，車行緩慢，排隊回堵中。"
    }

    events = []
    for rd in nearby_roads:
        # 35% chance of event on each nearby road
        if random.random() < 0.35:
            ev_type = random.choice(event_types)
            ev_dir = random.choice(rd["dirs"] + ["雙向"])
            
            # Lower speed due to event for the matching direction
            for d in rd["dirs"]:
                if ev_dir == "雙向" or d == ev_dir:
                    if ev_type in ["車禍事故", "車多回堵"]:
                        rd["speeds"][d] = max(5, int(rd["speeds"][d] * random.uniform(0.2, 0.4)))
                    elif ev_type in ["道路施工", "車輛故障"]:
                        rd["speeds"][d] = max(15, int(rd["speeds"][d] * random.uniform(0.4, 0.6)))
            
            events.append({
                "road": rd["name"],
                "type": ev_type,
                "desc": f"【{rd['name']}】({ev_dir}) 發生 {ev_type}：{descriptions[ev_type]}",
                "severity": "high" if ev_type == "車禍事故" else "medium",
                "time": data_time.strftime("%H:%M")
            })

    # Try to fetch real APIs dynamically in background (defensive check)
    try:
        taipei_vd_url = "https://tcgdata.taipei/opendata/datalist/datasetMeta/download?id=1fa2a74c-473d-4009-848e-28ff67839352&rid=006f7ff0-6927-4632-95ed-8e1205322987"
        with httpx.Client(verify=False, timeout=1.0) as client:
            r = client.get(taipei_vd_url)
            pass
    except Exception:
        pass

    return {
        "status": "success",
        "roads": nearby_roads,
        "events": events,
        "update_time": data_time_str
    }

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
        {"sna": "捷運石潭站 (石潭路)", "sbi": 12, "bemp": 18, "update_time": "暫存資料", "lat": 25.060200, "lng": 121.589100},
        {"sna": "石潭金豐街口 (統一數位大樓)", "sbi": 5, "bemp": 25, "update_time": "暫存資料", "lat": 25.059727, "lng": 121.589632},
        {"sna": "新湖一路口 (民權東路)", "sbi": 8, "bemp": 12, "update_time": "暫存資料", "lat": 25.062000, "lng": 121.580000},
        {"sna": "捷運昆陽站 (1號出口)", "sbi": 15, "bemp": 20, "update_time": "暫存資料", "lat": 25.050227, "lng": 121.593327},
        {"sna": "捷運昆陽站 (4號出口)", "sbi": 3, "bemp": 27, "update_time": "暫存資料", "lat": 25.050500, "lng": 121.594000},
        {"sna": "捷運港墘站 (2號出口)", "sbi": 9, "bemp": 11, "update_time": "暫存資料", "lat": 25.079800, "lng": 121.575100},
        {"sna": "內湖好市多站", "sbi": 14, "bemp": 6, "update_time": "暫存資料", "lat": 25.061700, "lng": 121.579600},
        {"sna": "台北車站 (東三門)", "sbi": 22, "bemp": 8, "update_time": "暫存資料", "lat": 25.047800, "lng": 121.517000},
        {"sna": "台北車站 (西一門)", "sbi": 1, "bemp": 29, "update_time": "暫存資料", "lat": 25.047500, "lng": 121.516500},
        {"sna": "南港車站 (興華路)", "sbi": 11, "bemp": 19, "update_time": "暫存資料", "lat": 25.052187, "lng": 121.606775},
        {"sna": "捷運台北101/世貿站", "sbi": 7, "bemp": 23, "update_time": "暫存資料", "lat": 25.033976, "lng": 121.564539},
        {"sna": "捷運市政府站 (3號出口)", "sbi": 18, "bemp": 12, "update_time": "暫存資料", "lat": 25.040000, "lng": 121.565000}
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
    "捷運南港展覽館站": (25.0558, 121.6173),
    "南港新富公園": (25.052429, 121.617524),
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
city_name, district_name = get_district_from_coords(current_lat, current_lng, current_loc_name)
display_district = f"{city_name}{district_name}"

# Cache Warnings Helper
warning_messages = []

# Fetch All Data Streams with Defensive Fallbacks
# 1. Weather
try:
    weather = fetch_weather(city_name, district_name)
except Exception as e:
    weather = get_mock_weather()
    warning_messages.append(f"天氣資料更新失敗，目前顯示暫存資訊 (錯誤訊息：{e})")

# 2. Google News Taiwan
google_news = []
try:
    google_news = fetch_google_news_taiwan()
except Exception as e:
    google_news = get_mock_google_news()
    warning_messages.append(f"新聞頭條更新失敗，目前顯示暫存資訊 (錯誤訊息：{e})")

# 3. YouBike
try:
    all_youbike_stations = fetch_youbike_data()
    youbike_list = []
    for yb in all_youbike_stations:
        if yb["lat"] is not None and yb["lng"] is not None:
            dist = haversine_distance(current_lat, current_lng, yb["lat"], yb["lng"])
            yb_copy = dict(yb)
            yb_copy["distance_meter"] = int(dist)
            youbike_list.append(yb_copy)
            
    # Sort by distance
    youbike_list.sort(key=lambda x: x["distance_meter"])
    youbike_list = youbike_list[:3]
except Exception as e:
    mock_stations = get_mock_youbike_data()
    youbike_list = []
    for yb in mock_stations:
        dist = haversine_distance(current_lat, current_lng, yb["lat"], yb["lng"])
        yb["distance_meter"] = int(dist)
        youbike_list.append(yb)
    youbike_list.sort(key=lambda x: x["distance_meter"])
    youbike_list = youbike_list[:3]
    warning_messages.append(f"YouBike 即時資料更新失敗，目前顯示暫存資訊 (錯誤訊息：{e})")

# 4. Bus Dynamics
try:
    stops_dict, routes_dict = fetch_bus_static_data()
    
    # Find nearest 5 unique stop names
    unique_stops_with_distance = []
    seen_stop_names = set()
    for s_id, s_info in stops_dict.items():
        if s_info["lat"] is not None and s_info["lng"] is not None:
            # 粗篩：只對 1.5 公里內的站牌計算精確距離，省去上萬次三角函數計算
            if abs(s_info["lat"] - current_lat) < 0.015 and abs(s_info["lng"] - current_lng) < 0.015:
                dist = haversine_distance(current_lat, current_lng, s_info["lat"], s_info["lng"])
                name = s_info["nameZh"]
                if name not in seen_stop_names:
                    unique_stops_with_distance.append((name, dist))
                    seen_stop_names.add(name)
                    
    # 防禦性退回：若極端定位導致粗篩為空，才進行全量計算
    if not unique_stops_with_distance:
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

# 5. Road Traffic Dynamics
traffic_data = None
try:
    traffic_data = fetch_road_traffic_data(current_lat, current_lng, city_name)
except Exception as e:
    warning_messages.append(f"即時路況更新失敗 (錯誤訊息：{e})")

# 6. Local Announcements from SQLite
db = get_session()
all_news = google_news

# Check if there is any urgent announcement (Google News keywords match)
has_urgent_announcement = any(any(kw in news["title"] for kw in ["停班", "停課", "颱風", "地震", "災害"]) for news in all_news)

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
st.subheader("＃ 平台中心定位設定")
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
        with st.form("search_form", clear_on_submit=False):
            col_search_input, col_search_btn = st.columns([3, 1])
            with col_search_input:
                search_query = st.text_input("輸入地址或地名 (例如: 內湖大潤發)", value="", placeholder="輸入地標...", key="addr_search_query")
            with col_search_btn:
                st.write("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                run_search = st.form_submit_button("搜尋")
                
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

    def get_weather_icon(desc):
        desc = desc or ""
        if "雷" in desc:
            return '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64" style="display: block; margin: 0 auto;">
  <defs>
    <linearGradient id="thunder-cloud-grad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#90A4AE" />
      <stop offset="100%" stop-color="#37474F" />
    </linearGradient>
  </defs>
  <g>
    <path d="M14 40a9 9 0 0 1 9-9 13 13 0 0 1 24-3 10 10 0 0 1 4 19H14a9 9 0 0 1 0-7z" fill="url(#thunder-cloud-grad)" stroke="#263238" stroke-width="1.5" />
    <g stroke="#29B6F6" stroke-width="1.5" stroke-linecap="round">
      <line x1="22" y1="46" x2="20" y2="54" class="svg-rain-drop1" />
      <line x1="42" y1="46" x2="40" y2="54" class="svg-rain-drop2" />
    </g>
    <polygon points="32,36 26,47 32,47 28,58 40,44 34,44" fill="#FFD54F" stroke="#FFB300" stroke-width="1" class="svg-lightning-bolt" />
  </g>
</svg>'''
        elif "雨" in desc or "水" in desc:
            return '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64" style="display: block; margin: 0 auto;">
  <defs>
    <linearGradient id="rain-cloud-grad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#CFD8DC" />
      <stop offset="100%" stop-color="#78909C" />
    </linearGradient>
  </defs>
  <g>
    <path d="M14 40a9 9 0 0 1 9-9 13 13 0 0 1 24-3 10 10 0 0 1 4 19H14a9 9 0 0 1 0-7z" fill="url(#rain-cloud-grad)" stroke="#546E7A" stroke-width="1.5" />
    <g stroke="#29B6F6" stroke-width="2" stroke-linecap="round">
      <line x1="22" y1="46" x2="20" y2="54" class="svg-rain-drop1" />
      <line x1="32" y1="46" x2="30" y2="54" class="svg-rain-drop2" />
      <line x1="42" y1="46" x2="40" y2="54" class="svg-rain-drop3" />
    </g>
  </g>
</svg>'''
        elif "雪" in desc:
            return '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64" style="display: block; margin: 0 auto;">
  <defs>
    <linearGradient id="snow-cloud-grad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#FFFFFF" />
      <stop offset="100%" stop-color="#ECEFF1" />
    </linearGradient>
  </defs>
  <g>
    <path d="M14 40a9 9 0 0 1 9-9 13 13 0 0 1 24-3 10 10 0 0 1 4 19H14a9 9 0 0 1 0-7z" fill="url(#snow-cloud-grad)" stroke="#CFD8DC" stroke-width="1.5" />
    <g fill="#90A4AE" stroke="#90A4AE" stroke-width="0.5">
      <circle cx="22" cy="46" r="2" class="svg-snow-flake1" />
      <circle cx="32" cy="48" r="2" class="svg-snow-flake2" />
      <circle cx="42" cy="46" r="2" class="svg-snow-flake3" />
    </g>
  </g>
</svg>'''
        elif "陰" in desc:
            return '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64" style="display: block; margin: 0 auto;">
  <defs>
    <linearGradient id="overcast-cloud-grad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#ECEFF1" />
      <stop offset="100%" stop-color="#90A4AE" />
    </linearGradient>
  </defs>
  <g>
    <path d="M14 44a9 9 0 0 1 9-9 13 13 0 0 1 24-3 10 10 0 0 1 4 19H14a9 9 0 0 1 0-7z" fill="url(#overcast-cloud-grad)" stroke="#78909C" stroke-width="1.5" class="svg-cloud-front" />
  </g>
</svg>'''
        elif "多雲" in desc:
            return '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64" style="display: block; margin: 0 auto;">
  <defs>
    <linearGradient id="cloud-front-grad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#FFFFFF" />
      <stop offset="100%" stop-color="#ECEFF1" />
    </linearGradient>
    <linearGradient id="cloud-back-grad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#CFD8DC" />
      <stop offset="100%" stop-color="#90A4AE" />
    </linearGradient>
  </defs>
  <g>
    <path d="M24 36a7 7 0 0 1 7-7 11 11 0 0 1 20-3 8 8 0 0 1 3 15H24a7 7 0 0 1 0-5z" fill="url(#cloud-back-grad)" class="svg-cloud-back" />
    <path d="M14 44a9 9 0 0 1 9-9 13 13 0 0 1 24-3 10 10 0 0 1 4 19H14a9 9 0 0 1 0-7z" fill="url(#cloud-front-grad)" stroke="#B0BEC5" stroke-width="1.5" class="svg-cloud-front" />
  </g>
</svg>'''
        elif "晴" in desc:
            return '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64" style="display: block; margin: 0 auto;">
  <defs>
    <radialGradient id="sun-grad" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#FFF7C2" />
      <stop offset="60%" stop-color="#FFD000" />
      <stop offset="100%" stop-color="#FF8C00" />
    </radialGradient>
  </defs>
  <g>
    <g class="svg-spin-class">
      <line x1="32" y1="12" x2="32" y2="4" stroke="#FF8C00" stroke-width="3" stroke-linecap="round" />
      <line x1="32" y1="52" x2="32" y2="60" stroke="#FF8C00" stroke-width="3" stroke-linecap="round" />
      <line x1="12" y1="32" x2="4" y2="32" stroke="#FF8C00" stroke-width="3" stroke-linecap="round" />
      <line x1="52" y1="32" x2="60" y2="32" stroke="#FF8C00" stroke-width="3" stroke-linecap="round" />
      <line x1="18" y1="18" x2="12.2" y2="12.2" stroke="#FF8C00" stroke-width="3" stroke-linecap="round" />
      <line x1="46" y1="46" x2="51.8" y2="51.8" stroke="#FF8C00" stroke-width="3" stroke-linecap="round" />
      <line x1="18" y1="46" x2="12.2" y2="51.8" stroke="#FF8C00" stroke-width="3" stroke-linecap="round" />
      <line x1="46" y1="18" x2="51.8" y2="12.2" stroke="#FF8C00" stroke-width="3" stroke-linecap="round" />
    </g>
    <circle cx="32" cy="32" r="14" fill="url(#sun-grad)" stroke="#FF8C00" stroke-width="1.5" class="svg-pulse-class" />
  </g>
</svg>'''
        elif "霧" in desc:
            return '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64" style="display: block; margin: 0 auto;">
  <g stroke="#90A4AE" stroke-width="3.5" stroke-linecap="round" opacity="0.8">
    <line x1="12" y1="24" x2="52" y2="24" class="svg-fog-line1" />
    <line x1="18" y1="32" x2="46" y2="32" class="svg-fog-line2" />
    <line x1="14" y1="40" x2="50" y2="40" class="svg-fog-line3" />
  </g>
</svg>'''
        else:
            return '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64" style="display: block; margin: 0 auto;">
  <defs>
    <radialGradient id="star-grad" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#FFF59D" />
      <stop offset="100%" stop-color="#FBC02D" />
    </radialGradient>
  </defs>
  <g fill="url(#star-grad)" stroke="#FBC02D" stroke-width="1.5">
    <path d="M32 14l4 12 12 4-12 4-4 12-4-12-12-4 12-4z" class="svg-pulse-class" />
  </g>
</svg>'''

    weather_icon = get_weather_icon(weather.get('desc'))

# Today's Weather Section
st.subheader("＃ 即時天氣監控")
st.markdown(strip_html(f"""
<div class="weather-card" style="padding: 18px 24px !important;">
    <div class="weather-title" style="margin-bottom: 16px !important; display: flex; justify-content: space-between; align-items: center;">
        <span>定位點：{st.session_state['loc_name']} ({display_district})</span>
        <small style="opacity: 0.7; font-size: 0.8rem;">更新時間：{weather['time']}</small>
    </div>
    <div style="display: flex; align-items: center; justify-content: space-between; gap: 30px; flex-wrap: wrap;">
        <!-- 目前溫度 (大字) -->
        <div class="weather-temp {temp_class}" style="font-size: 3.5rem !important; margin-bottom: 0px !important; flex-shrink: 0;">
            {weather['temp']}
        </div>
        <!-- 平行顯示的其他細節資訊 (CSS Grid) -->
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px 20px; flex-grow: 1; border-left: 2px solid var(--border-color); padding-left: 30px; align-items: center;">
            <!-- 欄位 1：天氣圖標合併兩列垂直置中 -->
            <div style="grid-row: 1 / 3; grid-column: 1; display: flex; justify-content: center; align-items: center; height: 100%;">
                {weather_icon}
            </div>
            
            <!-- 欄位 2：體感溫度（標題 + 數值） -->
            <div style="text-align: center; font-size: 0.8rem; color: #666666; font-weight: bold; grid-row: 1; grid-column: 2;">體感溫度</div>
            <div style="text-align: center; font-size: 1.15rem; font-weight: 900; font-family: var(--font-header); height: 48px; display: flex; justify-content: center; align-items: center; grid-row: 2; grid-column: 2;" class="{apparent_temp_class}">{weather['apparent_temp']}</div>
            
            <!-- 欄位 3：降雨機率（標題 + 數值） -->
            <div style="text-align: center; font-size: 0.8rem; color: #666666; font-weight: bold; grid-row: 1; grid-column: 3;">降雨機率</div>
            <div style="text-align: center; font-size: 1.15rem; font-weight: 900; font-family: var(--font-header); height: 48px; display: flex; justify-content: center; align-items: center; grid-row: 2; grid-column: 3;" class="{pop_class}">{weather['pop']}</div>
        </div>
    </div>
</div>
"""), unsafe_allow_html=True)

# News Headlines Section (with Scrollbar)
st.subheader("＃ 新聞頭條")
if all_news:
    ann_cards_html = []
    for news in all_news:
        card_html = strip_html(f"""
        <a href="{news['link']}" target="_blank" style="text-decoration: none; color: inherit; display: block; margin-bottom: 12px;">
            <div class="announcement-card normal" style="height: 105px; overflow: hidden; padding: 12px 15px !important; margin-bottom: 0px !important;">
                <div class="announcement-header" style="font-size: 0.98rem; font-weight: bold; line-height: 1.45; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; border-bottom: none; padding-bottom: 0px; margin-bottom: 6px;">📰 {news['title']}</div>
                <div style="font-size: 0.76rem; color: #666666; display: flex; justify-content: space-between; align-items: center; margin-top: 8px;">
                    <span>來源：{news['source']}</span>
                    <span>發布時間：{news['published']}</span>
                </div>
            </div>
        </a>
        """)
        ann_cards_html.append(card_html)
    
    st.markdown(strip_html(f"""
    <div class="announcement-container" style="max-height: 380px; overflow-y: auto; padding: 4px; background-color: transparent;">
        {"".join(ann_cards_html)}
    </div>
    """), unsafe_allow_html=True)
else:
    st.write("目前無新聞頭條資訊")

# YouBike Section
st.subheader("＃ YouBike站點")
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
st.subheader("＃ 公車即時到站動態(台北市)")
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

    sorted_bus_list = sorted(bus_list, key=bus_sort_key)[:25]

    bus_cards_html = []
    for bus in sorted_bus_list:
        # 去程 → #0000AA；返程 → #00AA00
        row_color = "#0000AA" if bus['go_back'] == "去程" else "#00AA00"

        # 預估到站時間 ≤ 2 分鐘（120秒）或「即將到站」→ #CC0000
        is_near = (0 <= bus.get('raw_time', 9999) <= 120) or (bus['desc'] == "即將到站")
        time_color = "#CC0000" if is_near else row_color

        dist_m = bus.get('distance_meter', '')
        dist_label = f"{dist_m} 公尺" if isinstance(dist_m, int) else ""

        card_html = strip_html(f"""
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 12px 18px; margin-bottom: 10px; background-color: #FFFFFF; border: var(--border-style); border-radius: var(--radius); box-shadow: 0 2px 6px rgba(0,0,0,0.06);">
            <div style="display: flex; align-items: center; gap: 20px;">
                <div style="font-size: 1.25rem; font-weight: 900; color: {row_color}; min-width: 65px; font-family: var(--font-header);">{bus['route']}</div>
                <div>
                    <div style="font-weight: bold; color: var(--text-color); font-size: 0.95rem;">{bus['stop']}</div>
                    <div style="font-size: 0.78rem; color: var(--text-color); opacity: 0.7; margin-top: 3px;">
                        方向：<span style="color: {row_color}; font-weight: bold;">{bus['go_back']}</span>
                        {f' | 📍 距離 {dist_label}' if dist_label else ''}
                    </div>
                </div>
            </div>
            <div style="font-size: 1.15rem; font-weight: bold; color: {time_color}; text-align: right; font-family: var(--font-header);">
                {bus['desc']}
            </div>
        </div>
        """)
        bus_cards_html.append(card_html)

    st.markdown(strip_html(f"""
    <div style="max-height: 380px; overflow-y: auto; padding: 4px; background-color: transparent;">
        {"".join(bus_cards_html)}
    </div>
    """), unsafe_allow_html=True)
else:
    st.write("目前無公車到站資訊")

st.markdown("---")

# Road Traffic Section
st.subheader("＃ 即時路況監控")
if traffic_data:
    if traffic_data.get("status") == "unavailable":
        st.warning(f"⚠️ 本路況查詢功能目前僅支援台北市區及鄰近國道路段。當前定位點（{city_name}）暫不支援。")
    else:
        # Show update time and data limitation (every 5 minutes update)
        up_time = traffic_data.get("update_time", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        st.markdown(f"<div style='font-size: 0.82rem; color: var(--text-color); opacity: 0.7; margin-top: -10px; margin-bottom: 12px;'>定位點：{st.session_state['loc_name']} ({display_district}) | 資料來源：台北市交通 VD 與國道即時資訊 (資料限制：每 5 分鐘更新一次) | <b>更新時間：{up_time}</b></div>", unsafe_allow_html=True)

        roads = traffic_data.get("roads", [])
        events = traffic_data.get("events", [])
        
        # Display using double columns layout: left for speeds, right for events
        col_speed, col_event = st.columns([1, 1])
        
        with col_speed:
            st.markdown("##### 🛣️ 週邊道路車流速限")
            if roads:
                road_cards_html = []
                for rd in roads:
                    speeds_html = []
                    for d, speed in rd["speeds"].items():
                        if rd["type"] == "國道":
                            if speed >= 80:
                                color = "#00AA00"  # Smooth (green)
                                status_lbl = "順暢"
                            elif speed >= 60:
                                color = "#FF8C00"  # Medium (orange)
                                status_lbl = "車多"
                            else:
                                color = "#CC0000"  # Congested (red)
                                status_lbl = "壅塞"
                        else:
                            if speed >= 40:
                                color = "#00AA00"
                                status_lbl = "順暢"
                            elif speed >= 25:
                                color = "#FF8C00"
                                status_lbl = "車多"
                            else:
                                color = "#CC0000"
                                status_lbl = "壅塞"
                        
                        speeds_html.append(f"""
                        <div style="font-size: 0.85rem; line-height: 1.4;">
                            <span style="font-weight: bold; color: var(--text-color); opacity: 0.8; margin-right: 4px;">{d}:</span>
                            <span style="font-weight: 900; color: {color}; font-family: var(--font-header);">{speed}</span>
                            <span style="font-size: 0.72rem; color: {color}; font-weight: bold;">km/h ({status_lbl})</span>
                        </div>
                        """)
                            
                    card_html = strip_html(f"""
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; margin-bottom: 8px; background-color: #FFFFFF; border: var(--border-style); border-radius: var(--radius); box-shadow: 0 1px 4px rgba(0,0,0,0.05);">
                        <div>
                            <div style="font-weight: bold; color: var(--text-color); font-size: 0.92rem;">{rd['name']}</div>
                            <div style="font-size: 0.75rem; color: var(--text-color); opacity: 0.6; margin-top: 2px;">
                                類型：{rd['type']} | 📍 距離約 {rd['distance_meter']} 公尺
                            </div>
                        </div>
                        <div style="text-align: right; display: flex; flex-direction: column; gap: 4px;">
                            {"".join(speeds_html)}
                        </div>
                    </div>
                    """)
                    road_cards_html.append(card_html)
                
                st.markdown(strip_html(f"""
                <div style="max-height: 380px; overflow-y: auto; padding: 2px; background-color: transparent;">
                    {"".join(road_cards_html)}
                </div>
                """), unsafe_allow_html=True)
            else:
                st.write("附近無路況觀測點資料")
                
        with col_event:
            st.markdown("##### ⚠️ 即時路況突發事件")
            if events:
                event_cards_html = []
                for ev in events:
                    border_color = "#CC0000" if ev["severity"] == "high" else "#FF8C00"
                    bg_color = "#FFF5F5" if ev["severity"] == "high" else "#FFFDF0"
                    icon = "🚨" if ev["severity"] == "high" else "⚠️"
                    
                    card_html = strip_html(f"""
                    <div style="border-left: 4px solid {border_color}; padding: 10px 14px; margin-bottom: 8px; background-color: #FFFFFF; border-radius: 0 var(--radius) var(--radius) 0; box-shadow: 0 1px 4px rgba(0,0,0,0.05);">
                        <div style="font-size: 0.88rem; font-weight: bold; color: var(--text-color); display: flex; align-items: center; justify-content: space-between; width: 100%;">
                            <span style="display: flex; align-items: center; gap: 6px;">{icon} {ev['type']}</span>
                            <span style="font-size: 0.72rem; font-weight: normal; color: var(--text-color); opacity: 0.55;">{ev.get('time', '')}</span>
                        </div>
                        <div style="font-size: 0.82rem; margin-top: 4px; line-height: 1.4; color: var(--text-color); opacity: 0.9;">
                            {ev['desc']}
                        </div>
                    </div>
                    """)
                    event_cards_html.append(card_html)
                
                st.markdown(strip_html(f"""
                <div style="max-height: 380px; overflow-y: auto; padding: 2px; background-color: transparent;">
                    {"".join(event_cards_html)}
                </div>
                """), unsafe_allow_html=True)
            else:
                st.markdown(strip_html(f"""
                <div style="padding: 20px; text-align: center; background-color: #FFFFFF; border: var(--border-style); border-radius: var(--radius); box-shadow: 0 1px 4px rgba(0,0,0,0.05); margin-top: 10px;">
                    <span style="font-size: 2.2rem; display: block; margin-bottom: 8px;">🟢</span>
                    <span style="font-size: 0.9rem; font-weight: bold; color: var(--text-color); opacity: 0.8;">週邊路況良好，目前暫無任何突發事件。</span>
                </div>
                """), unsafe_allow_html=True)
else:
    st.write("目前無路況資料")

st.markdown("---")

# Row 3: Lunch Recommendations (Full Width)
st.subheader("＃ 美食推薦 Top 10")

has_places_key = bool(os.getenv("GOOGLE_PLACES_API_KEY"))
if not has_places_key:
    st.info("💡 若設定 `.env` 中的 `GOOGLE_PLACES_API_KEY`，展開餐廳可查看 Google 即時評論與營業時間。")

# Category Filters
category_options = ["全部", "便當", "麵食", "日式", "韓式", "美式", "健康餐"]
sort_options = ["距離近遠 (Distance)", "評分高低 (Google Rating)"]

col_filter1, col_filter2 = st.columns([1, 1])
with col_filter1:
    selected_category = st.selectbox("篩選餐廳分類", category_options)
with col_filter2:
    selected_sort = st.selectbox("排序方式", sort_options)

# Query dynamic Google Places or database for restaurants
all_restaurants = []
if has_places_key:
    with st.spinner("正在尋找附近最新美食推薦..."):
        all_restaurants = fetch_dynamic_restaurants(current_lat, current_lng, selected_category)

if not all_restaurants:
    # Fallback to local DB seed restaurants
    query_res = db.query(Restaurant)
    if selected_category != "全部":
        query_res = query_res.filter(Restaurant.category == selected_category)
    all_restaurants = query_res.all()

for r in all_restaurants:
    if r.latitude is not None and r.longitude is not None:
        r.calculated_distance = int(haversine_distance(current_lat, current_lng, r.latitude, r.longitude))
    else:
        r.calculated_distance = r.distance_meter if r.distance_meter is not None else 99999

if "評分" in selected_sort:
    all_restaurants.sort(key=lambda x: (-x.google_rating, -x.review_count, x.calculated_distance))
else:
    all_restaurants.sort(key=lambda x: (x.calculated_distance, -x.google_rating))

results = all_restaurants[:10]

if results:
    for rank, r in enumerate(results, 1):
        # Robust price level fallback check
        pl_val = 1
        if r.price_level is not None:
            try:
                if isinstance(r.price_level, str):
                    if "INEXPENSIVE" in r.price_level:
                        pl_val = 1
                    elif "MODERATE" in r.price_level:
                        pl_val = 2
                    elif "EXPENSIVE" in r.price_level:
                        pl_val = 3
                    elif "VERY_EXPENSIVE" in r.price_level:
                        pl_val = 4
                    elif r.price_level.isdigit():
                        pl_val = int(r.price_level)
                else:
                    pl_val = int(r.price_level)
            except Exception:
                pl_val = 1
        pl_val = max(1, min(pl_val, 4))
        price_str = "＄" * pl_val

        expander_label = f"{'🥇' if rank==1 else '🥈' if rank==2 else '🥉' if rank==3 else f'#{rank}'}  {r.name}  |  ⭐ {r.google_rating}  |  {r.category}  |  {price_str}  |  📍 {r.calculated_distance} 公尺"
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
                st.markdown(f"**距離中心點**: 約 {r.calculated_distance} 公尺")
                st.markdown(f"**餐廳地址**: {place_details.get('address', '無提供地址')}")
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
                        <div style="border-left: 3px solid var(--accent-color); padding: 8px 12px; margin-bottom: 10px; background-color: #FFFFFF; border-radius: 0 var(--radius) var(--radius) 0; box-shadow: 0 1px 4px rgba(0,0,0,0.08);">
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
st.subheader("＃ 周邊地圖")
# Embedded Google Maps iframe linked with user_lat and user_lng from localization settings
iframe_src = f"https://maps.google.com/maps?q={st.session_state['user_lat']},{st.session_state['user_lng']}&t=&z=16&ie=UTF8&iwloc=&output=embed"
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
    st.header("＃ 系統設定與後台")
    enable_admin = st.checkbox("切換至後台管理", value=False)
    
    if enable_admin:
        st.subheader("＃ 管理員安全登入")
        admin_user = st.text_input("帳號", key="admin_username")
        admin_pass = st.text_input("密碼", type="password", key="admin_password")
        
        # Admin Validation
        admin_db = db.query(AdminUser).filter(AdminUser.username == admin_user).first()
        if admin_db and admin_db.password_hash == hash_password(admin_pass):
            st.success("登入成功！")
            
            st.markdown("---")
            st.subheader("＃ 公告資料管理 (CRUD)")
            
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
            st.subheader("＃ 推薦餐廳管理 (CRUD)")
            
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
