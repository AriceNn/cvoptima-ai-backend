# app/schemas/analysis_schema.py
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime

# --- AI Çıktı Modelleri ---
# Gemini'den bu yapıda bir JSON dönmesini isteyeceğiz.

class KeywordAnalysis(BaseModel):
    hard_skills: List[str] = Field(..., description="Teknik veya ölçülebilir beceriler (örn: Python, SQL, Proje Yönetimi)")
    soft_skills: List[str] = Field(..., description="Kişilerarası beceriler (örn: Ekip Çalışması, İletişim, Liderlik)")

class GapAnalysisResult(BaseModel):
    matching_skills: List[str] = Field(..., description="Hem CV'de hem ilanda bulunan ortak beceriler")
    missing_skills: List[str] = Field(..., description="İlanda aranan ancak CV'de bulunmayan veya zayıf olan beceriler")

class Suggestion(BaseModel):
    suggestion_title: str = Field(..., description="Önerinin kısa başlığı (örn: 'Deneyiminizi Nicelleştirin')")
    suggestion_detail: str = Field(..., description="Önerinin nasıl uygulanacağına dair detaylı açıklama")
    cv_example: str = Field(..., description="Öneriyi uygulamak için CV'ye eklenebilecek örnek bir cümle")

class FullAnalysisResponse(BaseModel):
    job_keywords: KeywordAnalysis = Field(..., description="İş ilanından çıkarılan anahtar kelimeler")
    cv_keywords: KeywordAnalysis = Field(..., description="CV'den çıkarılan anahtar kelimeler")
    gap_analysis: GapAnalysisResult = Field(..., description="Eksik ve eşleşen beceri analizi")
    suggestions: List[Suggestion] = Field(..., description="CV'yi iyileştirmek için 3-5 adet spesifik öneri")
    cover_letter_draft: str = Field(..., description="İlana ve CV'ye özel oluşturulmuş ön yazı taslağı")

# --- API İstek ve Yanıt Modelleri ---

class AnalysisRequest(BaseModel):
    cv_id: uuid.UUID
    job_description_text: str

class AnalysisTaskStartResponse(BaseModel):
    task_id: uuid.UUID
    status: str = "pending"

class AnalysisTaskStatusResponse(BaseModel):
    task_id: uuid.UUID
    status: str = Field(..., description="pending, completed, veya failed")
    result: Optional[FullAnalysisResponse] = None

# --- FAZ 4 YENİ ŞEMALAR ---

class CVListItem(BaseModel):
    """CV listesindeki tek bir öğeyi temsil eder."""
    id: uuid.UUID
    file_name: str
    created_at: datetime # Yüklenme zamanını döndüreceğiz

    # Pydantic'in veritabanı nesnelerini bu modele dönüştürmesini sağlar
    class Config:
        from_attributes = True 

class CVListResponse(BaseModel):
    """Kullanıcının CV listesini içeren yanıt modeli."""
    cvs: List[CVListItem]

class CVDetailResponse(BaseModel):
    """Belirli bir CV'nin tüm detaylarını temsil eder."""
    id: uuid.UUID
    file_name: str
    created_at: datetime
    file_path: str | None # Storage yolu NULL olabilir mi? Hayır, yükleme başarılıysa olmamalı. 'str' yapalım.
    cv_text_content: str # Tam metin içeriği

    class Config:
        from_attributes = True

class AnalysisJobListItem(BaseModel):
    """Analiz işleri listesindeki tek bir öğeyi temsil eder."""
    id: uuid.UUID # task_id
    cv_file_name: str | None # JOIN ile gelecek, CV silinmişse None olabilir
    job_description_snippet: str | None # İş ilanının kısa özeti
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class AnalysisJobListResponse(BaseModel):
    """Kullanıcının analiz işleri listesini içeren yanıt modeli."""
    jobs: List[AnalysisJobListItem]

class CVDownloadURLResponse(BaseModel):
    """CV indirme linkini içeren yanıt modeli."""
    download_url: str
    expires_in: int # Linkin kaç saniye geçerli olduğu

class CVDownloadURLResponse(BaseModel):
    """CV indirme için kısa kodu içeren yanıt modeli."""
    short_code: str 
    expires_in: int