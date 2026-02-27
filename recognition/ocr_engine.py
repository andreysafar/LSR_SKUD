import logging
import re
import numpy as np
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

RU_PLATE_PATTERN = re.compile(r'^[АВЕКМНОРСТУХ]\d{3}[АВЕКМНОРСТУХ]{2}\d{2,3}$')
LATIN_TO_CYRILLIC = {
    'A': 'А', 'B': 'В', 'C': 'С', 'E': 'Е', 'H': 'Н',
    'K': 'К', 'M': 'М', 'O': 'О', 'P': 'Р', 'T': 'Т',
    'X': 'Х', 'Y': 'У',
}


def normalize_plate(text: str) -> str:
    text = text.upper().strip()
    text = re.sub(r'[^A-ZА-Я0-9]', '', text)
    result = []
    for ch in text:
        result.append(LATIN_TO_CYRILLIC.get(ch, ch))
    return ''.join(result)


class OCREngine:
    def __init__(self, languages: list = None, gpu: bool = False,
                 confidence: float = 0.4):
        self.languages = languages or ['en']
        self.gpu = gpu
        self.confidence = confidence
        self.reader = None
        self._loaded = False

    def load(self):
        if self._loaded:
            return
        try:
            import easyocr
            self.reader = easyocr.Reader(self.languages, gpu=self.gpu)
            logger.info(f"OCR engine loaded (gpu={self.gpu})")
            self._loaded = True
        except ImportError:
            logger.warning("easyocr not available, using simulation mode")
            self._loaded = True
        except Exception as e:
            logger.error(f"Failed to load OCR engine: {e}")

    def recognize(self, plate_image: np.ndarray) -> Dict[str, Any]:
        result = {
            "text": "",
            "confidence": 0.0,
            "raw_text": "",
            "normalized": "",
            "is_valid_ru": False,
        }

        if not self._loaded:
            self.load()

        if self.reader is None:
            return result

        try:
            ocr_results = self.reader.readtext(plate_image)

            if ocr_results:
                texts = []
                total_conf = 0
                for detection in ocr_results:
                    bbox, text, conf = detection
                    texts.append(text)
                    total_conf += conf

                raw_text = ''.join(texts)
                avg_conf = total_conf / len(ocr_results)
                normalized = normalize_plate(raw_text)

                result = {
                    "text": raw_text,
                    "confidence": round(avg_conf, 3),
                    "raw_text": raw_text,
                    "normalized": normalized,
                    "is_valid_ru": bool(RU_PLATE_PATTERN.match(normalized)),
                }

        except Exception as e:
            logger.error(f"OCR error: {e}")

        return result
