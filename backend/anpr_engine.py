"""Pluggable ANPR engine for the PTS camera pipeline.

FastALPR is the preferred open-source backend when installed. The adapter keeps
the camera service independent from a particular detector or OCR implementation.
"""
import os
import re
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class PlakaSonucu:
    plaka_no: str
    guven_skoru: float
    kutu: Optional[tuple[int, int, int, int]] = None


class ANPREngine:
    def __init__(self, detector_model: str = "yolo-v9-t-384-license-plate-end2end", ocr_model: str = "cct-xs-v2-global-model"):
        try:
            from fast_alpr import ALPR
        except ImportError as exc:
            raise RuntimeError("FastALPR kurulu değil. Kurulum: pip install fast-alpr[onnx]") from exc
        ek_parametreler: dict = {}
        # PTS_ANPR_PROVIDERS=cpu ortam değişkeni GPU hızlandırmasını (DirectML/CUDA)
        # tamamen devre dışı bırakır. Bazı GPU sürücüleri, aynı anda birden fazla
        # kamera GPU üzerinde çıkarım yaptığında kararsızlaşabiliyor (gözlemlenen
        # semptom: onnxruntime "DXGI_ERROR_DEVICE_HUNG" / "GPU başka komutlara
        # yanıt vermeyecek" hatası verip GPU sürücüsünün sıfırlanması, bu da bazı
        # sistemlerde tüm bilgisayarın donup kendini yeniden başlatmasına yol açar).
        # camera_reader.py artık tüm kameralar arasında TEK bir ANPREngine paylaşıp
        # çağrıları serileştiriyor (bkz. `_paylasilan_motoru_al`), bu riski büyük
        # ölçüde azaltır; ama sürücü/donanım hâlâ kararsızsa bu değişkenle CPU'ya
        # tamamen zorlanabilir (birkaç kamera için tipik olarak yeterince hızlıdır).
        if os.environ.get("PTS_ANPR_PROVIDERS", "").strip().lower() in ("cpu", "cpu_only", "cpu-only"):
            ek_parametreler["detector_providers"] = ["CPUExecutionProvider"]
            ek_parametreler["ocr_providers"] = ["CPUExecutionProvider"]
            ek_parametreler["ocr_device"] = "cpu"
        self._alpr = ALPR(detector_model=detector_model, ocr_model=ocr_model, **ek_parametreler)

    def tahmin_et(self, frame: Any) -> list[PlakaSonucu]:
        """Frame üzerinde plaka bulur; motorun sonuç nesnelerini PTS tipine çevirir."""
        sonuclar = self._alpr.predict(frame)
        donus: list[PlakaSonucu] = []
        for sonuc in sonuclar or []:
            plaka = _alan(sonuc, "plate", "text")
            if not plaka:
                continue
            guven = float(_alan(sonuc, "score", "confidence") or 0)
            kutu_verisi = _alan(sonuc, "box", "bbox")
            kutu = _kutuya_cevir(kutu_verisi)
            donus.append(PlakaSonucu(_plaka_temizle(str(plaka)), guven, kutu))
        return [sonuc for sonuc in donus if sonuc.plaka_no]


def _alan(nesne: Any, *alanlar: str) -> Any:
    for alan in alanlar:
        if isinstance(nesne, dict) and alan in nesne:
            return nesne[alan]
        if hasattr(nesne, alan):
            return getattr(nesne, alan)
    return None


def _kutuya_cevir(kutu: Any) -> Optional[tuple[int, int, int, int]]:
    if not kutu:
        return None
    try:
        if isinstance(kutu, dict):
            return tuple(int(kutu[key]) for key in ("xmin", "ymin", "xmax", "ymax"))
        return tuple(int(_alan(kutu, key) or 0) for key in ("xmin", "ymin", "xmax", "ymax"))
    except (KeyError, TypeError, ValueError):
        return None


def _plaka_temizle(metin: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", metin.upper())