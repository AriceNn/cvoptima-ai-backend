# app/api/v1/download_router.py

from fastapi import APIRouter, HTTPException, status # Depends'i kaldırdık
from fastapi.responses import RedirectResponse
from app.core.supabase_client import get_supabase_client
# User ve get_current_user importlarını kaldırdık
from datetime import datetime, timezone
import uuid
from starlette.status import HTTP_302_FOUND # 302 kullanalım

router = APIRouter(
    tags=["Download (Yönlendirme)"] # Prefix main.py'dan geliyor (/dl)
)

supabase = get_supabase_client()

@router.get("/{short_code}", status_code=HTTP_302_FOUND) # 302 kullanalım
async def redirect_to_download( # Fonksiyon adını _secure olmadan değiştirebiliriz
    short_code: str
    # user: User = Depends(get_current_user) <-- KALDIRILDI
):
    """
    Verilen kısa kodu kullanarak kullanıcıyı orijinal indirme linkine yönlendirir.
    Bu endpoint KİLİTSİZDİR. Güvenlik, kısa kodun tahmin edilemezliği
    ve linkin kısa süreli geçerliliğine dayanır.
    """
    try:
        # 1. Kısa kodu DB'de ara (user_id kontrolü olmadan)
        response = supabase.table("shortened_urls").select(
            "original_signed_url, expires_at" # user_id'yi çekmeye gerek yok
        ).eq(
            "short_code", short_code
        ).maybe_single().execute()

        if response.data is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Geçersiz veya bulunamayan indirme linki.")

        link_data = response.data
        original_url = link_data.get("original_signed_url")
        expires_at_str = link_data.get("expires_at")

        # 2. SAHİPLİK KONTROLÜ <-- KALDIRILDI

        # 3. Son kullanma tarihini kontrol et (Bu hala ÇOK ÖNEMLİ)
        if expires_at_str:
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.now(timezone.utc) > expires_at:
                raise HTTPException(status_code=status.HTTP_410_GONE, detail="İndirme linkinin süresi dolmuş.")
        else:
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Linkin geçerlilik süresi bilgisi bulunamadı.")

        # 4. Kullanıcıyı orijinal URL'ye yönlendir
        if original_url:
            print(f"DEBUG: Yönlendirme yapılacak URL: {original_url}")
            return RedirectResponse(url=original_url, status_code=HTTP_302_FOUND) # 302 kullanalım
        else:
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Orijinal indirme linki bulunamadı.")

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"HATA: Yönlendirme başarısız ({short_code}): {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="İndirme linki işlenirken bir sunucu hatası oluştu."
        )