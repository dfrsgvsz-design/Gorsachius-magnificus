"""Audio analysis, upload, batch processing, report generation, and BirdNET endpoints."""

import logging
import os
import uuid

import numpy as np
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse

import main as _main
from models.schemas import BatchScanRequest

logger = logging.getLogger("field_survey_platform")

router = APIRouter()


@router.post("/api/analyze", tags=["Analysis"])
async def analyze_audio(
    file: UploadFile = File(...),
    top_k: int = Query(default=5, ge=1, le=20),
    confidence_threshold: float = Query(default=0.1, ge=0.0, le=1.0),
    engine: str = Query(
        default="cnn", description="Inference engine: cnn | birdnet | auto"
    ),
    session_id: str | None = Query(default=None),
):
    """
    Analyze uploaded audio file for bird species detection.
    Returns species predictions, spectrograms, and biodiversity metrics.
    """
    engine = (engine or "cnn").strip().lower()
    if engine not in {"cnn", "birdnet", "auto"}:
        raise HTTPException(
            status_code=400, detail="Invalid engine. Use: cnn, birdnet, auto"
        )

    content = await _main._read_upload(file, _main.MAX_UPLOAD_BYTES)
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    use_birdnet = engine == "birdnet" or (
        engine == "auto" and (_main.model is None) and _main.birdnet_engine.is_available()
    )
    if use_birdnet:
        results = _main.birdnet_engine.predict_from_bytes(
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
                    "species_chinese": _main.species_to_chinese.get(
                        sci, pred.get("species_chinese", "")
                    ),
                    "species_english": pred.get(
                        "species_common", _main.species_to_english.get(sci, "")
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
                            "species_chinese": _main.species_to_chinese.get(
                                sci, pred.get("species_chinese", "")
                            ),
                            "species_english": pred.get(
                                "species_common", _main.species_to_english.get(sci, "")
                            ),
                            "confidence": conf,
                            "reliable": conf >= max(0.3, confidence_threshold),
                            "source": "birdnet",
                        }
                    ],
                }
            )

        summary = _main.detection_summary(detections)
        if session_id is None:
            session_id = str(uuid.uuid4())[:8]
        _main.detection_history[session_id] = detections
        if _main.det_store and detections:
            _main.det_store.batch_add(detections, session_id=session_id)
            _main.det_store.save()

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

    if _main.model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    try:
        y, sr = _main.load_audio(content, sr=_main.DEFAULT_SR)
        total_duration = len(y) / sr
        waveform_img = _main.waveform_to_base64_image(y, sr=sr)
        full_mel = _main.audio_to_mel_spectrogram(y, sr=sr)
        spectrogram_img = _main.spectrogram_to_base64_image(full_mel, sr=sr)

        if _main.USE_V6_DUAL_CHANNEL:
            import librosa as _lr

            y_48k = _lr.resample(y, orig_sr=sr, target_sr=48000)
            sr_v6 = 48000
            seg_dur_v6 = 3.0
            hop_v6 = int(seg_dur_v6 * sr_v6 * (1 - _main.OVERLAP))
            seg_len_v6 = int(seg_dur_v6 * sr_v6)
            segments_v6 = []
            for start in range(0, max(1, len(y_48k) - seg_len_v6 + 1), hop_v6):
                segments_v6.append(y_48k[start : start + seg_len_v6])
            if not segments_v6:
                segments_v6 = [y_48k]
            all_detections = []
            segment_results = []
            for i, seg in enumerate(segments_v6):
                mel_dual = _main.compute_dual_channel_mel(seg, sr=sr_v6)
                time_offset = i * seg_dur_v6 * (1 - _main.OVERLAP)
                predictions = _main.predict_species(mel_dual, top_k=top_k)
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
            segments = _main.segment_audio(y, sr=sr)
            all_detections = []
            segment_results = []

            for i, seg in enumerate(segments):
                mel = _main.audio_to_mel_spectrogram(seg, sr=sr)
                mel_norm = _main.normalize_spectrogram(mel)
                time_offset = i * _main.SEGMENT_DURATION * (1 - _main.OVERLAP)

                predictions = _main.predict_species(mel_norm, top_k=top_k)

                seg_result = {
                    "segment_index": i,
                    "time_start": round(time_offset, 2),
                    "time_end": round(time_offset + _main.SEGMENT_DURATION, 2),
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

        summary = _main.detection_summary(all_detections)
        if session_id is None:
            session_id = str(uuid.uuid4())[:8]
        _main.detection_history[session_id] = all_detections
        if _main.det_store and all_detections:
            _main.det_store.batch_add(all_detections, session_id=session_id)
            _main.det_store.save()

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


@router.post("/api/compare-spectrograms", tags=["Analysis"])
async def compare_spectrograms(
    file_a: UploadFile = File(...),
    file_b: UploadFile = File(...),
):
    """Generate side-by-side spectrograms for two audio files."""
    results = {}
    for label, file_obj in [("a", file_a), ("b", file_b)]:
        content = await _main._read_upload(file_obj)
        if len(content) == 0:
            raise HTTPException(status_code=400, detail=f"File {label} is empty")
        try:
            y, sr = _main.load_audio(content, sr=_main.DEFAULT_SR)
            mel = _main.audio_to_mel_spectrogram(y, sr=sr)
            results[label] = {
                "filename": file_obj.filename or f"audio_{label}",
                "duration": round(len(y) / sr, 2),
                "sample_rate": sr,
                "spectrogram_image": _main.spectrogram_to_base64_image(mel, sr=sr),
                "waveform_image": _main.waveform_to_base64_image(y, sr=sr),
            }
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot process file {label} ({file_obj.filename}): {e}",
            )
    return results


@router.post("/api/analyze-batch", tags=["Analysis"])
async def analyze_batch(
    files: list[UploadFile] = File(...),
    top_k: int = Query(default=5, ge=1, le=20),
    confidence_threshold: float = Query(default=0.1, ge=0.0, le=1.0),
):
    """Analyze multiple audio files in one request.

    Returns per-file results and aggregated diversity metrics across all files.
    """
    if _main.model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    import librosa as _lr
    import io as _io

    if len(files) > _main.MAX_BATCH_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files ({len(files)}). Maximum: {_main.MAX_BATCH_FILES}",
        )

    all_file_results = []
    all_species = []

    for file in files:
        content = await _main._read_upload(file, _main.MAX_UPLOAD_BYTES)
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

        if _main.USE_V6_DUAL_CHANNEL or _main.USE_V7:
            mel = _main.compute_dual_channel_mel(seg, sr=48000)
        else:
            mel_spec = _main.audio_to_mel_spectrogram(seg, sr=48000)
            mel = _main.normalize_spectrogram(mel_spec)

        predictions = _main.predict_species(mel, top_k=top_k)
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
        aggregated_diversity = _main.compute_alpha_diversity(all_species)

    unique_species = list(set(all_species))

    return {
        "num_files": len(files),
        "num_analyzed": len([r for r in all_file_results if "error" not in r]),
        "total_unique_species": len(unique_species),
        "unique_species": unique_species,
        "aggregated_diversity": aggregated_diversity,
        "file_results": all_file_results,
    }


@router.post("/api/report/generate", tags=["Analysis"])
async def generate_report(
    file: UploadFile = File(...),
    site_name: str = Query(default="未命名站点"),
    top_k: int = Query(default=10, ge=1, le=50),
):
    """Generate an HTML survey report from audio analysis."""
    if _main.model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    content = await _main._read_upload(file, _main.MAX_UPLOAD_BYTES)
    import librosa as _lr
    import io as _io

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
        mel = _main.compute_dual_channel_mel(seg, sr=48000)
        preds = _main.predict_species(mel, top_k=top_k)
        for p in preds:
            p["time_start"] = round(start / 48000, 2)
            p["time_end"] = round((start + seg_len) / 48000, 2)
        all_detections.extend(preds)

    species_list = [
        d["species_scientific"] for d in all_detections if d.get("reliable")
    ]
    if species_list:
        diversity = _main.compute_alpha_diversity(species_list)
    else:
        diversity = {}

    analysis_result = {
        "detections": all_detections,
        "diversity_summary": diversity,
    }

    html = _main.report_generator.generate_report_html(
        analysis_result,
        site_name=site_name,
        author=f"Biodiversity Survey Platform V7 Acoustic Engine ({'ConvNeXt' if _main.USE_V7 else 'SE-ResNet'})",
    )
    return HTMLResponse(content=html)


@router.post("/api/batch/scan", tags=["Batch Import"])
async def batch_scan_directory(req: BatchScanRequest):
    """Scan a directory (e.g. SD card mount) and classify files for import."""
    _main._validate_scan_path(req.directory)
    result = _main.scan_directory(req.directory, recursive=req.recursive)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    by_camera = _main.group_by_camera(result.get("image_files", []))
    by_date = _main.group_by_date(
        result.get("image_files", []) + result.get("audio_files", [])
    )
    manifest = _main.create_import_manifest(
        result,
        device_id=req.device_id,
        site_name=req.site_name,
        camera_serial=req.camera_serial,
    )
    return {
        "scan": result["summary"],
        "total_size_mb": result["total_size_mb"],
        "by_camera": {k: len(v) for k, v in by_camera.items()},
        "by_date": {k: len(v) for k, v in by_date.items()},
        "manifest": manifest,
    }


@router.get("/api/birdnet/status", tags=["BirdNET"])
async def birdnet_status():
    """Check BirdNET engine availability."""
    return {
        "available": _main.birdnet_engine.is_available(),
        "info": "BirdNET-Analyzer by Cornell Lab — ~6000 species baseline",
    }


@router.post("/api/birdnet/analyze")
async def birdnet_analyze(
    file: UploadFile = File(...),
    lat: float | None = Query(default=None),
    lon: float | None = Query(default=None),
    min_conf: float = Query(default=0.1, ge=0.0, le=1.0),
    top_k: int = Query(default=10, ge=1, le=50),
):
    """Analyze audio using BirdNET as baseline comparison engine."""
    if not _main.birdnet_engine.is_available():
        raise HTTPException(
            status_code=503, detail="BirdNET not installed. Run: pip install birdnetlib"
        )

    content = await _main._read_upload(file, _main.MAX_UPLOAD_BYTES)
    results = _main.birdnet_engine.predict_from_bytes(
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
        r["species_chinese"] = _main.species_to_chinese.get(sci, "")
        r["species_english"] = r.get("species_common", _main.species_to_english.get(sci, ""))

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
    content = await _main._read_upload(file, _main.MAX_UPLOAD_BYTES)

    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        cnn_results = []
        try:
            import librosa as _lr
            import io

            y, sr = _lr.load(io.BytesIO(content), sr=48000, mono=True)
            dur = 3.0
            seg_len = int(dur * 48000)
            if len(y) >= seg_len:
                seg = y[:seg_len]
            else:
                seg = np.pad(y, (0, seg_len - len(y)))
            mel = _main.compute_dual_channel_mel(seg, sr=48000)
            cnn_results = _main.predict_species(mel, top_k=top_k)
        except Exception as e:
            cnn_results = [{"error": str(e)}]

        birdnet_results = []
        if _main.birdnet_engine.is_available():
            birdnet_results = _main.birdnet_engine.predict_from_file(tmp_path, top_k=top_k)
            for r in birdnet_results:
                sci = r.get("species_scientific", "")
                r["species_chinese"] = _main.species_to_chinese.get(sci, "")
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
            "version": "v7" if _main.USE_V7 else ("v6" if _main.USE_V6_DUAL_CHANNEL else "v1"),
            "detections": cnn_results,
        },
        "birdnet": {
            "available": _main.birdnet_engine.is_available(),
            "detections": birdnet_results,
        },
        "agreement": {
            "cnn_species": list(cnn_species),
            "birdnet_species": list(bn_species),
            "overlap": list(overlap),
            "agreement_ratio": len(overlap) / max(len(cnn_species | bn_species), 1),
        },
    }
