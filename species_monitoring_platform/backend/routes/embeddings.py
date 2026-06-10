"""Acoustic embedding space analysis endpoints."""

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["Embeddings"])


@router.get("/api/embeddings/stats")
async def embedding_stats():
    """Get embedding engine statistics."""
    import main as _m

    return _m.emb_engine.get_stats()


@router.get("/api/embeddings/cluster/{session_id}")
async def cluster_session_embeddings(session_id: str):
    """Cluster embeddings from a session to discover acoustic patterns."""
    import main as _m

    embeddings, labels = _m.emb_engine.get_session_embeddings(session_id)
    if len(embeddings) == 0:
        raise HTTPException(status_code=404, detail="No embeddings for this session")

    clusters = _m.emb_engine.cluster_embeddings(embeddings)
    coords = _m.emb_engine.reduce_dimensions(embeddings, n_components=2)

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


@router.get("/api/embeddings/similarity/{session_id}")
async def species_acoustic_similarity(session_id: str):
    """Compute inter-species acoustic similarity matrix from embeddings."""
    import main as _m

    embeddings, labels = _m.emb_engine.get_session_embeddings(session_id)
    if len(embeddings) == 0:
        raise HTTPException(status_code=404, detail="No embeddings for this session")
    return _m.emb_engine.compute_acoustic_similarity_matrix(embeddings, labels)


@router.get("/api/embeddings/novel/{session_id}")
async def find_novel_sounds(session_id: str):
    """Find potentially novel or unrecognized sound events in a session."""
    import main as _m

    novel = _m.emb_engine.find_novel_sounds(session_id)
    return {"session_id": session_id, "novel_sounds": novel, "total": len(novel)}
