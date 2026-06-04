import hashlib
import uuid
import datetime
from sqlalchemy import create_engine, Column, String, Boolean, DateTime, Float, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()
DB_FILE = 'dashboard.db'
DATABASE_URL = f'sqlite:///{DB_FILE}'

# --- Password Utility ---
def hash_password(password: str) -> str:
    salt = "life_dashboard_salt_"
    return hashlib.sha256((salt + password).encode('utf-8')).hexdigest()

# --- Database Models ---
def get_taipei_now():
    # Return naive datetime representing Taipei local time (UTC+8)
    tz_utc8 = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.now(tz_utc8).replace(tzinfo=None)

class Announcement(Base):
    __tablename__ = 'announcements'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=False)
    content = Column(String(1000), nullable=False)
    is_urgent = Column(Boolean, default=False)
    source = Column(String(50), default='Admin')
    created_at = Column(DateTime, default=get_taipei_now)

class Restaurant(Base):
    __tablename__ = 'restaurants'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    category = Column(String(50), nullable=False)  # 限定：便當、麵食、日式、韓式、美式、健康餐
    google_rating = Column(Float, default=4.0)
    review_count = Column(Integer, default=100)
    price_level = Column(Integer, default=1)  # 1 to 4
    distance_meter = Column(Integer)  # 距離 (石潭路155號為基準)
    latitude = Column(Float)
    longitude = Column(Float)

class Landmark(Base):
    __tablename__ = 'landmarks'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), unique=True, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

class SystemConfig(Base):
    __tablename__ = 'system_configs'
    
    key = Column(String(100), primary_key=True)
    value = Column(String(255), nullable=False)

class AdminUser(Base):
    __tablename__ = 'admin_users'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(100), unique=True, nullable=False)
    totp_secret = Column(String(255), nullable=True)
    totp_bound = Column(Boolean, default=False)

# --- DB Initialization and Seeding ---
def get_session():
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()

def init_db():
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        # 1. Seed Admin User
        # Remove old default 'admin' user if exists for security
        old_admin = db.query(AdminUser).filter(AdminUser.username == 'admin').first()
        if old_admin:
            db.delete(old_admin)
            print("Removed old default admin user.")

        admin_exists = db.query(AdminUser).filter(AdminUser.username == 'admin999').first()
        if not admin_exists:
            admin = AdminUser(username='admin999', totp_secret=None, totp_bound=False)
            db.add(admin)
            print("Created admin999 user slot (Google Authenticator pending).")

        # 2. Seed System Config & Landmarks (Option B)
        seeded_config = db.query(SystemConfig).filter(SystemConfig.key == 'has_seeded_landmarks').first()
        if not seeded_config or seeded_config.value != 'True':
            landmark_count = db.query(Landmark).count()
            if landmark_count == 0:
                seed_landmarks = [
                    Landmark(name="統一數位大樓 (內湖石潭路155號)", latitude=25.063549, longitude=121.589583),
                    Landmark(name="捷運南港展覽館站", latitude=25.055800, longitude=121.617300),
                    Landmark(name="南港新富公園", latitude=25.052429, longitude=121.617524),
                    Landmark(name="捷運昆陽站", latitude=25.050227, longitude=121.593327),
                    Landmark(name="捷運港墘站", latitude=25.079800, longitude=121.575100),
                    Landmark(name="內湖好市多", latitude=25.061700, longitude=121.579600),
                    Landmark(name="台北車站", latitude=25.047800, longitude=121.517000),
                    Landmark(name="南港車站", latitude=25.052187, longitude=121.606775),
                    Landmark(name="台北101 / 信義商圈", latitude=25.033976, longitude=121.564539),
                    Landmark(name="內科園區 (湖濱路)", latitude=25.075000, longitude=121.583000)
                ]
                db.bulk_save_objects(seed_landmarks)
                print("Seeded default landmarks.")
            
            if not seeded_config:
                db.add(SystemConfig(key='has_seeded_landmarks', value='True'))
            else:
                seeded_config.value = 'True'
            print("Initialized system config: has_seeded_landmarks.")
            
        # 2. Seed Announcements
        announcement_count = db.query(Announcement).count()
        if announcement_count == 0:
            initial_announcements = [
                Announcement(
                    title="內科通勤公車路線調整通知",
                    content="為提升通勤時段運能，即日起部分往返石潭路與捷運站之通勤公車班次調整，詳細時間請見台北市公運處官網。",
                    is_urgent=False,
                    source="TaipeiGov"
                ),
                Announcement(
                    title="夏季防範登革熱積水容器宣導",
                    content="近期午後常有陣雨，請各單位落實巡檢辦公周邊與陽台積水容器，定期落實「巡、倒、清、刷」，防範登革熱疫情滋生。",
                    is_urgent=False,
                    source="TaipeiGov"
                ),
                Announcement(
                    title="大樓中興電梯例行性季度保養公告",
                    content="本週六 (6/6) 上午 09:00 至 下午 17:00 將進行 A 棟 2 號電梯與 B 棟 1 號電梯之例行維護工程，保養期間請改搭相鄰電梯，造成不便敬請見諒。",
                    is_urgent=False,
                    source="Admin"
                ),
            ]
            db.bulk_save_objects(initial_announcements)
            print("Seeded initial announcements.")
            
        # 3. Seed Restaurants (At least 20 local Neihu restaurants)
        restaurant_count = db.query(Restaurant).count()
        if restaurant_count == 0:
            seed_restaurants = [
                Restaurant(name="梁社漢排骨 石潭店", category="便當", google_rating=4.2, review_count=320, price_level=1, distance_meter=120, latitude=25.0603, longitude=121.5891),
                Restaurant(name="少點鹽健康餐盒 內湖店", category="健康餐", google_rating=4.5, review_count=210, price_level=2, distance_meter=280, latitude=25.0594, longitude=121.5885),
                Restaurant(name="八方雲集 石潭成功店", category="麵食", google_rating=4.1, review_count=450, price_level=1, distance_meter=150, latitude=25.0610, longitude=121.5901),
                Restaurant(name="貳樓餐廳 內湖店", category="美式", google_rating=4.6, review_count=2800, price_level=3, distance_meter=750, latitude=25.0650, longitude=121.5810),
                Restaurant(name="吉野家 內湖成功店", category="日式", google_rating=3.9, review_count=380, price_level=1, distance_meter=500, latitude=25.0585, longitude=121.5920),
                Restaurant(name="韓式豆腐鍋專賣店", category="韓式", google_rating=4.3, review_count=180, price_level=2, distance_meter=350, latitude=25.0590, longitude=121.5870),
                Restaurant(name="能量小姐健康餐盒 內湖石潭店", category="健康餐", google_rating=4.4, review_count=190, price_level=2, distance_meter=240, latitude=25.0605, longitude=121.5880),
                Restaurant(name="麥當勞 內湖舊宗店", category="美式", google_rating=4.0, review_count=1600, price_level=1, distance_meter=900, latitude=25.0570, longitude=121.5790),
                Restaurant(name="大戶屋 內湖大潤發店", category="日式", google_rating=4.3, review_count=720, price_level=2, distance_meter=850, latitude=25.0580, longitude=121.5800),
                Restaurant(name="三商巧福 舊宗店", category="麵食", google_rating=3.8, review_count=210, price_level=1, distance_meter=800, latitude=25.0575, longitude=121.5805),
                Restaurant(name="涓豆腐 內湖InBase店", category="韓式", google_rating=4.5, review_count=1400, price_level=3, distance_meter=950, latitude=25.0560, longitude=121.5785),
                Restaurant(name="麵家三士 內湖成功店", category="麵食", google_rating=4.0, review_count=110, price_level=2, distance_meter=520, latitude=25.0588, longitude=121.5915),
                Restaurant(name="鬍鬚張魯肉飯 成功店", category="便當", google_rating=4.1, review_count=520, price_level=1, distance_meter=480, latitude=25.0592, longitude=121.5925),
                Restaurant(name="石二鍋 內湖大潤發店", category="日式", google_rating=4.4, review_count=1500, price_level=2, distance_meter=860, latitude=25.0579, longitude=121.5801),
                Restaurant(name="MOS BURGER 摩斯漢堡 成功店", category="美式", google_rating=4.2, review_count=280, price_level=2, distance_meter=400, latitude=25.0595, longitude=121.5930),
                Restaurant(name="正忠排骨飯 內湖店", category="便當", google_rating=4.0, review_count=640, price_level=1, distance_meter=650, latitude=25.0620, longitude=121.5830),
                Restaurant(name="段純貞牛肉麵 內湖店", category="麵食", google_rating=4.2, review_count=980, price_level=2, distance_meter=700, latitude=25.0630, longitude=121.5825),
                Restaurant(name="木子日式拉麵", category="日式", google_rating=4.3, review_count=120, price_level=2, distance_meter=310, latitude=25.0615, longitude=121.5882),
                Restaurant(name="韓川館 韓式料理", category="韓式", google_rating=4.2, review_count=350, price_level=2, distance_meter=680, latitude=25.0600, longitude=121.5820),
                Restaurant(name="SUBWAY 內湖成功店", category="健康餐", google_rating=4.1, review_count=180, price_level=1, distance_meter=460, latitude=25.0597, longitude=121.5928),
            ]
            db.bulk_save_objects(seed_restaurants)
            print("Seeded 20 restaurants.")
            
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        raise e
    finally:
        db.close()

if __name__ == '__main__':
    init_db()
