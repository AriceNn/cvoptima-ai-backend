# app/services/parser_service.py
import pdfplumber
import docx
import io
from fastapi import HTTPException, status

# --- YENİ İMPORTLAR (OCR İÇİN) ---
from pdf2image import convert_from_bytes
import pytesseract
from PIL import Image
# --- BİTTİ ---

async def parse_text_with_pdfplumber(file_content: bytes) -> str:
    """Plan A (Hızlı Yol): Dijital PDF'ten metin çıkarmayı dener."""
    text_content = ""
    try:
        with io.BytesIO(file_content) as pdf_file:
            with pdfplumber.open(pdf_file) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_content += page_text + "\n"
    except Exception as e:
        print(f"Pdfplumber hatası: {e}") # Sadece logla, programı durdurma
        return "" # Hata olursa boş döndür, OCR denesin
    return text_content.strip()

async def parse_text_with_ocr(file_content: bytes) -> str:
    """Plan B (Yavaş Yol): PDF'i resme dönüştürür ve OCR uygular."""
    text_content = ""
    try:
        # 1. PDF 'bytes'larını PIL Image (resim) listesine dönüştür
        # poppler'ın sistemde kurulu olmasını gerektirir
        images = convert_from_bytes(file_content)
        
        # 2. Her bir resim (sayfa) üzerinde OCR çalıştır
        for img in images:
            # Türkçe ('tur') ve İngilizce ('eng') dillerini tanımasını söyle
            # Tesseract'ın bu dilleri bulabilmesi için 'brew install tesseract-lang' gerekir
            try:
                page_text = pytesseract.image_to_string(img, lang='tur+eng')
                if page_text:
                    text_content += page_text + "\n"
            except pytesseract.TesseractNotFoundError:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Tesseract OCR motoru sistemde bulunamadı. 'brew install tesseract' yapıldı mı?"
                )
    except Exception as e:
        # pdf2image hatası (örn: poppler kurulu değil) veya Tesseract hatası
        print(f"OCR Hatası: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OCR ayrıştırması sırasında beklenmedik hata: {str(e)}"
        )
    return text_content.strip()

async def parse_docx(file_content: bytes) -> str:
    """DOCX dosyalarını ayrıştırır."""
    text_content = ""
    try:
        with io.BytesIO(file_content) as docx_file:
            doc = docx.Document(docx_file)
            for para in doc.paragraphs:
                if para.text:
                    text_content += para.text + "\n"
    except Exception as e:
        print(f"DOCX Parser Hatası: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"DOCX dosyası işlenirken hata oluştu: {str(e)}"
        )
    return text_content.strip()


async def parse_document_to_text(file_content: bytes, filename: str) -> str:
    """
    Ana ayrıştırma fonksiyonu. Dosya tipine göre doğru yöntemi seçer.
    PDF'ler için "Plan A / Plan B" fallback mantığını uygular.
    """
    text_content = ""
    
    if filename.endswith('.pdf'):
        # Plan A: Önce hızlı (dijital) yolu dene
        text_content = await parse_text_with_pdfplumber(file_content)
        
        # Plan B: Hızlı yol başarısız olursa (boş metin dönerse),
        # yavaş (OCR) yolu dene.
        if not text_content:
            print(f"Bilgi: '{filename}' için dijital metin bulunamadı. OCR deneniyor...")
            text_content = await parse_text_with_ocr(file_content)

    elif filename.endswith('.docx'):
        text_content = await parse_docx(file_content)
        
    else:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Desteklenmeyen dosya formatı. Lütfen .pdf veya .docx yükleyin."
        )

    # Her iki (veya üç) yöntem de başarısız olduysa
    if not text_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dosya boş veya metin çıkarılamadı. Dosyanın bozuk olmadığından emin olun."
        )
        
    return text_content