from fastapi import (
    APIRouter, 
    UploadFile, 
    File, 
    HTTPException, 
    status,
    Depends 
)
from app.services.parser_service import parse_document_to_text 
from app.core.supabase_client import get_supabase_client
from pydantic import BaseModel
import uuid
from app.core.security import get_current_user 
from gotrue.types import User 
from app.schemas.analysis_schema import CVListResponse, CVListItem 
from typing import List
from app.schemas.analysis_schema import CVDetailResponse
from app.schemas.analysis_schema import CVDownloadURLResponse
from app.core.short_code_generator import generate_unique_short_code
from datetime import datetime, timedelta, timezone # Zaman hesaplaması için
from fastapi.responses import RedirectResponse

router = APIRouter(
    prefix="/cv",
    tags=["CV Management (Kilitli)"]
)

supabase = get_supabase_client()

class CVUploadResponse(BaseModel):
    """CV yüklendiğinde kullanıcıya dönen yanıt modeli."""
    cv_id: uuid.UUID
    file_name: str
    message: str

@router.post("/upload", response_model=CVUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_cv(
    # FastAPI, bu endpoint'i çağırmadan önce get_current_user'ı çalıştırır.
    # Eğer token yoksa/geçersizse, bu fonksiyon 401 hatası verir ve
    # aşağıdaki kod HİÇ ÇALIŞMAZ.
    # Eğer token geçerliyse, 'user' değişkeni dolu gelir.
    user: User = Depends(get_current_user), 
    file: UploadFile = File(...)
):
    """
    KİMLİĞİ DOĞRULANMIŞ kullanıcı için yeni bir CV (.pdf veya .docx) yükler.
    
    1. Dosyayı metne ayrıştırır (parse) (OCR dahil).
    2. Orijinal dosyayı Supabase Storage'a yükler.
    3. Dosya yolu, adı, ayrıştırılmış metin ve 'user_id'yi 'user_cvs' tablosuna kaydeder.
    4. Kullanıcıya bu CV için kullanılacak olan 'cv_id'yi döndürür.
    """
    
    # Dosya içeriğini 'bytes' olarak oku
    try:
        file_content = await file.read()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dosya okunurken hata oluştu: {str(e)}"
        )
    
    # 1. Dosyayı metne ayrıştır (Bu, OCR nedeniyle 1-15 saniye sürebilir)
    try:
        parsed_text = await parse_document_to_text(file_content, file.filename)
    except HTTPException as he:
        # parser_service'den gelen (415, 400, 500) hataları yansıt
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Dosya ayrıştırma sırasında beklenmedik hata: {str(e)}"
        )
        
    # 2. Dosya için benzersiz bir depolama yolu (path) oluştur
    try:
        file_extension = f".{file.filename.split('.')[-1]}"
    except IndexError:
        file_extension = ""
        
    unique_file_name = f"{uuid.uuid4()}{file_extension}"
    
    # Mimari Not: Dosyaları 'user.id'ye göre klasörlemek en iyi pratiktir.
    storage_file_path = f"{user.id}/{unique_file_name}"
    
    # 3. Dosyanın orijinal 'bytes' içeriğini Supabase Storage'a yükle
    try:
        print(f"Bilgi: Orijinal dosya Supabase Storage'a yükleniyor: {storage_file_path}")
        
        supabase.storage.from_("user_uploads").upload(
            path=storage_file_path,
            file=file_content,
            file_options={"content-type": file.content_type}
        )
        print("Bilgi: Orijinal dosya Storage'a yüklendi.")
    except Exception as e:
        print(f"HATA: Supabase Storage'a yüklenemedi: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Dosya depolama alanına (Storage) yüklenirken hata oluştu: {str(e)}"
        )
        
    # 4. Veriyi 'user_cvs' tablosuna kaydet
    try:
        data_to_insert = {
            "file_name": file.filename,          # Orijinal adı
            "cv_text_content": parsed_text,      # OCR'dan gelen metin
            "file_path": storage_file_path,      # Storage'daki yolu
            "user_id": str(user.id)              # <-- FAZ 3 GÜNCELLEMESİ
        }
        
        print(f"DEBUG: (Kullanıcı: {user.id}) Supabase'e gönderilen veri: {data_to_insert}")
            
        response = supabase.table("user_cvs").insert(data_to_insert).execute()
        
        if not response.data or len(response.data) == 0:
             raise Exception("Veritabanına kayıt başarısız oldu, veri dönmedi.")
                
        new_cv = response.data[0]
        new_cv_id = new_cv.get("id")

        return CVUploadResponse(
            cv_id=new_cv_id,
            file_name=file.filename,
            message="CV başarıyla yüklendi, işlendi ve depolandı."
        )

    except Exception as e:
        print(f"HATA: CV veritabanına kaydedilemedi: {e}")
        # Mimari Not (Gelecek): Burada bir "rollback" (geri alma) mantığı
        # olmalı ve Storage'a yüklenen 'storage_file_path' silinmelidir.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"CV veritabanına kaydedilirken bir hata oluştu: {str(e)}"
        )
    
    # --- FAZ 4 YENİ ENDPOINT ---
@router.get("", response_model=CVListResponse) # URL prefix'i zaten /cv olduğu için "" yeterli
async def list_user_cvs(
    user: User = Depends(get_current_user) # <-- GÜVENLİK: Sadece giriş yapmış kullanıcı
):
    """
    Giriş yapmış kullanıcının yüklediği tüm CV'leri listeler.
    En yeniden eskiye doğru sıralar.
    """
    try:
        # Supabase veritabanından SADECE gerekli sütunları seçiyoruz
        # RLS politikası sayesinde otomatik olarak SADECE bu kullanıcıya ait olanlar gelecek
        response = supabase.table("user_cvs").select(
            "id, file_name, created_at" # Metin içeriğini (cv_text_content) çekmiyoruz!
        ).eq( 
            "user_id", str(user.id) # RLS zaten filtreliyor ama burada belirtmek "defense in depth"
        ).order(
            "created_at", desc=True # En yeniden eskiye sırala (iyi UX)
        ).execute()

        if not response.data:
            # Kullanıcının hiç CV'si yoksa boş liste döndür, hata verme
            return CVListResponse(cvs=[])
            
        # Veritabanı yanıtını Pydantic modelimize uygun hale getir
        cv_list = [CVListItem.model_validate(item) for item in response.data]
        
        return CVListResponse(cvs=cv_list)

    except Exception as e:
        print(f"HATA: CV listesi alınamadı: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CV listesi alınırken bir sunucu hatası oluştu."
        )
    
@router.get("/{cv_id}", response_model=CVDetailResponse)
async def get_cv_details(
    cv_id: uuid.UUID, # URL'den gelen CV ID'sini alır (FastAPI otomatik doğrular)
    user: User = Depends(get_current_user) # <-- GÜVENLİK: Sadece giriş yapmış kullanıcı
):
    """
    Giriş yapmış kullanıcının BELİRLİ bir CV'sinin detaylarını getirir.
    Sadece kullanıcının KENDİ CV'sine erişebilir.
    """
    try:
        # Veritabanından BELİRTİLEN cv_id'ye ve GİRİŞ YAPAN user_id'ye sahip
        # TEK BİR satırı seçiyoruz.
        # RLS politikası zaten filtreliyor, ancak 'eq("user_id", ...)' eklemek
        # hem daha güvenli (defense in depth) hem de kodun niyetini netleştirir.
        response = supabase.table("user_cvs").select(
            "id, file_name, created_at, file_path, cv_text_content" # Tüm detayları çekiyoruz
        ).eq(
            "id", str(cv_id)
        ).eq(
            "user_id", str(user.id)
        ).maybe_single().execute() # '.single()' -> Tam 1 satır bekler, yoksa hata verir. '.maybe_single()' -> 0 veya 1 satır döner, hata vermez.

        # Eğer .maybe_single() 'None' döndürdüyse (yani satır yoksa veya kullanıcıya ait değilse)
        if response.data is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="CV bulunamadı veya bu kullanıcıya ait değil."
            )
            
        # Veritabanı yanıtını Pydantic modelimize doğrula ve döndür
        return CVDetailResponse.model_validate(response.data)

    except HTTPException as he:
        # 404 hatasını doğrudan yansıt
        raise he
    except Exception as e:
        print(f"HATA: CV detayı alınamadı ({cv_id}): {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CV detayı alınırken bir sunucu hatası oluştu."
        )
    
@router.delete("/{cv_id}", status_code=status.HTTP_204_NO_CONTENT) # Başarılı silmede 204 döndür
async def delete_user_cv(
    cv_id: uuid.UUID,
    user: User = Depends(get_current_user) # <-- GÜVENLİK: Sadece giriş yapmış kullanıcı
):
    """
    Giriş yapmış kullanıcının BELİRLİ bir CV'sini siler.
    Sadece kullanıcının KENDİ CV'sini silebilir.
    Hem veritabanı kaydını hem de Storage'daki dosyayı siler.
    """
    try:
        # 1. CV'nin varlığını ve sahipliğini doğrula, AYNI ZAMANDA file_path'i al
        #    Tek bir DB sorgusu ile ikisini birden yapalım.
        select_response = supabase.table("user_cvs").select(
            "id, file_path" # Sadece dosya yoluna ihtiyacımız var
        ).eq(
            "id", str(cv_id)
        ).eq(
            "user_id", str(user.id)
        ).maybe_single().execute()

        # Eğer CV yoksa veya kullanıcıya ait değilse
        if select_response.data is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Silinecek CV bulunamadı veya bu kullanıcıya ait değil."
            )
            
        cv_data = select_response.data
        file_path_to_delete = cv_data.get("file_path")

        # 2. Storage'daki dosyayı sil (EĞER file_path varsa)
        if file_path_to_delete:
            try:
                print(f"Bilgi: Supabase Storage'dan dosya siliniyor: {file_path_to_delete}")
                # Supabase V2 Storage silme syntax'ı: .remove() bir liste alır
                supabase.storage.from_("user_uploads").remove([file_path_to_delete])
                print("Bilgi: Storage dosyası silindi.")
            except Exception as storage_exc:
                # Mimari Karar: Storage silme başarısız olursa ne yapmalı?
                # Şimdilik: Hatayı logla ama DB silmeye DEVAM ET (en azından DB temizlensin).
                # Daha sağlam bir sistemde: Belki işlemi durdur veya tekrar dene.
                print(f"UYARI: Storage dosyası ({file_path_to_delete}) silinemedi: {storage_exc}")
        else:
             print(f"UYARI: CV ({cv_id}) için 'file_path' bulunamadı, Storage silme atlandı.")


        # 3. Veritabanındaki CV kaydını sil
        #    Doğrudan 'id' ve 'user_id' ile silmeyi deneyebiliriz.
        print(f"Bilgi: Veritabanından CV kaydı siliniyor: {cv_id}")
        delete_response = supabase.table("user_cvs").delete().eq(
            "id", str(cv_id)
        ).eq( 
            "user_id", str(user.id) # İkinci güvenlik katmanı (RLS zaten koruyor)
        ).execute()

        # Silme işlemi genelde data döndürmez ama hata vermemeli
        # Belki 'count' kontrol edilebilir ama RLS varsa emin olamayız.
        print(f"Bilgi: Veritabanı kaydı silindi (veya zaten yoktu/başkasına aitti).")

        # Başarılı silme durumunda 204 No Content otomatik dönecektir.

    except HTTPException as he:
        # 404 hatasını yansıt
        raise he
    except Exception as e:
        print(f"HATA: CV silinemedi ({cv_id}): {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CV silinirken bir sunucu hatası oluştu."
        )
    
@router.get("/{cv_id}/download", response_model=CVDownloadURLResponse)
async def get_cv_download_url(
    cv_id: uuid.UUID,
    user: User = Depends(get_current_user)

):
    """
    Giriş yapmış kullanıcının BELİRLİ bir CV'sinin orijinal dosyasını indirmesi
    için KISA KOD ve geçerlilik süresi oluşturur.
    Sadece kullanıcının KENDİ CV'sine erişebilir.
    """
    URL_EXPIRATION_SECONDS = 60

    try:
        # 1. CV'nin varlığını, sahipliğini doğrula ve file_path'i al
        select_response = supabase.table("user_cvs").select(
            "id, file_path"
        ).eq(
            "id", str(cv_id)
        ).eq(
            "user_id", str(user.id)
        ).maybe_single().execute()

        if select_response.data is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="İndirilecek CV bulunamadı veya bu kullanıcıya ait değil."
            )

        cv_data = select_response.data
        file_path = cv_data.get("file_path")

        if not file_path:
             raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="CV kaydı bulundu ancak ilişkili dosya yolu (file_path) mevcut değil."
            )

        # 2. Supabase Storage'dan UZUN imzalı URL oluştur
        try:
            print(f"Bilgi: Uzun imzalı URL oluşturuluyor: {file_path}")
            signed_url_response = supabase.storage.from_("user_uploads").create_signed_url(
                path=file_path,
                expires_in=URL_EXPIRATION_SECONDS
            )
            original_signed_url = signed_url_response.get('signedURL')
            if not original_signed_url:
                 raise Exception("Supabase'den uzun imzalı URL alınamadı.")
            print("Bilgi: Uzun imzalı URL oluşturuldu.")

        except Exception as storage_exc:
            print(f"HATA: Uzun imzalı URL oluşturulamadı ({file_path}): {storage_exc}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Dosya indirme linki oluşturulurken bir depolama hatası oluştu."
            )

        # 3. Benzersiz bir KISA KOD üret
        try:
            short_code = await generate_unique_short_code()
            print(f"Bilgi: Benzersiz kısa kod üretildi: {short_code}")
        except Exception as code_exc:
             print(f"HATA: Benzersiz kısa kod üretilemedi: {code_exc}")
             raise HTTPException(
                 status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail="Kısa indirme linki oluşturulamadı."
             )

        # 4. Son kullanma tarihini hesapla (UTC olarak)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=URL_EXPIRATION_SECONDS)

        # 5. Kısaltılmış URL bilgilerini DB'ye kaydet
        try:
            insert_data = {
                "user_id": str(user.id),
                "cv_id": str(cv_id),
                "short_code": short_code,
                "original_signed_url": original_signed_url,
                "expires_at": expires_at.isoformat() # ISO formatında string olarak kaydet
            }
            response = supabase.table("shortened_urls").insert(insert_data).execute()
            if not response.data:
                raise Exception("Kısaltılmış URL kaydı başarısız.")
            print("Bilgi: Kısaltılmış URL DB'ye kaydedildi.")
        except Exception as db_exc:
            print(f"HATA: Kısaltılmış URL kaydedilemedi: {db_exc}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Kısa indirme linki kaydedilirken hata oluştu."
            )

        # 6. Kullanıcıya SADECE KISA KODU ve geçerlilik süresini döndür
        return CVDownloadURLResponse(
            short_code=short_code,      # <-- Doğru alan adı
            expires_in=URL_EXPIRATION_SECONDS
        )

    except HTTPException as he:
        # 404 gibi bilerek fırlatılanları yansıt
        raise he
    except Exception as e:
        # Diğer beklenmedik hatalar
        print(f"HATA: CV indirme URL'si alınamadı ({cv_id}): {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CV indirme linki alınırken bir sunucu hatası oluştu."
        )