# app/core/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache
from dotenv import load_dotenv  # <--- 1. BU SATIRI EKLEYİN
import os # <--- Proje yolunu bulmak için eklendi

# --- 2. MİMARİ DÜZELTME BURADA ---
# pydantic-settings'in sihirli .env yüklemesine güvenmek yerine,
# .env dosyasını biz manuel olarak yüklüyoruz.

# Projenin ana dizinini bul (config.py'nin iki üst dizini)
# /app/core/ -> /app/ -> / (proje kök dizini)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOTENV_PATH = os.path.join(BASE_DIR, '.env')

if os.path.exists(DOTENV_PATH):
    load_dotenv(dotenv_path=DOTENV_PATH)
    print(f".env dosyası şu yoldan yüklendi: {DOTENV_PATH}") # <--- Yüklendiğini görmek için log
else:
    print(f"UYARI: .env dosyası şu yolda bulunamadı: {DOTENV_PATH}") # <--- Bulamazsa log

# --- 3. pydantic-settings'in geri kalanı ---
# load_dotenv() çalıştığı için, BaseSettings artık 
# GOOGLE_API_KEY'i işletim sistemi ortam değişkenlerinden (environment) okuyabilir.

class Settings(BaseSettings):
    GOOGLE_API_KEY: str
    SUPABASE_URL: str     
    SUPABASE_SERVICE_KEY: str

    class Config:
        pass 

@lru_cache()
def get_settings():
    try:
        return Settings()
    except Exception as e:
        # Pydantic'in hata vermesi (örn: KEY hala bulunamadı) durumunda
        print(f"HATA: Ayarlar yüklenemedi. .env dosyanızı veya değişken adını kontrol edin. Hata: {e}")
        raise e