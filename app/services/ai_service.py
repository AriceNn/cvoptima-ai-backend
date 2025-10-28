# app/services/ai_service.py

import google.generativeai as genai
import json # <--- DÜZELTME İÇİN GEREKLİ IMPORT
from fastapi import HTTPException, status
from app.schemas.analysis_schema import FullAnalysisResponse # Pydantic modelimiz
from app.core.config import get_settings

# --- 1. Yapılandırma ---
try:
    settings = get_settings()
    genai.configure(api_key=settings.GOOGLE_API_KEY)
except Exception as e:
    print(f"HATA: Google Gemini API yapılandırılamadı. .env dosyasını kontrol edin. Hata: {e}")


def get_system_prompt_for_json_schema() -> str:
    """
    AI'a JSON şemasını ve temel kimliğini veren 
    sistem talimatını (system instruction) oluşturur.
    """
    
    # --- MİMARİ DÜZELTME: .schema_json() yerine .model_json_schema() ---
    # Pydantic V2 (modern) .model_json_schema() kullanır ve bir 'dict' döndürür.
    schema_dict = FullAnalysisResponse.model_json_schema()
    
    # Bu 'dict'i, prompt'a eklemek için 'json.dumps' ile formatlı bir JSON metnine dönüştürüyoruz.
    schema_string = json.dumps(schema_dict, indent=2, ensure_ascii=False) # ensure_ascii=False, Türkçe karakterleri korur
    
    SYSTEM_PROMPT = f"""
Sen, dünya standartlarında bir kıdemli İK yöneticisi ve kariyer koçusun. Görevin, bir kullanıcının CV'sini (Özgeçmiş)
ve başvurduğu iş ilanını (İş Tanımı) analiz ederek kapsamlı bir iyileştirme raporu oluşturmaktır.

Çıktın *sadece* ve *sadece* geçerli bir JSON nesnesi olmalıdır.
Bu JSON nesnesi, aşağıda sana verilen JSON şemasına *harfiyen* uymalıdır.
Asla JSON dışında bir metin, açıklama, "İşte JSON:" gibi bir giriş veya
```json ... ``` gibi markdown etiketleri kullanma.

--- İSTENEN JSON ŞEMASI ---
{schema_string}
--- JSON ŞEMASI BİTTİ ---

Analiz adımların:
1.  **İş İlanı Analizi (job_keywords):** İş ilanını dikkatlice oku. İlanda talep edilen temel teknik becerileri (hard_skills)
    ve sosyal becerileri (soft_skills) çıkar.
2.  **CV Analizi (cv_keywords):** Kullanıcının CV'sini oku. CV'de vurgulanan teknik ve sosyal becerileri çıkar.
3.  **Eksik Analizi (gap_analysis):** İki listeyi karşılaştır.
    - `matching_skills`: Hem ilanda hem CV'de olan ortak beceriler.
    - `missing_skills`: İlanda açıkça istenen ama CV'de bulunmayan veya yeterince vurgulanmayan beceriler.
4.  **Öneriler (suggestions):** CV'yi ilana daha uygun hale getirmek için 3 ila 5 adet *spesifik* ve *eyleme geçirilebilir*
    öneri oluştur. Öneriler genel olmamalı (örn: 'Becerilerinizi ekleyin'). 
    Spesifik olmalı (örn: 'Başlık: Proje Yönetimi Deneyimini Vurgula', 'Detay: İş ilanında 'Agile' tecrübesi isteniyor. 
    CV'nizdeki 'X Projesi' deneyiminize 'Agile metodolojileri kullanarak 3 ayda tamamlandı' gibi bir ibare ekleyin.', 
    'Örnek: 'X Projesi (Agile) - ...'').
5.  **Ön Yazı Taslağı (cover_letter_draft):** Kullanıcının CV'sindeki güçlü yönleri ve iş ilanındaki talepleri 
    birleştiren, profesyonel, ikna edici ve kısa bir ön yazı taslağı oluştur.
"""
    return SYSTEM_PROMPT

# --- 2. Model Kurulumu (Modern Yöntem) ---
try:
    SYSTEM_INSTRUCTION = get_system_prompt_for_json_schema()
    
    GENERATION_CONFIG = {
        "response_mime_type": "application/json",
        "temperature": 0.1,
    }
    
    model = genai.GenerativeModel(
        model_name='gemini-2.5-flash', # Kullandığınız model
        system_instruction=SYSTEM_INSTRUCTION,
        generation_config=GENERATION_CONFIG
    )
except Exception as e:
    print(f"HATA: Gemini modeli yüklenemedi. Model adı veya yapılandırma hatalı olabilir. Hata: {e}")
    model = None

# --- 3. Servis Fonksiyonu (Senkron) ---
def run_full_analysis(cv_text: str, job_description_text: str) -> FullAnalysisResponse:
    """
    Verilen CV ve İş Tanımı metinleri için tam AI analizini Gemini ile SENKRON olarak çalıştırır.
    """
    
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI modeli yüklenemedi. Lütfen sunucu loglarını kontrol edin."
        )

    try:
        user_prompt = f"""
İşte analiz etmen gereken dokümanlar:

--- İŞ TANIMI (Job Description) ---
{job_description_text}
--- İŞ TANIMI BİTTİ ---

--- CV (Özgeçmiş) ---
{cv_text}
--- CV BİTTİ ---

Lütfen analizini sadece sağlanan JSON şemasına uygun olarak yap.
"""
        
        print("Gemini API'ye (senkron) istek gönderiliyor...")
        response = model.generate_content(user_prompt)
        print("Gemini API'den yanıt alındı.")

        # --- YENİ AJAN LOG 3 (HAM YANIT) ---
        print("--- DEBUG: GEMINI'DEN GELEN HAM YANIT ---")
        print(response.text)
        print("---------------------------------------")
        # --- BİTTİ ---
        
        response_json = json.loads(response.text)
        validated_response = FullAnalysisResponse.model_validate(response_json)
        
        return validated_response

    except json.JSONDecodeError:
        print(f"HATA: Gemini API geçerli bir JSON dönmedi. Dönen metin: {response.text}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Yapay zeka geçerli bir formatta yanıt vermedi. Lütfen tekrar deneyin."
        )
    except Exception as e:
        print(f"AI Servis Hatası (Gemini): {e}") 
        
        if 'safety' in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="İçerik güvenlik filtreleri tarafından engellendi. Lütfen girdilerinizi kontrol edin."
            )
            
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Yapay zeka analizi sırasında bir hata oluştu: {str(e)}"
        )