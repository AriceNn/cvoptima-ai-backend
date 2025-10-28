from supabase import create_client, Client
from app.core.config import get_settings
import os

# Ayarları yükle
settings = get_settings()

# .env dosyasındaki değişkenleri al
url: str = settings.SUPABASE_URL
key: str = settings.SUPABASE_SERVICE_KEY

# Supabase istemcisini başlat
try:
    # service_role anahtarını kullandığımız için,
    # bu istemci tüm RLS (Satır Seviyesi Güvenlik) kurallarını atlayacaktır.
    # Backend'imizin buna ihtiyacı var.
    supabase: Client = create_client(url, key)
    print("Supabase istemcisi başarıyla başlatıldı.")
except Exception as e:
    print(f"HATA: Supabase istemcisi başlatılamadı: {e}")
    supabase: Client = None

def get_supabase_client() -> Client:
    """
    FastAPI'nin 'Depends' sistemi için istemciyi döndüren bir yardımcı fonksiyon.
    Şimdilik doğrudan import edeceğiz, ancak bu yapı gelecekte
    dependency injection için hazır.
    """
    if supabase is None:
        raise Exception("Supabase istemcisi başlatılmamış. Lütfen sunucu loglarını kontrol edin.")
    return supabase