"""Audio analysis, upload, batch processing, and BirdNET endpoints."""

import logging
import os
import uuid
from typing import Optional

import numpy as np
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Analysis"])
logger = logging.getLogger("field_survey_platform")


@router.post("/api/analyze")
async def analyze_audio(
    file: UploadFile = File(...),
    top_k: int = Query(default=5, ge=1, le=20),
    confidence_threshold: float = Query(default=0.1, ge=0.0, le=1.0),
    engine: str = Query(
        default="cnn", description="Inference engine: cnn | birdnet | auto"
    ),
    session_id: Optional[str] = Query(default=None),
):
    """Analyze uploaded audio file for bird species detection."""
    import main as _m
    from audio_processor import (
        DEFAULT_SR,
        OVERLAP,
        SEGMENT_DURATION,
        audio_to_mel_spectrogram,
        load_audio,
        normalize_spectrogram,
        segment_audio,
        spectrogram_to_base64_image,
        waveform_to_base64_image,
    )
    from shared.backend.analysis.biodiversity import detection_summary

    engine = (engine or "cnn").strip().lower()
    if engine not in {"cnn", "birdnet", "auto"}:
        raise HTTPException(
            status_code=400, detail="Invalid engine. Use: cnn, birdnet, auto"
        )

    content = await _m._read_upload(file, _m.MAX_UPLOAD_BYTES)
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    use_birdnet = engine == "birdnet" or (
        engine == "auto" and (_m.model is None) and _m.birdnet_engine.is_available()
    )
    if use_birdnet:
        results = _m.birdnet_engine.predict_from_bytes(
            content,
            filename=file.filename or "audio.wav",
            min_conf=confidence_threshold,
            top_k=top_k,
        )
        if results and "error" in results[0]:
            raise HTTPException(status_code=500, detail=results[0]["error"])

        detections = []
        segment_results = []
        for idx, pred in enumerate(results):
            sci = pred.get("species_scientific", "")
            conf = float(pred.get("confidence", 0.0))
            if conf < confidence_threshold:
                continue
            detections.append(
                {
                    "species": sci,
                    "species_chinese": _m.species_to_chinese.get(
                        sci, pred.get("species_chinese", "")
                    ),
                    "species_english": pred.get(
                        "species_common", _m.species_to_english.get(sci, "")
                    ),
                    "confidence": conf,
                    "time_offset": float(pred.get("start_time", 0.0)),
                }
            )
            segment_results.append(
                {
                    "segment_index": idx,
                    "time_start": round(float(pred.get("start_time", 0.0)), 2),
                    "time_end": round(float(pred.get("end_time", 0.0)), 2),
                    "predictions": [
                        {
                            "species_scientific": sci,
                            "species_chinese": _m.species_to_chinese.get(
                                sci, pred.get("species_chinese", "")
                            ),
                            "species_english": pred.get(
                                "species_common", _m.species_to_english.get(sci, "")
                            ),
                            "confidence": conf,
                            "reliable": conf >= max(0.3, confidence_threshold),
                            "source": "birdnet",
                        }
                    ],
                }
            )

        summary = detection_summary(detections)
        if session_id is None:
            session_id = str(uuid.uuid4())[:8]
        _m.detection_history[session_id] = detections
        if _m.det_store and detections:
            _m.det_store.batch_add(detections, session_id=session_id)
            _m.det_store.save()

        return {
            "session_id": session_id,
            "filename": file.filename,
            "duration_seconds": None,
            "sample_rate": None,
            "num_segments": len(segment_results),
            "waveform_image": None,
            "spectrogram_image": None,
            "segment_results": segment_results,
            "detections": detections,
            "summary": summary,
            "engine_used": "birdnet",
        }

    if _m.model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    try:
        y, sr = load_audio(content, sr=DEFAULT_SR)
        total_duration = len(y) / sr
        waveform_img = waveform_to_base64_image(y, sr=sr)
        full_mel = audio_to_mel_spectrogram(y, sr=sr)
        spectrogram_img = spectrogram_to_base64_image(full_mel, sr=sr)

        if _m.USE_V6_DUAL_CHANNEL:
            import librosa as _lr
            from shared.backend.models.cnn_model_v6 import compute_dual_channel_mel

            y_48k = _lr.resample(y, orig_sr=sr, target_sr=48000)
            sr_v6 = 48000
            seg_dur_v6 = 3.0
            hop_v6 = int(seg_dur_v6 * sr_v6 * (1 - OVERLAP))
            seg_len_v6 = int(seg_dur_v6 * sr_v6)
            segments_v6 = []
            for start in range(0, max(1, len(y_48k) - seg_len_v6 + 1), hop_v6):
                segments_v6.append(y_48k[start : start + seg_len_v6])
            if not segments_v6:
                segments_v6 = [y_48k]
            all_detections = []
            segment_results = []
            for i, seg in enumerate(segments_v6):
                mel_dual = compute_dual_channel_mel(seg, sr=sr_v6)
                time_offset = i * seg_dur_v6 * (1 - OVERLAP)
                predictions = _m.predict_species(mel_dual, top_k=top_k)
                seg_result = {
                    "segment_index": i,
                    "time_start": round(time_offset, 2),
                    "time_end": round(time_offset + seg_dur_v6, 2),
                    "predictions": predictions,
                }
                segment_results.append(seg_result)
                for pred in predictions:
                    if pred["confidence"] >= confidence_threshold:
                        all_detections.append(
                            {
                                "species": pred["species_scientific"],
                                "species_chinese": pred["species_chinese"],
                                "species_english": pred["species_english"],
                                "confidence": pred["confidence"],
                                "time_offset": time_offset,
                            }
                        )
        else:
            segments = segment_audio(y, sr=sr)
            all_detections = []
            segment_results = []
            for i, seg in enumerate(segments):
                mel = audio_to_mel_spectrogram(seg, sr=sr)
                mel_norm = normalize_spectrogram(mel)
                time_offset = i * SEGMENT_DURATION * (1 - OVERLAP)
                predictions = _m.predict_species(mel_norm, top_k=top_k)
                seg_result = {
                    "segment_index": i,
                    "time_start": round(time_offset, 2),
                    "time_end": round(time_offset + SEGMENT_DURATION, 2),
                    "predictions": predictions,
                }
                segment_results.append(seg_result)
                for pred in predictions:
                    if pred["confidence"] >= confidence_threshold:
                        all_detections.append(
                            {
                                "species": pred["species_scientific"],
                                "species_chinese": pred["species_chinese"],
                                "species_english": pred["species_english"],
                                "confidence": pred["confidence"],
                                "time_offset": time_offset,
                            }
                        )

        summary = detection_summary(all_detections)
        if session_id is None:
            session_id = str(uuid.uuid4())[:8]
        _m.detection_history[session_id] = all_detections
        if _m.det_store and all_detections:
            _m.det_store.batch_add(all_detections, session_id=session_id)
            _m.det_store.save()

        return {
            "session_id": session_id,
            "filename": file.filename,
            "duration_seconds": round(total_duration, 2),
            "sample_rate": sr,
            "num_segments": len(segment_results),
            "waveform_image": waveform_img,
            "spectrogram_image": spectrogram_img,
            "segment_results": segment_results,
            "detections": all_detections,
            "summary": summary,
            "engine_used": "cnn",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Audio analysis failed for file=%s", file.filename)
        message = str(e)
        lowered = message.lower()
        if any(
            token in lowered
            for token in [
                "format not recognised",
                "format not recognized",
                "error opening",
                "invalid data found",
                "returned non-zero exit status",
                "ffmpeg",
            ]
        ):
            raise HTTPException(
                status_code=400, detail=f"Invalid audio file: {message}"
            )
        raise HTTPException(status_code=500, detail=f"Analysis error: {message}")


@router.post("/api/compare-spectrograms")
async def compare_spectrograms(
    file_a: UploadFile = File(...),
    file_b: UploadFile = File(...),
):
    """Generate side-by-side spectrograms for two audio files."""
    import main as _m
    from audio_processor import (
        DEFAULT_SR,
        audio_to_mel_spectrogram,
        load_audio,
        spectrogram_to_base64_image,
        waveform_to_base64_image,
    )

    results = {}
    for label, file_obj in [("a", file_a), ("b", file_b)]:
        content = await _m._read_upload(file_obj)
        if len(content) == 0:
            raise HTTPException(status_code=400, detail=f"File {label} is empty")
        try:
            y, sr = load_audio(content, sr=DEFAULT_SR)
            mel = audio_to_mel_spectrogram(y, sr=sr)
            results[label] = {
                "filename": file_obj.filename or f"audio_{label}",
                "duration": round(len(y) / sr, 2),
                "sample_rate": sr,
                "spectrogram_image": spectrogram_to_base64_image(mel, sr=sr),
                "waveform_image": waveform_to_base64_image(y, sr=sr),
            }
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot process file {label} ({file_obj.filename}): {e}",
            )
    return results


@router.post("/api/analyze-batch")
async def analyze_batch(
    files: list[UploadFile] = File(...),
    top_k: int = Query(default=5, ge=1, le=20),
    confidence_threshold: float = Query(default=0.1, ge=0.0, le=1.0),
):
    """Analyze multiple audio files in one request."""
    import io as _io

    import librosa as _lr

    import main as _m
    from audio_processor import audio_to_mel_spectrogram, normalize_spectrogram
    from shared.backend.analysis.biodiversity import compute_alpha_diversity
    from shared.backend.models.cnn_model_v6 import compute_dual_channel_mel

    if _m.model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    if len(files) > _m.MAX_BATCH_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files ({len(files)}). Maximum: {_m.MAX_BATCH_FILES}",
        )

    all_file_results = []
    all_species = []

    for file in files:
        content = await _m._read_upload(file, _m.MAX_UPLOAD_BYTES)
        try:
            y, sr = _lr.load(_io.BytesIO(content), sr=48000, mono=True)
        except Exception as e:
            all_file_results.append(
                {"filename": file.filename, "error": str(e), "detections": []}
            )
            continue

        dur = 3.0
        seg_len = int(dur * 48000)
        if len(y) >= seg_len:
            seg = y[:seg_len]
        else:
            seg = np.pad(y, (0, seg_len - len(y)))

        if _m.USE_V6_DUAL_CHANNEL or _m.USE_V7:
            mel = compute_dual_channel_mel(seg, sr=48000)
        else:
            mel_spec = audio_to_mel_spectrogram(seg, sr=48000)
            mel = normalize_spectrogram(mel_spec)

        predictions = _m.predict_species(mel, top_k=top_k)
        filtered = [p for p in predictions if p["confidence"] >= confidence_threshold]

        for p in filtered:
            if p.get("reliable"):
                all_species.append(p["species_scientific"])

        all_file_results.append(
            {
                "filename": file.filename,
                "detections": filtered,
                "top_species": filtered[0] if filtered else None,
            }
        )

    aggregated_diversity = {}
    if all_species:
        aggregated_diversity = compute_alpha_diversity(all_species)

    unique_species = list(set(all_species))

    return {
        "num_files": len(files),
        "num_analyzed": len([r for r in all_file_results if "error" not in r]),
        "total_unique_species": len(unique_species),
        "unique_species": unique_species,
        "aggregated_diversity": aggregated_diversity,
        "file_results": all_file_results,
    }


@router.post("/api/report/generate")
async def generate_report(
    file: UploadFile = File(...),
    site_name: str = Query(default="未命名站点"),
    top_k: int = Query(default=10, ge=1, le=50),
):
    """Generate an HTML survey report from audio analysis."""
    import io as _io

    import librosa as _lr

    import main as _m
    import report_generator
    from shared.backend.analysis.biodiversity import compute_alpha_diversity
    from shared.backend.models.cnn_model_v6 import compute_dual_channel_mel

    if _m.model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    content = await _m._read_upload(file, _m.MAX_UPLOAD_BYTES)
    y, sr = _lr.load(_io.BytesIO(content), sr=48000, mono=True)

    dur = 3.0
    seg_len = int(dur * 48000)
    overlap = 0.25
    hop = int(seg_len * (1 - overlap))

    all_detections = []
    for start in range(0, max(1, len(y) - seg_len + 1), hop):
        seg = y[start : start + seg_len]
        if len(seg) < seg_len:
            seg = np.pad(seg, (0, seg_len - len(seg)))
        mel = compute_dual_channel_mel(seg, sr=48000)
        preds = _m.predict_species(mel, top_k=top_k)
        for p in preds:
            p["time_start"] = round(start / 48000, 2)
            p["time_end"] = round((start + seg_len) / 48000, 2)
        all_detections.extend(preds)

    species_list = [
        d["species_scientific"] for d in all_detections if d.get("reliable")
    ]
    diversity = compute_alpha_diversity(species_list) if species_list else {}

    analysis_result = {
        "detections": all_detections,
        "diversity_summary": diversity,
    }

    html = report_generator.generate_report_html(
        analysis_result,
        site_name=site_name,
        author=f"Biodiversity Survey Platform V7 Acoustic Engine ({'ConvNeXt' if _m.USE_V7 else 'SE-ResNet'})",
    )
    return HTMLResponse(content=html)


@router.get("/api/birdnet/status", tags=["BirdNET"])
async def birdnet_status():
    """Check BirdNET engine availability."""
    import main as _m

    return {
        "available": _m.birdnet_engine.is_available(),
        "info": "BirdNET-Analyzer by Cornell Lab — ~6000 species baseline",
    }


@router.post("/api/birdnet/analyze")
async def birdnet_analyze(
    file: UploadFile = File(...),
    lat: Optional[float] = Query(default=None),
    lon: Optional[float] = Query(default=None),
    min_conf: float = Query(default=0.1, ge=0.0, le=1.0),
    top_k: int = Query(default=10, ge=1, le=50),
):
    """Analyze audio using BirdNET as baseline comparison engine."""
    import main as _m

    if not _m.birdnet_engine.is_available():
        raise HTTPException(
            status_code=503, detail="BirdNET not installed. Run: pip install birdnetlib"
        )

    content = await _m._read_upload(file, _m.MAX_UPLOAD_BYTES)
    results = _m.birdnet_engine.predict_from_bytes(
        content,
        filename=file.filename or "audio.wav",
        lat=lat,
        lon=lon,
        min_conf=min_conf,
        top_k=top_k,
    )

    if results and "error" in results[0]:
        raise HTTPException(status_code=500, detail=results[0]["error"])

    for r in results:
        sci = r.get("species_scientific", "")
        r["species_chinese"] = _m.species_to_chinese.get(sci, "")
        r["species_english"] = r.get("species_common", _m.species_to_english.get(sci, ""))

    return {
        "engine": "birdnet",
        "num_detections": len(results),
        "detections": results,
    }


@router.post("/api/compare-engines")
async def compare_engines(
    file: UploadFile = File(...),
    top_k: int = Query(default=5, ge=1, le=20),
):
    """Compare our CNN model vs BirdNET on the same audio file."""
    import io
    import tempfile

    import librosa as _lr

    import main as _m
    from shared.backend.models.cnn_model_v6 import compute_dual_channel_mel

    content = await _m._read_upload(file, _m.MAX_UPLOAD_BYTES)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        cnn_results = []
        try:
            y, sr = _lr.load(io.BytesIO(content), sr=48000, mono=True)
            dur = 3.0
            seg_len = int(dur * 48000)
            if len(y) >= seg_len:
                seg = y[:seg_len]
            else:
                seg = np.pad(y, (0, seg_len - len(y)))
            mel = compute_dual_channel_mel(seg, sr=48000)
            cnn_results = _m.predict_species(mel, top_k=top_k)
        except Exception as e:
            cnn_results = [{"error": str(e)}]

        birdnet_results = []
        if _m.birdnet_engine.is_available():
            birdnet_results = _m.birdnet_engine.predict_from_file(tmp_path, top_k=top_k)
            for r in birdnet_results:
                sci = r.get("species_scientific", "")
                r["species_chinese"] = _m.species_to_chinese.get(sci, "")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    cnn_species = {
        r["species_scientific"] for r in cnn_results if "species_scientific" in r
    }
    bn_species = {
        r["species_scientific"] for r in birdnet_results if "species_scientific" in r
    }
    overlap = cnn_species & bn_species

    return {
        "cnn_model": {
            "version": "v7" if _m.USE_V7 else ("v6" if _m.USE_V6_DUAL_CHANNEL else "v1"),
            "detections": cnn_results,
        },
        "birdnet": {
            "available": _m.birdnet_engine.is_available(),
            "detections": birdnet_results,
        },
        "agreement": {
            "cnn_species": list(cnn_species),
            "birdnet_species": list(bn_species),
            "overlap": list(overlap),
            "agreement_ratio": len(overlap) / max(len(cnn_species | bn_species), 1),
        },
    }
