# app/api/v1/analysis_router.py
from fastapi import APIRouter, BackgroundTasks, HTTPException, status, Depends
from pydantic import ValidationError
from app.schemas.analysis_schema import (
    AnalysisRequest, 
    AnalysisTaskStartResponse, 
    AnalysisTaskStatusResponse,
    FullAnalysisResponse,
    AnalysisJobListResponse, 
    AnalysisJobListItem
)
from app.services.ai_service import run_full_analysis
from app.core.supabase_client import get_supabase_client
import uuid
from typing import Dict, Any, List
from app.core.security import get_current_user # Güvenlik (Token doğrulama)
from gotrue.types import User
from app.core.limiter import limiter # <-- FAZ 4 SONU: Rate Limiter importu

router = APIRouter(
    prefix="/analysis",
    tags=["Analysis (Kilitli)"] # Swagger'da görünecek başlık
)

supabase = get_supabase_client()

# --- ARKA PLAN GÖREVİ ---
def run_analysis_background_task(task_id: uuid.UUID, cv_id: uuid.UUID, job_description_text: str, user_id: uuid.UUID):
    """
    Arka planda (asenkron) çalışan ana AI analiz görevi.
    1. DB'den CV metnini çeker (sahiplik kontrolü ile).
    2. AI servisini (Gemini) çalıştırır.
    3. Sonucu 'analysis_jobs' tablosuna 'completed' veya 'failed' olarak günceller.
    """
    try:
        print(f"Arka plan görevi {task_id} (Kullanıcı: {user_id}) başladı...")
        
        # 1. DB'den CV metnini çek (Güvenlik: Sadece o kullanıcıya ait CV'yi seç)
        cv_response = supabase.table("user_cvs").select("cv_text_content").eq("id", str(cv_id)).eq("user_id", str(user_id)).execute()
        
        if not cv_response.data:
            raise Exception(f"CV ID ({cv_id}) bulunamadı veya kullanıcıya ({user_id}) ait değil.")
            
        cv_text = cv_response.data[0].get("cv_text_content")
        if not cv_text:
            raise Exception(f"CV ID'si {cv_id} için 'cv_text_content' (ayrıştırılmış metin) boş.")

        # 2. AI analizini çalıştır (Yavaş olan kısım)
        analysis_result: FullAnalysisResponse = run_full_analysis(cv_text, job_description_text)
        
        # 3. Başarı durumunda 'analysis_jobs' tablosunu güncelle
        # RLS politikası sayesinde sadece user_id'si eşleşen satırı güncelleyebilir.
        supabase.table("analysis_jobs").update({
            "status": "completed",
            "result": analysis_result.model_dump() # Pydantic modelini dict'e çevir
        }).eq("id", str(task_id)).eq("user_id", str(user_id)).execute()
        
        print(f"Arka plan görevi {task_id} tamamlandı.")

    except Exception as e:
        print(f"HATA: Arka plan görevi {task_id} başarısız oldu: {e}")
        # 4. Hata durumunda 'analysis_jobs' tablosunu güncelle
        supabase.table("analysis_jobs").update({
            "status": "failed",
            "result": {"error": str(e)} 
        }).eq("id", str(task_id)).eq("user_id", str(user_id)).execute()

# --- API ENDPOINT'LERİ ---

@router.post("/start", response_model=AnalysisTaskStartResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_analysis(
    analysis_request: AnalysisRequest, # Frontend'den gelen body (cv_id, job_description_text)
    background_tasks: BackgroundTasks, # Arka plan görevi için
    user: User = Depends(get_current_user), # Güvenlik: Token'ı doğrular, 'user' nesnesini getirir
    _limit: None = Depends(limiter.limit("8/minute")) # <-- YENİ: Rate limit kuralı
):
    """
    KİMLİĞİ DOĞRULANMIŞ kullanıcı için yeni bir analiz görevi başlatır.
    Kullanıcı başına dakikada 8 istek ile sınırlandırılmıştır.
    """
    try:
        # 1. 'analysis_jobs' tablosuna 'pending' olarak yeni bir satır ekle
        new_job_data = {
            "cv_id": str(analysis_request.cv_id),
            "job_description_text": analysis_request.job_description_text,
            "status": "pending",
            "user_id": str(user.id) # Token'dan gelen user.id'yi ekle
        }
        
        response = supabase.table("analysis_jobs").insert(new_job_data).execute()
        
        if not response.data or len(response.data) == 0:
            raise Exception("Veritabanına 'job' kaydı başarısız oldu, veri dönmedi.")
            
        new_task = response.data[0]
        task_id = new_task.get("id")
        
        # 2. Pydantic modeliyle yanıtı doğrula (task_id'nin UUID olduğundan emin ol)
        try:
            response_model = AnalysisTaskStartResponse(task_id=task_id, status="pending")
        except ValidationError as e:
            print(f"HATA: Pydantic validasyonu başarısız (task_id UUID değil mi?): {e}")
            raise HTTPException(status_code=500, detail="Oluşturulan görev ID'si geçersiz.")
        
        # 3. Asıl ağır işi (AI analizi) arka plana at
        background_tasks.add_task(
            run_analysis_background_task, 
            task_id, 
            analysis_request.cv_id, 
            analysis_request.job_description_text,
            user.id
        )
        
        # 4. Kullanıcıya (frontend'e) hemen yanıt dön
        return response_model

    except Exception as e:
        print(f"HATA: Analiz başlatılamadı: {e}")
        # 'analysis_jobs_cv_id_fkey' hatası (Foreign Key) 404'e maplenir
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Analiz başlatılırken bir hata oluştu. CV ID ({analysis_request.cv_id}) bulunamadı veya geçersiz."
        )

@router.get("", response_model=AnalysisJobListResponse)
async def list_user_analysis_jobs(user: User = Depends(get_current_user)):
    """
    Giriş yapmış kullanıcının başlattığı tüm analiz işlerini listeler.
    İlişkili CV'nin adını da JOIN ile getirir.
    """
    try:
        # Supabase JOIN Syntax: select("*, table_name(column_name)")
        # RLS politikası sayesinde zaten sadece bu kullanıcıya ait olanlar gelir.
        response = supabase.table("analysis_jobs").select(
            "id, job_description_text, status, created_at, user_cvs(file_name)" # JOIN
        ).eq(
            "user_id", str(user.id) # Katmanlı savunma
        ).order(
            "created_at", desc=True # En yeniden eskiye sırala
        ).execute()

        if not response.data:
            return AnalysisJobListResponse(jobs=[])
            
        job_list_processed = []
        for item in response.data:
            snippet = item.get("job_description_text", "")
            if snippet and len(snippet) > 100: snippet = snippet[:100] + "..."
            
            cv_info = item.get("user_cvs")
            cv_file_name = cv_info.get("file_name") if cv_info else None
            
            job_list_processed.append(
                AnalysisJobListItem(
                    id=item["id"],
                    cv_file_name=cv_file_name,
                    job_description_snippet=snippet,
                    status=item["status"],
                    created_at=item["created_at"]
                )
            )
        
        return AnalysisJobListResponse(jobs=job_list_processed)
        
    except Exception as e:
        print(f"HATA: Analiz iş listesi alınamadı: {e}")
        raise HTTPException(status_code=500, detail="Analiz iş listesi alınırken bir sunucu hatası oluştu.")

@router.get("/status/{task_id}", response_model=AnalysisTaskStatusResponse)
async def get_analysis_status(task_id: uuid.UUID, user: User = Depends(get_current_user)):
    """
    Giriş yapmış kullanıcının BELİRLİ bir analiz işinin durumunu ve sonucunu sorgular.
    """
    try:
        # RLS + explicit user_id check
        response = supabase.table("analysis_jobs").select("status, result").eq("id", str(task_id)).eq("user_id", str(user.id)).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Görev bulunamadı veya bu kullanıcıya ait değil.")
        
        job_data = response.data[0]
        job_data["task_id"] = task_id
        
        # 'result' (JSONB) alanını doğrula
        if job_data.get("result"):
            if 'error' in job_data["result"]: # Arka plan görevinde hata oluşmuşsa
                 job_data["result"] = None
            else:
                 # Veritabanından gelen dict'i FullAnalysisResponse Pydantic modeline doğrula
                job_data["result"] = FullAnalysisResponse.model_validate(job_data["result"])

        # Tüm yanıtı AnalysisTaskStatusResponse Pydantic modeline doğrula
        return AnalysisTaskStatusResponse.model_validate(job_data)
        
    except ValidationError as e:
        print(f"HATA: Sonuç validasyonu başarısız: {e}")
        raise HTTPException(status_code=500, detail="Analiz sonucu veritabanında, ancak beklenen formata uymuyor.")
    except Exception as e:
        print(f"HATA: Görev durumu alınamadı: {e}")
        raise HTTPException(status_code=500, detail="Görev durumu alınırken bir hata oluştu.")

@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_analysis_job(task_id: uuid.UUID, user: User = Depends(get_current_user)):
    """
    Giriş yapmış kullanıcının BELİRLİ bir analiz işini siler.
    (RLS politikası sayesinde sadece kendi işini silebilir)
    """
    try:
        response = supabase.table("analysis_jobs").delete().eq(
            "id", str(task_id)
        ).eq( 
            "user_id", str(user.id) # Katmanlı savunma
        ).execute()

        # 'ON DELETE CASCADE' ayarlanmadıysa ve bu işe bağlı veri varsa hata verebilir.
        # Şimdilik basit tutuyoruz.
        print(f"Bilgi: Analiz işi ({task_id}) silindi (veya zaten yoktu/başkasına aitti).")

    except Exception as e:
        print(f"HATA: Analiz işi silinemedi ({task_id}): {e}")
        raise HTTPException(status_code=500, detail="Analiz işi silinirken bir sunucu hatası oluştu.")