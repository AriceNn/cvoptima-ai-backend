from supabase import create_client, Client
from app.core.config import get_settings

# Ayarları yükle
settings = get_settings()

# .env dosyasındaki değişkenleri al
url: str = settings.SUPABASE_URL
key: str = settings.SUPABASE_SERVICE_KEY

# Supabase istemcisini başlat
try:
    supabase: Client = create_client(url, key)
    print("Supabase istemcisi başarıyla başlatıldı.")
except Exception as e:
    print(f"HATA: Supabase istemcisi başlatılamadı: {e}")
    supabase: Client = None

def get_supabase_client() -> Client:
    if supabase is None:
        raise Exception("Supabase istemcisi başlatılmamış. Lütfen sunucu loglarını kontrol edin.")
    return supabase