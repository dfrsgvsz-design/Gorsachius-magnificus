"""Health check, readiness, and runtime info endpoints."""

from fastapi import APIRouter

import main as _main

router = APIRouter(tags=["Health"])


@router.get("/api/health")
async def health_check():
    warnings = _main._build_runtime_warnings()
    model_species = len(_main.species_mapping) if _main.species_mapping else 0
    db_species = _main.species_db.count if _main.species_db else 0
    runtime_state = _main._runtime_state_from_warnings(warnings)
    runtime_paths = _main.describe_runtime_paths()
    readiness = _main._build_readiness_summary(runtime_state, runtime_paths)
    model_info = {
        "loaded": _main.model is not None,
        "version": "v7" if _main.USE_V7 else ("v6" if _main.USE_V6_DUAL_CHANNEL else "v1-v3"),
        "architecture": (
            "ConvNeXt-Tiny/Pico"
            if _main.USE_V7
            else "SE-ResNet + GeM" if _main.USE_V6_DUAL_CHANNEL else "ResNet/SE-ResNet"
        ),
        "ensemble": _main.USE_ENSEMBLE,
        "ood_detection": _main.USE_V7,
        "dual_channel_mel": _main.USE_V6_DUAL_CHANNEL or _main.USE_V7,
    }
    protocol_registry_loaded = bool(
        _main.survey_store and _main.survey_store.list_protocol_definitions()
    )
    prioritized_taxonomy_packages = (
        _main.survey_store.list_taxonomy_packages() if _main.survey_store else []
    )
    prioritized_taxonomy_packages = [
        item
        for item in prioritized_taxonomy_packages
        if str(item.get("program") or "").strip()
        in {"terrestrial_vertebrates", "plants", "insects"}
    ]
    taxonomy_release_health = _main._taxonomy_release_health_summary(
        prioritized_taxonomy_packages
    )
    taxonomy_assets_ready = bool(
        _main.taxonomy_catalog
        and getattr(_main.taxonomy_catalog, "stats", None)
        and (_main.taxonomy_catalog.stats().get("taxa", 0) > 0)
    )
    attachment_storage_ready = bool(_main.survey_store)
    survey_go_live_blockers: list[str] = []
    if any(
        str(item.get("program") or "").strip() == "terrestrial_vertebrates"
        and not bool(item.get("exhaustive") or item.get("exhaustive_species_content"))
        for item in prioritized_taxonomy_packages
    ):
        survey_go_live_blockers.append("TERRESTRIAL_VERTEBRATE_CATALOG_INCOMPLETE")
    if any(
        str(item.get("program") or "").strip() in {"plants", "insects"}
        and int(item.get("local_seed_asset_count") or 0) <= 0
        for item in prioritized_taxonomy_packages
    ):
        survey_go_live_blockers.append("PLANT_INSECT_SEED_ASSETS_MISSING")
    if any(bool(item.get("seed_only")) for item in prioritized_taxonomy_packages):
        survey_go_live_blockers.append("TAXONOMY_PACKAGES_STILL_SEED_ONLY")
    if prioritized_taxonomy_packages and not bool(
        taxonomy_release_health["taxonomy_count_parity_ok"]
    ):
        survey_go_live_blockers.append("TAXONOMY_RELEASE_COUNT_PARITY_FAILED")
    if int(taxonomy_release_health["taxonomy_review_backlog_count"] or 0) > 0:
        survey_go_live_blockers.append("TAXONOMY_REVIEW_BACKLOG_OPEN")
    if int(taxonomy_release_health["taxonomy_exhaustive_package_count"] or 0) < len(
        prioritized_taxonomy_packages
    ):
        survey_go_live_blockers.append("TAXONOMY_RELEASE_NOT_EXHAUSTIVE")
    return {
        "status": "ok",
        "runtime_state": runtime_state,
        "ready": readiness["legacy_ready"],
        "deployment_ready": readiness["strict_ready"],
        "readiness": readiness,
        "model": model_info,
        "model_loaded": _main.model is not None,
        "device": str(_main.DEVICE),
        "num_species_model": model_species,
        "num_species_db": db_species,
        "species_coverage": {
            "model_species": model_species,
            "database_species": db_species,
            "missing_from_model": max(0, db_species - model_species),
            "coverage_ratio": (model_species / db_species) if db_species else 1.0,
        },
        "current_taxonomy_release_id": taxonomy_release_health[
            "current_taxonomy_release_id"
        ],
        "taxonomy_exhaustive_package_count": taxonomy_release_health[
            "taxonomy_exhaustive_package_count"
        ],
        "taxonomy_count_parity_ok": taxonomy_release_health["taxonomy_count_parity_ok"],
        "taxonomy_review_backlog_count": taxonomy_release_health[
            "taxonomy_review_backlog_count"
        ],
        "survey_readiness": {
            "taxonomy_assets_ready": taxonomy_assets_ready,
            "protocol_registry_loaded": protocol_registry_loaded,
            "attachment_storage_ready": attachment_storage_ready,
            "taxonomy_package_count": len(prioritized_taxonomy_packages),
            "current_taxonomy_release_id": taxonomy_release_health[
                "current_taxonomy_release_id"
            ],
            "taxonomy_exhaustive_package_count": taxonomy_release_health[
                "taxonomy_exhaustive_package_count"
            ],
            "taxonomy_count_parity_ok": taxonomy_release_health[
                "taxonomy_count_parity_ok"
            ],
            "taxonomy_review_backlog_count": taxonomy_release_health[
                "taxonomy_review_backlog_count"
            ],
            "taxonomy_seed_only_package_count": sum(
                1
                for item in prioritized_taxonomy_packages
                if bool(item.get("seed_only"))
            ),
            "taxonomy_local_seed_asset_gap_count": sum(
                1
                for item in prioritized_taxonomy_packages
                if int(item.get("local_seed_asset_count") or 0) <= 0
            ),
            "go_live_blockers": survey_go_live_blockers,
            "go_live_ready": len(survey_go_live_blockers) == 0,
            "deployment_ready": bool(
                readiness["strict_ready"]
                and taxonomy_assets_ready
                and protocol_registry_loaded
                and attachment_storage_ready
            ),
        },
        "birdnet_available": _main.birdnet_engine.is_available(),
        "devices_online": _main.device_mgr.online_count if _main.device_mgr else 0,
        "active_sessions": len(_main.rt_processor.list_sessions()) if _main.rt_processor else 0,
        "detection_store": _main.det_store.get_stats() if _main.det_store else {},
        "embedding_engine": _main.emb_engine.get_stats() if _main.emb_engine else {},
        "runtime_paths": runtime_paths,
        "warnings": warnings,
    }


@router.get("/api/paper-context", tags=["Health"])
async def paper_context():
    """Return summary of the Sugai et al. (2026) paper context for the platform."""
    return {
        "paper": "Sugai et al. (2026) Acoustic indices are not useful for biodiversity research. Methods in Ecology and Evolution.",
        "key_problems_with_acoustic_indices": [
            "缺乏理论和实证支持作为生物多样性代理指标",
            "无法识别具体物种——仅是声能的数学抽象",
            "缺乏跨类群、生态系统的通用性",
            "统计陷阱普遍（伪重复、多重检验、因果推断错误）",
            "不适合保护决策——入侵种检测和种群监测需要物种识别",
        ],
        "platform_solutions": [
            "CNN卷积神经网络直接识别鸟类物种（而非声学指数）",
            "基于mel频谱图的SE-ResNet架构 + 知识蒸馏 (Teacher-Student)",
            "双通道mel频谱输入 (低频0-3kHz + 高频500Hz-15kHz, BirdNET标准)",
            "整合Xeno-canto中国鸟类声音数据库用于训练",
            "计算真实物种多样性指标（Shannon、Simpson、Chao1、Fisher's alpha）",
            "支持多站点Beta多样性比较（Jaccard、Sørensen、Bray-Curtis、Whittaker）",
            "Beta多样性分解：turnover vs nestedness（Socolar et al., 2016）",
            "功能多样性指标：FRic、FEve、FDis（Cadotte et al., 2011）",
            "物种累积曲线 + 稀疏化曲线评估调查充分性",
            "Feature embedding提取 + HDBSCAN无监督聚类发现未知声学模式",
            "检测验证工作流：机器检测 → 人工审核 → 确认/拒绝（处理假阳性/假阴性）",
            "占域模型数据准备（MacKenzie et al., 2002）：处理不完美检测",
            "保护优先级评分：整合IUCN濒危等级 + 国家保护级别",
            "持久化检测记录存储（支持跨会话/跨站点汇总分析）",
        ],
        "databases_used": [
            {
                "name": "Xeno-canto",
                "url": "https://xeno-canto.org",
                "description": "全球最大的鸟类声音开放数据库",
            },
            {
                "name": "Macaulay Library",
                "url": "https://www.macaulaylibrary.org",
                "description": "康奈尔大学鸟类声音档案",
            },
            {
                "name": "BirdCLEF",
                "url": "https://www.kaggle.com/competitions/birdclef-2025",
                "description": "Kaggle鸟声识别竞赛",
            },
        ],
        "referenced_tools": [
            {
                "name": "BirdNET",
                "url": "https://github.com/kahst/BirdNET-Analyzer",
                "type": "CNN鸟声识别",
            },
            {
                "name": "Perch",
                "url": "https://github.com/google-research/perch",
                "type": "Google生物声学基础模型",
            },
            {"name": "ARBIMON", "url": "https://arbimon.org", "type": "声学监测平台"},
            {"name": "Raven Pro", "type": "声音分析软件"},
            {
                "name": "WildTrax",
                "url": "https://wildtrax.ca",
                "type": "野生动物追踪平台",
            },
        ],
    }
