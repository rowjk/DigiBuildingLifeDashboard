# Newsprint 視覺設計系統與實作指南 (Newsprint Style Guide)

本文件基於對 [designprompts.dev/newsprint](https://www.designprompts.dev/newsprint) 的深度視覺與排版分析所建立。Newsprint（報紙印刷）是一種極具個性、權威感且充滿物理質感的**編輯部新聞紙風格（Editorial Newspaper Style）**。它徹底揚棄了現代網頁常見的漸層、圓角、陰影與柔和毛玻璃效果，轉而向傳統紙質印刷致敬，透過強對比的黑白墨色、嚴謹的網格線條以及精緻的襯線字體，創造出極佳的資訊可讀性與視覺張力。

本指南提供完整的設計標記（Design Tokens）、純 CSS 實作程式碼、Tailwind CSS 配置，以及針對本專案 Streamlit 儀表板的專屬樣式套用代碼與 AI 生成提示詞（System Prompt）。

---

## 👁️ 一、Newsprint 視覺風格深度解析

### 1. 核心設計理念 (Design Philosophy)
*   **紙感回歸 (Ink-on-Paper)**：模擬油墨壓印在紙張上的實體感受，強調二維平面的權威感。
*   **編輯纪律 (Editorial Discipline)**：以嚴格的網格（Grid）和細實線（Rules）來分割區塊，取代現代卡片的陰影投影。
*   **高資訊密度 (High Density)**：仿照報紙版面，鼓勵緊湊的文字排版，讓多個資訊流（天氣、公告、站點、交通）以版型欄位形式高效鋪開。
*   **拒絕現代點綴 (No Softness)**：
    *   ❌ 嚴禁：漸層色（Gradients）、模糊（Blur）、圓角（Border Radius > 2px）、盒子陰影（Box Shadows）、滑順的彈性動畫。
    *   ✅ 採用：純色塊、精確的 1px/2px 直角黑線、俐落的硬切換（Hard-cut）Hover 效果。

### 2. 品牌情感與調性 (Emotional Vibe)
*   **權威、博學、直接、傳統、具公信力**。適合新聞媒體、報告、儀表板、數據分析、企業內部生活資訊展示等需要「訊息第一」的介面。

---

## 🎨 二、設計標記系統 (Design Tokens)

### 1. 色彩系統 (Color Palette)
色彩系統極度簡練，僅靠紙張底色、墨黑色及警示性紅色構成：

| 標記名稱 (Token) | 數值 (Hex) | 設計意圖 (Design Intent) |
| :--- | :--- | :--- |
| `background-paper` | `#F7F4EF` | 模擬有些微泛黃、溫暖、不傷眼的傳統新聞紙質底色。 |
| `text-ink` | `#111111` | 模擬深黑色油墨，具有極高對比與辨識度，非純黑（`#000`）以避免刺眼。 |
| `text-muted` | `#555555` | 用於副標題、時間、次要資訊的灰色油墨。 |
| `border-rule` | `#111111` | 用於版面分割線、表格邊框，維持排版的骨架感。 |
| `accent-red` | `#CC0000` | 北市府緊急公告或高亮警示所使用的「印章紅 / 社論紅」，吸睛且嚴肅。 |
| `accent-red-light` | `#FDF2F2` | 用於緊急警告區塊的背景底色。 |
| `hover-ink` | `#000000` | 互動時的反白或全墨黑填充。 |

### 2. 字體排印 (Typography)
Newsprint 風格的核心在於「標題襯線，內文無襯線 / 襯線雙軌制」：

*   **標題字型 (Headings - Serif)**：
    *   推薦 Google Fonts：`Fraunces`、`Playfair Display`、`Lora`
    *   系統備用字型：`Georgia`, `Cambria`, `"Times New Roman"`, serif
    *   特徵：粗體（Font Weight 700/800）、較大的字重對比，傳達強烈的「頭條新聞」感。
*   **內文字型 (Body - Sans-Serif or Serif)**：
    *   推薦 Google Fonts：`Inter`（現代清晰）或 `PT Serif`（復古閱讀）
    *   系統備用字型：`system-ui`, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif
    *   特徵：高度易讀、行高（Line Height）設定在 `1.6` 至 `1.75` 之間，提供充足的字距與行距以利閱讀。

### 3. 佈局與網格 (Grid & Layout Rules)
*   **實線網格**：卡片或資訊區塊之間使用 `1px solid #111111` 的外框，相鄰的卡片共享邊框線，形成類似報紙版面的格線。
*   **非對稱寬度**：在 12 欄網格中，多採用 `8:4`、`7:5` 或三等分 `4:4:4` 的排版，使視覺看起來有主次社論的層次感。
*   **首字放大 (Drop Caps)**：在長篇公告或主要介紹的第一段，首字可使用較大字體，為版面增添文學氣息。

---

## 🛠️ 三、網頁技術套用指南

### 1. 原生 CSS / CSS 變數實作 (Vanilla CSS)
如果您在一般 HTML/JS 專案中套用此風格，可直接將以下程式碼加入樣式表：

```css
/* 匯入 Google Fonts */
@import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,700;0,9..144,900;1,9..144,400&family=Inter:wght@400;500;600;700&display=swap');

:root {
  --bg-paper: #F7F4EF;
  --text-ink: #111111;
  --text-muted: #555555;
  --border-rule: #111111;
  --accent-red: #CC0000;
  --accent-red-light: #FDF2F2;
  
  --font-serif: 'Fraunces', Georgia, serif;
  --font-sans: 'Inter', system-ui, sans-serif;
}

/* 全域底色與字體 */
body {
  background-color: var(--bg-paper);
  color: var(--text-ink);
  font-family: var(--font-sans);
  line-height: 1.6;
  margin: 0;
  padding: 0;
}

/* 報紙大標題 */
h1, h2, h3 {
  font-family: var(--font-serif);
  font-weight: 900;
  color: var(--text-ink);
  margin-top: 0;
  letter-spacing: -0.02em;
}

h1 {
  font-size: 3rem;
  border-bottom: 3px double var(--border-rule);
  padding-bottom: 10px;
  text-transform: uppercase;
}

h2 {
  font-size: 1.8rem;
  border-bottom: 1px solid var(--border-rule);
  padding-bottom: 5px;
}

/* 報紙格線卡片 (Newspaper Columns) */
.news-card {
  background-color: transparent;
  border: 1px solid var(--border-rule);
  border-radius: 0; /* 強制直角 */
  padding: 20px;
  margin-bottom: 20px;
  box-shadow: none; /* 無陰影 */
}

/* 報紙風格按鈕 (Newspaper Button) */
.news-btn {
  font-family: var(--font-serif);
  font-weight: 700;
  background-color: transparent;
  color: var(--text-ink);
  border: 2px solid var(--border-rule);
  padding: 8px 16px;
  cursor: pointer;
  border-radius: 0;
  transition: all 0.1s ease; /* 快速硬切換 */
}

.news-btn:hover {
  background-color: var(--text-ink);
  color: var(--bg-paper); /* 反白效果 */
}

/* 雙分隔線 */
.double-divider {
  border-top: 3px double var(--border-rule);
  margin: 20px 0;
}
```

### 2. Tailwind CSS 配置檔 (Tailwind Config)
如果您使用的是 Tailwind CSS，請在 `tailwind.config.js` 中擴充主題配置：

```javascript
module.exports = {
  theme: {
    extend: {
      colors: {
        newsprint: {
          paper: '#F7F4EF',
          ink: '#111111',
          muted: '#555555',
          red: '#CC0000',
          'red-light': '#FDF2F2',
        }
      },
      fontFamily: {
        serif: ['Fraunces', 'Georgia', 'serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      borderWidth: {
        '3': '3px',
      },
      borderRadius: {
        'none': '0',
      }
    },
  },
  plugins: [],
}
```

---

## ⚡ 四、專案實作：統一數位大樓 Life Dashboard 套用

若要將此風格完全注入您目前的 Python Streamlit 儀表板中，您只需將 `app.py` 中原本的 `st.markdown("<style>...</style>")` 區塊（[app.py:L26-70](file:///c:/Users/james_wu/Documents/Antigravity_Project/統一數位大樓生活資訊平台 (Life Dashboard)/app.py#L26-70)）替換為以下的新聞紙客製化 CSS 樣式。

### Streamlit 客製化樣式替換區塊：
```python
# ----------------- CSS Custom Styling (Newsprint Editorial Style) -----------------
st.markdown("""
<style>
    /* 匯入襯線與無襯線 Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,700;0,9..144,900;1,9..144,400&family=Inter:wght@400;500;600;700&display=swap');

    /* 覆寫 Streamlit 全域底色與字體 */
    .stApp {
        background-color: #F7F4EF !important;
        color: #111111 !important;
        font-family: 'Inter', system-ui, sans-serif;
    }
    
    /* 調整主容器邊界 */
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 2rem !important;
        max-width: 1200px;
    }

    /* 報紙標題樣式 */
    h1 {
        font-family: 'Fraunces', Georgia, serif !important;
        font-weight: 900 !important;
        color: #111111 !important;
        border-bottom: 4px double #111111 !important;
        padding-bottom: 12px !important;
        letter-spacing: -0.03em !important;
        text-transform: uppercase;
        font-size: 2.6rem !important;
    }

    h2, h3, .stSubheader {
        font-family: 'Fraunces', Georgia, serif !important;
        font-weight: 700 !important;
        color: #111111 !important;
        border-bottom: 1px solid #111111 !important;
        padding-bottom: 6px !important;
        margin-top: 1.5rem !important;
        margin-bottom: 1rem !important;
    }

    /* 刪除 Streamlit 預設元件的圓角與陰影 */
    div[data-testid="stMetricValue"] {
        font-family: 'Fraunces', Georgia, serif !important;
        font-weight: 900 !important;
        color: #111111 !important;
    }
    
    /* YouBike 等資訊卡片：化身為報紙欄欄位 */
    .metric-card {
        background-color: transparent !important;
        border-radius: 0px !important; /* 強制直角 */
        padding: 15px !important;
        border: 1px solid #111111 !important; /* 墨黑單實線 */
        margin-bottom: 15px !important;
    }
    
    .metric-label {
        font-size: 0.85rem !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #555555 !important;
        font-family: 'Inter', sans-serif;
    }
    
    .metric-value {
        font-size: 1.8rem !important;
        font-family: 'Fraunces', Georgia, serif !important;
        font-weight: 900 !important;
        color: #111111 !important;
    }

    /* 天氣卡片：由炫目漸層改為極簡新聞專欄風格 */
    .weather-card {
        background: transparent !important;
        color: #111111 !important;
        border-radius: 0px !important;
        padding: 20px !important;
        border: 2px solid #111111 !important; /* 粗實線強調主要專欄 */
        margin-bottom: 20px !important;
        box-shadow: none !important;
    }
    
    .weather-title {
        font-family: 'Fraunces', Georgia, serif !important;
        font-size: 1.1rem !important;
        font-weight: bold !important;
        border-bottom: 1px dashed #111111;
        padding-bottom: 8px;
        margin-bottom: 12px !important;
    }
    
    .weather-temp {
        font-family: 'Fraunces', Georgia, serif !important;
        font-size: 3rem !important;
        font-weight: 900 !important;
        line-height: 1 !important;
        margin-bottom: 10px;
    }
    
    .weather-details {
        font-size: 0.95rem !important;
        line-height: 1.6 !important;
    }

    /* 調整警告橫幅 (st.warning / st.error) 符合報紙社論插頁風格 */
    .stAlert {
        border-radius: 0px !important;
        border: 1px solid #111111 !important;
        background-color: #FDF2F2 !important; /* 淡紅紙底 */
        color: #CC0000 !important;
    }

    /* 表格與 Dataframe 風格化 */
    div[data-testid="stTable"], .element-container iframe {
        border: 1px solid #111111 !important;
        border-radius: 0px !important;
    }
    
    /* 側邊欄風格同步 */
    section[data-testid="stSidebar"] {
        background-color: #F2EFE9 !important; /* 稍微深一點的新聞紙色做區隔 */
        border-right: 1px solid #111111 !important;
    }
    
    /* 自訂雙線條 */
    hr {
        border: none !important;
        border-top: 3px double #111111 !important;
        opacity: 1 !important;
        margin: 1.5rem 0 !important;
    }
</style>
""", unsafe_allow_html=True)
```

---

## 🤖 五、AI 生成提示詞 (Newsprint System Prompt)

您可以直接複製以下 Prompt 餵給 Claude 或 GPT，指令 AI 產出完全符合本風格的全新網頁元件：

```markdown
你是一位精通 20 世紀初傳統報紙印刷（Broadsheet Newspaper）與現代編輯排版學的資深 UI/UX 設計師與前端工程師。請為我生成符合「Newsprint」設計系統風格的 UI 元件。

請嚴格遵守以下 Newsprint 設計規範：

1. 【角色與行為】：
   - 抱持極簡、理性且權威的編輯態度。
   - 拒絕一切浮誇的網頁裝飾，讓資訊透過嚴謹的「排版（Typography）」與「網格（Grid）」自己發聲。

2. 【色彩標記 (Colors)】：
   - 頁面底色必須是 `#F7F4EF`（溫暖的新聞紙泛白色）。
   - 內文字體與主線條必須是 `#111111`（深墨黑色）。
   - 次要資訊與輔助標籤使用 `#555555`（無光澤灰墨色）。
   - 關鍵提示、警報或活動徽章，使用 `#CC0000`（醒目的印章紅）。
   - 嚴禁使用任何色彩漸層（Gradients）、半透明毛玻璃或柔和粉彩色。

3. 【字體排印 (Typography)】：
   - 所有的主標題、次標題與強重音，必須使用精緻的 Serif（襯線字型），例如 'Fraunces'、'Playfair Display'、Georgia，字重設為 700、800 或 900。
   - 內文段落、表單文字與按鈕，使用乾淨清晰的 Sans-Serif（無襯線字型），例如 'Inter' 或 system-ui。

4. 【形狀與陰影】：
   - 圓角（Border Radius）一律設為 `0px`（純直角）或最多為 `2px`（紙張裁切微小圓角）。
   - 嚴禁使用任何陰影效果（`box-shadow: none`、`text-shadow: none`）。

5. 【佈局線條 (Rules & Grids)】：
   - 區塊之間使用 `1px solid #111111` 的實線進行分隔。
   - 頁頭可以使用 `3px double #111111`（雙實線）來增加報紙報頭的層次質感。
   - Hover 效果必須為「硬切換（Hard-cut）」，例如：當滑鼠懸停在按鈕上時，瞬間將背景設為 `#111111`、文字設為 `#F7F4EF`，不使用淡入淡出過渡。
```

---

## 📈 六、驗證與調校建議

1.  **高對比度 (A11y)**：本風格的墨黑字體（#111111）在新聞紙底色（#F7F4EF）上的對比度高達 15.6:1，遠超 WebAIM AAA 級的 7:1 標準，具有極佳的易讀性。
2.  **紙質紋理 (選用)**：若想更精緻，可為網站背景加上極淡的雜訊（Noise）底圖，以模擬紙張微小的纖維顆粒感。
3.  **地圖色彩優化**：如果您的地圖使用 Google Maps 或 Mapbox，建議套用「Mono」或「Retro Paper」主題色彩配置，將地圖底色也調成灰黃色調，讓整體視覺更加一體化。
