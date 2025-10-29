# app/core/limiter.py
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

def get_request_identifier(request: Request) -> str:
    """
    Kullanıcıyı tanımlamak için bir anahtar döndürür.
    Öncelik: Authorization token.
    Fallback: IP Adresi (Token olmayan endpoint'ler için).
    """
    # Middleware'imiz sayesinde /analysis/start endpoint'ine gelen
    # isteklerin ZATEN bir Authorization başlığı olmasını bekliyoruz.
    auth_header = request.headers.get("authorization")
    
    if auth_header:
        try:
            # Token'ın kendisini (Bearer xxx) anahtar olarak kullanalım.
            # Bu, kullanıcıya özgüdür ve güvenlidir.
            return auth_header.split(" ")[1] 
        except IndexError:
            # Başlık formatı bozuksa, IP'ye düş
            return get_remote_address(request)
    
    # Eğer bir şekilde token yoksa (ki olmamalı), IP adresini kullan
    return get_remote_address(request)

# Limitleyiciyi oluştur ve anahtar fonksiyonumuzu (key_func) ata
# storage: Varsayılan olarak hafızada (in-memory) tutar. 
# Production için Redis (örn: "redis://localhost:6379") kullanmak daha iyidir.
limiter = Limiter(key_func=get_request_identifier)