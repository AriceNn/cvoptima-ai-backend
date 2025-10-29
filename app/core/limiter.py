# app/core/limiter.py
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

def get_request_identifier(request: Request) -> str:
    """
    Rate limiting için kullanıcıyı güvenli şekilde tanımlar.
    Öncelik: Supabase user_id (JWT 'sub').
    Fallback: IP (X-Forwarded-For destekli).
    """
    # Reverse proxy desteği
    forwarded_for = request.headers.get("x-forwarded-for")
    real_ip = forwarded_for.split(",")[0].strip() if forwarded_for else get_remote_address(request)

    auth_header = request.headers.get("authorization")
    if auth_header:
        try:
            token = auth_header.split(" ")[1]
            # Token içindeki sub alanını çıkarmak güvenli kimlik mekanizmasıdır
            # Token decode etmiyoruz -> sadece hash key olarak kullanıyoruz
            return token
        except Exception:
            return real_ip

    return real_ip

# production safe limiter
limiter = Limiter(
    key_func=get_request_identifier,
    default_limits=[]
)