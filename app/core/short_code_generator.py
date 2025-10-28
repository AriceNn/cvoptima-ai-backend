import random
import string
from app.core.supabase_client import get_supabase_client

supabase = get_supabase_client()
DEFAULT_CODE_LENGTH = 7 # Kısa kodun uzunluğu (örn: 7 karakter)

def generate_short_code(length: int = DEFAULT_CODE_LENGTH) -> str:
    """Rastgele harf ve rakamlardan oluşan belirli uzunlukta bir kod üretir."""
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

async def generate_unique_short_code(length: int = DEFAULT_CODE_LENGTH) -> str:
    """
    Veritabanında ('shortened_urls' tablosu) benzersiz olduğu garanti edilen
    bir kısa kod üretir.
    
    Not: Çok düşük bir ihtimal olsa da, üretilen kod zaten varsa 
    tekrar deneyerek çakışmayı önler (collision handling).
    """
    max_attempts = 10 # Sonsuz döngüyü önlemek için bir sınır koyalım
    for _ in range(max_attempts):
        short_code = generate_short_code(length)
        try:
            # Bu kodun DB'de olup olmadığını kontrol et
            response = supabase.table("shortened_urls").select("id").eq("short_code", short_code).limit(1).execute()
            
            # Eğer 'data' boşsa, kod benzersizdir, onu döndür
            if not response.data:
                return short_code
                
        except Exception as e:
            # Veritabanı hatası durumunda işlemi durdur
            print(f"HATA: Kısa kod benzersizliği kontrol edilemedi: {e}")
            raise e # Veya None döndürerek hatayı yukarıya bildir
            
    # Eğer max_attempts denemede benzersiz kod bulunamazsa hata ver
    raise Exception(f"Benzersiz kısa kod {max_attempts} denemede üretilemedi.")