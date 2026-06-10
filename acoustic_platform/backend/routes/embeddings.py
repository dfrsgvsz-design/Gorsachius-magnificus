"""Embedding search, classification, clustering, and few-shot detector endpoints."""

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

import main as _main

router = APIRouter()


@router.get("/api/embeddings/stats", tags=["Embeddings"])
async def embedding_stats():
    """Get embedding engine statistics."""
    return _main.emb_engine.get_stats()


@router.get("/api/embeddings/cluster/{session_id}", tags=["Embeddings"])
async def cluster_session_embeddings(session_id: str):
    """Cluster embeddings from a session to discover acoustic patterns."""
    embeddings, labels = _main.emb_engine.get_session_embeddings(session_id)
    if len(embeddings) == 0:
        raise HTTPException(status_code=404, detail="No embeddings for this session")

    clusters = _main.emb_engine.cluster_embeddings(embeddings)
    coords = _main.emb_engine.reduce_dimensions(embeddings, n_components=2)

    points = []
    for i in range(len(embeddings)):
        points.append(
            {
                "x": float(coords[i][0]),
                "y": float(coords[i][1]),
                "species": labels[i],
                "cluster": int(clusters[i]),
            }
        )

    return {
        "session_id": session_id,
        "n_points": len(points),
        "n_clusters": len(set(clusters)) - (1 if -1 in clusters else 0),
        "points": points,
    }


@router.get("/api/embeddings/similarity/{session_id}", tags=["Embeddings"])
async def species_acoustic_similarity(session_id: str):
    """Compute inter-species acoustic similarity matrix from embeddings."""
    embeddings, labels = _main.emb_engine.get_session_embeddings(session_id)
    if len(embeddings) == 0:
        raise HTTPException(status_code=404, detail="No embeddings for this session")
    return _main.emb_engine.compute_acoustic_similarity_matrix(embeddings, labels)


@router.get("/api/embeddings/novel/{session_id}", tags=["Embeddings"])
async def find_novel_sounds(session_id: str):
    """Find potentially novel or unrecognized sound events in a session."""
    novel = _main.emb_engine.find_novel_sounds(session_id)
    return {"session_id": session_id, "novel_sounds": novel, "total": len(novel)}


# ── Few-shot Detector ──

@router.post("/api/fewshot/create-detector", tags=["Few-shot"])
async def create_fewshot_detector(
    name: str = Query(...),
    species: str = Query(...),
    files: list[UploadFile] = File(...),
):
    """Create a few-shot detector from 1-5 reference audio files."""
    embeddings = []
    for f in files[:5]:
        content = await _main._read_upload(f)
        emb = _main.fewshot.extract_embedding_from_audio(content)
        if emb is not None:
            embeddings.append(emb)
    if not embeddings:
        raise HTTPException(
            status_code=422,
            detail="Could not extract embeddings from any reference file",
        )
    return _main.fewshot.create_detector(name, species, embeddings)


@router.get("/api/fewshot/detectors", tags=["Few-shot"])
async def list_fewshot_detectors():
    """List all saved few-shot detectors."""
    return {"detectors": _main.fewshot.list_detectors()}


@router.delete("/api/fewshot/detectors/{detector_id}", tags=["Few-shot"])
async def delete_fewshot_detector(detector_id: str):
    """Delete a few-shot detector."""
    if not _main.fewshot.delete_detector(detector_id):
        raise HTTPException(status_code=404, detail="Detector not found")
    return {"deleted": True}
