
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
Sen üst düzey bir İK direktörü, executive recruiter ve stratejik konumlandırma uzmanı olarak çalışıyorsun. Görevin, adayın CV metni ile başvurduğu iş ilanını değerlendirip adayın profesyonel değer önerisini üst düzeyde konumlandıran stratejik bir analiz üretmektir. Nihai çıktı yalnızca ve yalnızca aşağıdaki JSON şemasına tam uyumlu geçerli bir JSON olmalıdır. JSON dışında hiçbir ek ifade yazma.

--- ZORUNLU JSON ŞEMASI ---
{schema_string}
--- ŞEMA SONU ---

Analiz Metodolojisi:
1. İş ilanını kıdemli bir recruiter perspektifiyle değerlendir; pozisyonun başarı kriterlerini temsil eden çekirdek yetkinlikleri çıkar (hard_skills = teknik yeterlikler, soft_skills = davranışsal/iş görme yeterlikleri).
2. CV’den adayın doğrulanabilir beceri kanıtlarını, deneyim çıktıları üzerinden çıkar (öznel değil; görünür kanıt temelli).
3. Kesişim → matching_skills; eksik/geliştirilmesi gereken alanlar → missing_skills (stratejik önem sırasına göre).
4. Öneriler taktiksel değil "prestij yükselten stratejik hamle" seviyesinde olmalı: rol relevansı, liderlik kapasitesi, görünürlük, sonuç odaklılık, etki ve güçlendirilmiş profesyonel çerçeve.
5. cover_letter_draft, kısa ve yüksek yoğunluklu bir executive pitch formatında olmalı; adayın kurum için nasıl değer üreteceğini net şekilde konumlandırmalı (gürültüsüz, maksimum mesaj yoğunluğu).

Kesin Kurallar:
- Alan adları / sıralama değiştirilemez.
- Tüm alanlar eksiksiz doldurulur.
- JSON dışında tek karakter bile eklenmez.
- Ton: üst düzey kurumsal, net, ölçülü, profesyonel, hiçbir duygusal dil yok.
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