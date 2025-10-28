# app/core/security.py

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.core.supabase_client import get_supabase_client
from supabase import Client
from gotrue.types import User # Supabase'in 'User' modelini import ediyoruz

# OAuth2PasswordBearer, FastAPI'ye "Bana 'Authorization: Bearer <token>' 
# başlığından token'ı ayıklayıp getir" demenin standart yoludur.
# tokenUrl, /login endpoint'imiz olduğunda (sonraki adımda) orayı gösterecek,
# şimdilik sadece bir yer tutucu.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token") # Henüz bu endpoint yok

# Supabase istemcisini al
supabase_client = get_supabase_client()

def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """
    FastAPI 'Depends' sistemi için bir bağımlılık (dependency).
    1. 'Authorization' başlığından Bearer token'ı alır.
    2. Token'ı Supabase'e göndererek kullanıcıyı doğrular.
    3. Kullanıcı nesnesini (veya 401 hatasını) döndürür.
    
    Bu fonksiyonu bir endpoint'e 'Depends' ile eklediğimizde, o endpoint
    otomatik olarak "kilitli" hale gelir.
    """
    try:
        # Supabase-py V2'de 'get_user' bir 'AuthResponse' nesnesi döndürür
        user_response = supabase_client.auth.get_user(token)
        
        if not user_response or not user_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Geçersiz kimlik doğrulama bilgileri (token)",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Kullanıcıyı (AuthUser nesnesini) döndür
        return user_response.user

    except Exception as e:
        # Supabase'in 'GoTrueApiError'unu da yakalayabiliriz, 
        # ancak şimdilik genel bir hata yakalama yeterli.
        print(f"Yetkilendirme Hatası: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz veya süresi dolmuş token",
            headers={"WWW-Authenticate": "Bearer"},
        )