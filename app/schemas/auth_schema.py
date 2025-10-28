# app/schemas/auth_schema.py

from pydantic import BaseModel, EmailStr, Field  # <-- 'Field' burada olmalı
import uuid  # <-- 'uuid' burada olmalı

class UserCreate(BaseModel):
    """Kullanıcı kaydı (sign-up) için Pydantic modeli"""
    email: EmailStr
    password: str = Field(..., min_length=8) # <-- 'Field' ve büyük 'C'

class UserResponse(BaseModel):
    """Kayıt başarılı olduğunda dönen yanıt modeli"""
    id: uuid.UUID
    email: EmailStr

    class Config:
        from_attributes = True # 'orm_mode'un Pydantic V2'deki adı

class Token(BaseModel):
    """Giriş (login) başarılı olduğunda dönen Access Token modeli"""
    access_token: str
    token_type: str = "bearer"