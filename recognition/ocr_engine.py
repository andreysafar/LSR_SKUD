import logging
import os
import re
import numpy as np
from typing import Dict, Any, Optional, List

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
                 confidence: float = 0.4, backend: str = "easyocr"):
        self.languages = languages or ["en"]
        self.gpu = gpu
        self.confidence = confidence
        self._backend = backend
        self.reader = None          # EasyOCR reader
        self._paddle_reader = None  # PaddleOCR reader
        self._loaded = False

    def _ensure_loaded(self):
        if not self._loaded:
            self.load()

    def load(self):
        if self._loaded:
            return

        if self._backend == "paddleocr":
            try:
                from paddleocr import PaddleOCR
                self._paddle_reader = PaddleOCR(
                    use_angle_cls=True,
                    lang="en",
                    use_gpu=self.gpu,
                    show_log=False,
                )
                self._loaded = True
                logger.info("PaddleOCR loaded (gpu=%s)", self.gpu)
                return
            except ImportError:
                logger.warning("PaddleOCR not installed, falling back to EasyOCR")
                self._backend = "easyocr"
            except Exception as e:
                logger.error("PaddleOCR init failed: %s, falling back to EasyOCR", e)
                self._backend = "easyocr"

        # EasyOCR (default or fallback)
        import easyocr
        self.reader = easyocr.Reader(
            self.languages,
            gpu=self.gpu,
            model_storage_directory=os.path.abspath("models"),
            download_enabled=False,
        )
        self._loaded = True
        logger.info("EasyOCR loaded (gpu=%s, langs=%s)", self.gpu, self.languages)

    def _parse_easyocr_result(self, ocr_results, plate_image: np.ndarray) -> Dict[str, Any]:
        """Parse EasyOCR output into standard format."""
        result = {
            "text": "",
            "confidence": 0.0,
            "raw_text": "",
            "normalized": "",
            "is_valid_ru": False,
        }

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

        return result

    def _parse_paddle_result(self, ocr_results, plate_image: np.ndarray) -> Dict[str, Any]:
        """Parse PaddleOCR output into standard format."""
        result = {
            "text": "",
            "confidence": 0.0,
            "raw_text": "",
            "normalized": "",
            "is_valid_ru": False,
        }

        if not ocr_results or not ocr_results[0]:
            return result

        texts = []
        total_conf = 0.0
        count = 0

        for line in ocr_results[0]:
            if line and len(line) >= 2:
                text_info = line[1]
                if isinstance(text_info, tuple) and len(text_info) >= 2:
                    text, conf = text_info[0], text_info[1]
                elif isinstance(text_info, str):
                    text, conf = text_info, 0.5
                else:
                    continue
                texts.append(text)
                total_conf += conf
                count += 1

        if texts:
            raw_text = "".join(texts)
            avg_conf = total_conf / count if count > 0 else 0.0
            normalized = normalize_plate(raw_text)
            result["text"] = raw_text
            result["confidence"] = round(avg_conf, 3)
            result["raw_text"] = raw_text
            result["normalized"] = normalized
            result["is_valid_ru"] = bool(RU_PLATE_PATTERN.match(normalized))

        return result

    def recognize(self, plate_image: np.ndarray) -> Dict[str, Any]:
        self._ensure_loaded()

        result = {
            "text": "",
            "confidence": 0.0,
            "raw_text": "",
            "normalized": "",
            "is_valid_ru": False,
        }

        if plate_image is None or plate_image.size == 0:
            return result

        try:
            if self._backend == "paddleocr" and self._paddle_reader:
                ocr_results = self._paddle_reader.ocr(plate_image, cls=True)
                return self._parse_paddle_result(ocr_results, plate_image)
            else:
                if self.reader is None:
                    return result
                ocr_results = self.reader.readtext(plate_image)
                return self._parse_easyocr_result(ocr_results, plate_image)
        except Exception as e:
            logger.error(f"OCR error: {e}")
            return result

    def recognize_batch(self, plate_images: List[np.ndarray]) -> List[Dict[str, Any]]:
        """Batch OCR recognition. Processes multiple plate images efficiently.

        For EasyOCR: processes images sequentially but with shared GPU context.
        For PaddleOCR: uses native batch processing.
        """
        if not plate_images:
            return []

        self._ensure_loaded()
        results = []

        if self._backend == "paddleocr" and self._paddle_reader:
            # PaddleOCR supports batch natively
            try:
                batch_results = self._paddle_reader.ocr(plate_images, cls=True)
                for i, ocr_result in enumerate(batch_results):
                    results.append(self._parse_paddle_result(ocr_result, plate_images[i]))
            except Exception as e:
                logger.error(f"PaddleOCR batch error: {e}")
                # Fallback to sequential
                for img in plate_images:
                    results.append(self.recognize(img))
        else:
            # EasyOCR: sequential but with warm GPU
            for plate_image in plate_images:
                results.append(self.recognize(plate_image))

        return results
