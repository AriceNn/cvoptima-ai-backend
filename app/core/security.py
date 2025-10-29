# app/core/security.py

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.core.supabase_client import get_supabase_client
from gotrue.types import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token") # Henüz bu endpoint yok

# Supabase istemcisini al
supabase_client = get_supabase_client()

def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
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