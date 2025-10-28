# app/api/v1/auth_router.py

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordRequestForm
from app.core.supabase_client import get_supabase_client
from app.schemas.auth_schema import UserCreate, Token, UserResponse
from gotrue.errors import AuthApiError  # <--- NİHAİ DÜZELTME: APIError -> AuthApiError

router = APIRouter(
    prefix="/auth",
    tags=["Authentication (Kilitsiz)"]
)

supabase = get_supabase_client()

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def user_register(user_in: UserCreate):
    """
    Yeni bir kullanıcı oluşturur (Supabase Auth).
    """
    try:
        response = supabase.auth.sign_up({
            "email": user_in.email,
            "password": user_in.password,
        })
        
        if response.user is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Kullanıcı oluşturuldu ancak oturum bilgisi alınamadı. Lütfen giriş yapmayı deneyin."
            )

        return UserResponse(id=response.user.id, email=response.user.email)

    except AuthApiError as e:  # <--- NİHAİ DÜZELTME
        # Supabase'den gelen spesifik hatayı (örn: "User already exists") yakala
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kayıt sırasında beklenmedik bir hata oluştu: {str(e)}"
        )

@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends()
):
    """
    Kullanıcıya e-posta ve şifre karşılığında bir Bearer Token (JWT) verir.
    """
    try:
        response = supabase.auth.sign_in_with_password({
            "email": form_data.username, # OAuth2 formu 'username' alanı gönderir
            "password": form_data.password
        })

        if not response.session or not response.session.access_token:
            raise Exception("Oturum veya token alınamadı")

        return Token(
            access_token=response.session.access_token,
            token_type="bearer"
        )
        
    except AuthApiError as e:  # <--- NİHAİ DÜZELTME
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Giriş başarısız: E-posta veya şifre yanlış.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        print(f"Token hatası: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Giriş başarısız: E-posta veya şifre yanlış.",
            headers={"WWW-Authenticate": "Bearer"},
        )