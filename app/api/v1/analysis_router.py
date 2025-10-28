from fastapi import (
    APIRouter, 
    BackgroundTasks, 
    HTTPException, 
    status, 
    Depends
)
from pydantic import ValidationError 
from app.schemas.analysis_schema import (
    AnalysisRequest, 
    AnalysisTaskStartResponse, 
    AnalysisTaskStatusResponse,
    FullAnalysisResponse
)
from app.services.ai_service import run_full_analysis
from app.core.supabase_client import get_supabase_client
import uuid
from typing import Dict, Any
from app.core.security import get_current_user 
from gotrue.types import User
from app.schemas.analysis_schema import AnalysisJobListResponse, AnalysisJobListItem 
from typing import List
from datetime import datetime

router = APIRouter(
    prefix="/analysis",
    tags=["Analysis (Kilitli)"] # Tag'i güncelledim
)

# Supabase istemcisini al
supabase = get_supabase_client()

def run_analysis_background_task(task_id: uuid.UUID, cv_id: uuid.UUID, job_description_text: str, user_id: uuid.UUID):
    """
    Arka planda çalışacak olan *senkron* görev.
    1. DB'den KULLANICIYA AİT CV metnini çeker.
    2. AI analizini çalıştırır.
    3. DB'deki 'analysis_jobs' satırını 'completed' veya 'failed' olarak günceller.
    """
    try:
        print(f"Arka plan görevi {task_id} (Kullanıcı: {user_id}) başladı...")
        
        # 1. DB'den CV metnini çek
        # --- GÜVENLİK KONTROLÜ (Savunma Katmanı 1) ---
        # Sadece o kullanıcıya ait olan o CV'yi seç
        cv_response = supabase.table("user_cvs").select("cv_text_content").eq("id", str(cv_id)).eq("user_id", str(user_id)).execute()
        
        if not cv_response.data:
            raise Exception(f"CV ID ({cv_id}) bulunamadı veya kullanıcıya ({user_id}) ait değil.")
            
        cv_text = cv_response.data[0].get("cv_text_content")

        # --- YENİ AJAN LOG 1 (GİRDİ KONTROLÜ) ---
        print("--- DEBUG: AI'A GONDERILEN GIRDILER ---")
        print(f"CV METNI (ilk 200 karakter): {cv_text[:200]}...")
        print(f"IS ILANI (ilk 200 karakter): {job_description_text[:200]}...")
        print("-----------------------------------")
        # --- BİTTİ ---

        if not cv_text:
            raise Exception(f"CV ID'si {cv_id} için 'cv_text_content' boş.")

        # 2. AI analizini çalıştır (Bu, 10-30 saniye süren yavaş kısımdır)
        analysis_result: FullAnalysisResponse = run_full_analysis(cv_text, job_description_text)

        # --- YENİ AJAN LOG 2 (ÇIKTI KONTROLÜ) ---
        analysis_result_dict = analysis_result.model_dump()
        print("--- DEBUG: DB'YE YAZILACAK VERI ---")
        print(analysis_result_dict)
        print("----------------------------------")
        # --- BİTTİ ---
        
        # 3. Görev tamamlandığında 'analysis_jobs' tablosunu güncelle
        supabase.table("analysis_jobs").update({
            "status": "completed",
            "result": analysis_result.model_dump() # Pydantic V2
        }).eq("id", str(task_id)).execute()
        
        print(f"Arka plan görevi {task_id} tamamlandı.")

    except Exception as e:
        print(f"Arka plan görevi {task_id} başarısız oldu: {e}")
        # Hata durumunda 'analysis_jobs' tablosunu güncelle
        supabase.table("analysis_jobs").update({
            "status": "failed",
            "result": {"error": str(e)} 
        }).eq("id", str(task_id)).execute()


@router.post("/start", response_model=AnalysisTaskStartResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_analysis(
    request: AnalysisRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user) # <-- FAZ 3 GÜVENLİK KİLİDİ
):
    """
    KİMLİĞİ DOĞRULANMIŞ kullanıcı için yeni bir analiz görevi başlatır.
    1. 'analysis_jobs' tablosuna 'pending' ve 'user_id' ile yeni bir satır ekler.
    2. Ağır işi (AI analizi) arka plana atar.
    3. Kullanıcıya anında 'task_id' (job'un UUID'si) döner.
    """
    try:
        # 1. 'analysis_jobs' tablosuna YENİ BİR GÖREV SATIRI ekle
        new_job_data = {
            "cv_id": str(request.cv_id),
            "job_description_text": request.job_description_text,
            "status": "pending",
            "user_id": str(user.id) # <-- FAZ 3 GÜNCELLEMESİ
        }
        
        response = supabase.table("analysis_jobs").insert(new_job_data).execute()
        
        if not response.data or len(response.data) == 0:
            raise Exception("Veritabanına 'job' kaydı başarısız oldu, veri dönmedi.")
            
        new_task = response.data[0]
        task_id = new_task.get("id")
        
        # Pydantic validasyonunu 'return' etmeden önce yap
        try:
            response_model = AnalysisTaskStartResponse(task_id=task_id, status="pending")
        except ValidationError as e:
            print(f"HATA: Pydantic validasyonu başarısız: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Veritabanından dönen task_id ({task_id}) geçerli bir UUID değil. Veritabanı şemasını (Adım 2.2) kontrol edin."
            )
        
        # 2. Arka plan görevine 'user.id'yi de yolla (güvenlik için)
        background_tasks.add_task(
            run_analysis_background_task, 
            task_id, 
            request.cv_id, 
            request.job_description_text,
            user.id # <-- FAZ 3 GÜNCELLEMESİ
        )
        
        # 3. Kullanıcıya doğrulanmış modeli dön
        return response_model

    except HTTPException as he:
        # Pydantic hatasını veya diğerlerini tekrar fırlat
        raise he
    except Exception as e:
        # Bu, genellikle 'cv_id'nin bulunamaması (Foreign Key violation) hatasıdır.
        print(f"HATA: Analiz başlatılamadı: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analiz başlatılırken bir hata oluştu. CV ID ({request.cv_id}) bulunamadı veya bu kullanıcıya ait değil."
        )


@router.get("/status/{task_id}", response_model=AnalysisTaskStatusResponse)
async def get_analysis_status(
    task_id: uuid.UUID,
    user: User = Depends(get_current_user) # <-- FAZ 3 GÜVENLİK KİLİDİ
):
    """
    Verilen task_id'ye sahip analizin durumunu sorgular.
    SADECE O GÖREVİ BAŞLATAN KULLANICI sorgulayabilir.
    """
    try:
        # --- GÜVENLİK KONTROLÜ (Savunma Katmanı 2) ---
        # Veritabanından o 'task_id'yi VE o 'user_id'yi seç
        response = supabase.table("analysis_jobs").select("status, result").eq("id", str(task_id)).eq("user_id", str(user.id)).execute()
        
        if not response.data:
            # Eğer veri yoksa, bunun iki sebebi vardır:
            # 1. Görev ID'si gerçekten yoktur.
            # 2. Görev ID'si vardır, ama BU KULLANICIYA AİT DEĞİLDİR.
            # Her iki durumda da 404 dönmek, en güvenli yoldur.
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Görev bulunamadı veya bu kullanıcıya ait değil.")
        
        job_data = response.data[0]

        # --- YENİ AJAN LOG (OKUMA KONTROLÜ) ---
        print("--- DEBUG: DB'DEN OKUNAN HAM VERI ---")
        print(f"Tip (job_data['result']): {type(job_data.get('result'))}")
        print(f"Icerik (job_data['result']): {job_data.get('result')}")
        print("-----------------------------------")
        # --- BİTTİ ---
        
        # Pydantic şemasının validasyonundan geçirmek için 'task_id'yi ekle
        job_data["task_id"] = task_id
        
        # 'result' alanı 'None' değilse (yani 'completed' ise),
        # Pydantic'in onu FullAnalysisResponse'a dönüştürmesini sağla
        if job_data.get("result"):
            if 'error' in job_data["result"]:
                 job_data["result"] = None
            else:
                job_data["result"] = FullAnalysisResponse.model_validate(job_data["result"])

        return AnalysisTaskStatusResponse.model_validate(job_data)

    except ValidationError as e:
        # Eğer 'result'taki JSON, FullAnalysisResponse şemasına uymazsa
        print(f"HATA: Sonuç validasyonu başarısız: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Analiz sonucu veritabanında, ancak beklenen formata uymuyor."
        )
    except Exception as e:
        print(f"HATA: Görev durumu alınamadı: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Görev durumu alınırken bir hata oluştu."
        )
    
@router.get("", response_model=AnalysisJobListResponse)
async def list_user_analysis_jobs(
    user: User = Depends(get_current_user) # <-- GÜVENLİK: Sadece giriş yapmış kullanıcı
):
    """
    Giriş yapmış kullanıcının başlattığı tüm analiz işlerini listeler.
    En yeniden eskiye doğru sıralar. İlişkili CV'nin dosya adını da getirir.
    """
    try:
        # Supabase JOIN Syntax: select("*, table_name(column_name)")
        # RLS politikası sayesinde otomatik olarak SADECE bu kullanıcıya ait işler gelecek.
        response = supabase.table("analysis_jobs").select(
            "id, job_description_text, status, created_at, user_cvs(file_name)" # JOIN burada: user_cvs tablosundan file_name'i çek
        ).eq(
            "user_id", str(user.id) # Katmanlı savunma
        ).order(
            "created_at", desc=True # En yeniden eskiye sırala
        ).execute()

        if not response.data:
            return AnalysisJobListResponse(jobs=[])
            
        # Veritabanı yanıtını Pydantic modelimize uygun hale getir
        job_list_processed = []
        for item in response.data:
            # İş ilanının özetini oluştur (ilk 100 karakter + ...)
            snippet = item.get("job_description_text", "")
            if snippet and len(snippet) > 100:
                snippet = snippet[:100] + "..."
                
            # JOIN'dan gelen CV verisini ayıkla
            cv_info = item.get("user_cvs") # Bu bir dict {'file_name': '...'} veya None olabilir
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Analiz iş listesi alınırken bir sunucu hatası oluştu."
        )

@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_analysis_job(
    task_id: uuid.UUID,
    user: User = Depends(get_current_user) # <-- GÜVENLİK: Sadece giriş yapmış kullanıcı
):
    """
    Giriş yapmış kullanıcının BELİRLİ bir analiz işini siler.
    Sadece kullanıcının KENDİ analiz işini silebilir.
    """
    try:
        response = supabase.table("analysis_jobs").delete().eq(
            "id", str(task_id)
        ).eq( 
            "user_id", str(user.id) # İkinci güvenlik katmanı
        ).execute()

        print(f"Bilgi: Analiz işi ({task_id}) silindi (veya zaten yoktu/başkasına aitti).")

    except Exception as e:
        print(f"HATA: Analiz işi silinemedi ({task_id}): {e}")
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Analiz işi silinirken bir sunucu hatası oluştu."
        )