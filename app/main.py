from fastapi import FastAPI
from app.api.v1 import analysis_router
from app.api.v1 import cv_router
from app.api.v1 import auth_router
from app.api.v1 import download_router
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="CVOptima API (Gemini Edition)",
    description="Yapay zeka destekli akıllı CV ve Ön Yazı asistanı.",
    version="1.0.0"
)

# Tüm olası frontend domain'lerini ekleyin
origins = [
    "http://localhost:3000",
    "http://localhost:3001", 
    "https://cvoptima-web.vercel.app",
    "https://cvoptima-ai-frontend.vercel.app",  # Bu domain'i kontrol edin
    "https://cvoptima-ai-frontend-git-main-*.vercel.app",  # Preview deploys
    "https://*.vercel.app",  # Tüm Vercel domain'leri
]

app.include_router(auth_router.router, prefix="/api/v1")
app.include_router(analysis_router.router, prefix="/api/v1")
app.include_router(cv_router.router, prefix="/api/v1") 
app.include_router(download_router.router, prefix="/dl")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True, 
    allow_methods=["*"],
    allow_headers=["*"], 
)

@app.get("/", tags=["Root"], include_in_schema=False)
async def read_root():
    return {"message": "CVOptima API'ye hoş geldiniz."}