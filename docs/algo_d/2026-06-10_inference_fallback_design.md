# Algo-D 决策记录：CNN 推理失败 / GPU OOM 的降级路径 `inference_fallback.py`

- **工单：** P2 W3 推理降级路径（"CNN 推理失败 / GPU OOM 时自动降为 BirdNET embedding + KNN。审核设备不一定有 GPU"）
- **DRI：** Algo-D
- **决策日期：** 2026-06-10
- **生效版本：** 后端下一个发版（建议 v7.1.0 同 P0 W1 一起）

---

## 1. 触发条件（什么算"失败"）

`safe_predict_species` 会捕获并降级的异常类型：

| 异常 | 含义 | 降级原因 |
|---|---|---|
| `torch.cuda.OutOfMemoryError` | GPU 显存不足 | OOM |
| `RuntimeError` 含 `"out of memory"` 子串 | 同上（旧版 torch / 不同后端） | OOM |
| `RuntimeError` 含 `"CUDA"`/`"cuDNN"` 子串 | GPU 驱动/上下文崩溃 | gpu_error |
| `FileNotFoundError`（model_path 不存在） | checkpoint 未部署 | no_model |
| 其它未捕获 `Exception` 抛到顶层 | 主模型 bug | runtime_error |

降级动作：调用 `inference_fallback.predict_species_fallback(audio_path, top_k, reason=<上面之一>)`，返回与 `predict_species` **完全同形** 的 list[dict]，并在 `_meta` 上加 `"fallback_engine": "birdnet_embedding_knn"`、`"fallback_reason": <reason>`。

---

## 2. 两层 fallback 设计

```
predict_species(mel)              <- 主路径（CNN ensemble + calibration + OOD）
        │
        │  raises (OOM / no_model / runtime_error)
        ▼
safe_predict_species(audio_path)  <- wrapper
        │
        │  fallback
        ▼
predict_species_fallback(audio_path)
        │
        ├── Tier-1: BirdNET embedding + KNN  ← P2 W3 主路径
        │   - 调 BirdNETEmbeddingEngine.extract_embeddings(audio_path)
        │   - 对每段 chunk embedding 在预建 KNN 索引上查最近邻
        │   - 按 species 投票 + 平均相似度 + 取 top_k
        │   - 要求：BirdNET 安装 + KNN 索引文件存在
        │
        └── Tier-2: BirdNET 自带分类器（birdnetlib）   ← Tier-1 不可用时
            - 调 birdnet_engine.predict_from_file(audio_path, top_k, min_conf)
            - 这是 BirdNET 自带的 6522 类直接分类
            - 要求：birdnetlib 安装
```

两层都不可用 → 返回 `[]` 并把 `_meta.fallback_engine = "none"` 标出来。

---

## 3. KNN 索引构建

### 3.1 输入
- `species_monitoring_platform/data/xc_expanded/manifest.json` 当前 19401 条 / 223 种
- 可选地通过 `--manifest <path>` 切换到 v7-223 训练完成后产出的更干净 manifest

### 3.2 流程
1. 遍历每条 manifest 项 → 调 `BirdNETEmbeddingEngine.extract_embeddings(file_path)` 拿 1024-dim 向量（每段 3s 一个 chunk，一条录音可能多 chunk）
2. 全部向量堆栈 → `embeddings.npy` (N × 1024)
3. 对应 species 索引（按 `species_mapping.json` 的 idx）→ `labels.npy` (N)
4. 复制 `species_mapping.json` 到索引目录
5. 写 `index_meta.json`（构建时间、源 manifest、embedding_dim、KNN k、距离度量 etc.）

### 3.3 输出位置
```
species_monitoring_platform/backend/checkpoints/birdnet_knn/
├── embeddings.npy         # N × 1024 float32
├── labels.npy             # N int32
├── species_mapping.json   # idx -> scientific_name (与主 mapping 同步)
└── index_meta.json        # 元数据
```

### 3.4 运行时
- `predict_species_fallback` 启动时 lazy-load 这 4 个文件到 numpy
- KNN 查询用纯 numpy 实现（cosine sim + top-k argpartition），不需要 sklearn/faiss 依赖
- 1024 维 × ~20k 向量 = ~80MB 内存，CPU 上 top-k 查询 < 50ms（可接受）

### 3.5 一次性构建
```powershell
python "f:\Gorsachius magnificus\scripts\algo_d\build_birdnet_knn_index.py" `
  --manifest "f:\Gorsachius magnificus\species_monitoring_platform\data\xc_expanded\manifest.json" `
  --output   "f:\Gorsachius magnificus\species_monitoring_platform\backend\checkpoints\birdnet_knn" `
  --species-mapping "f:\Gorsachius magnificus\species_monitoring_platform\backend\checkpoints\species_mapping.json"
# 预计耗时 30 min – 2 h（取决于 CPU 速度 + manifest 大小）
# 全程不需要 GPU
```

支持 `--dry-run` 跑 10 条样本估算总耗时，不要真跑就先看看。

---

## 4. 返回形状（drop-in compatibility）

`predict_species_fallback` 和 `predict_species` 返回结构必须一致：

```python
[
  {
    "species_scientific": "Gorsachius magnificus",
    "species_chinese": "白耳夜鹭",  # 从 species_to_chinese 字典查
    "species_english": "White-eared Night Heron",
    "confidence": 0.72,            # KNN 路径：top-k 投票得分；BirdNET 路径：BirdNET min_conf
    "reliable": True,              # KNN 路径：confidence>0.3 且 top-1 票数 > k/2；BirdNET：confidence>0.5
  },
  ...
  # 第 0 条带 _meta:
  {
    ...,
    "_meta": {
      "fallback_engine": "birdnet_embedding_knn",  # or "birdnet_classifier" / "none"
      "fallback_reason": "out_of_memory",
      "knn_k": 7,
      "voting": "weighted_cosine",
      "model_version": "birdnet-2.4-knn",
      "temperature": None,         # 这条路径不做温度标定
      "ensemble": False,
    }
  }
]
```

前端不需要任何代码改动 —— `_meta` 多了几个字段，少了几个字段（如 `entropy`、`ood_detected`），但 confidence/reliable/species_* 5 个字段保持。

---

## 5. 验收门禁（与 P0 W1 / P0 W2 平级）

| 门禁 | 工具 | 通过条件 |
|---|---|---|
| **F1** 模块单元测试 | `pytest scripts/algo_d/_artifacts/test_inference_fallback.py` | 模块可以被 import；空索引下返回 `[]`+meta 正确；模拟 OOM 时不抛错 |
| **F2** 手动触发降级 | `python scripts/algo_d/audit_inference_fallback.py --fake-oom` | 期望降级被命中、返回符合 §4 结构 |
| **F3** drop-in 形状 | 同上 | 返回的 list[dict] 字段名集合 ⊇ 主路径所必需的 |
| **F4** KNN 索引可重建 | `python scripts/algo_d/build_birdnet_knn_index.py --dry-run` | 10 条样本下 < 1 分钟跑通，不依赖 GPU |

---

## 6. 风险与缓解

| # | 风险 | 缓解 |
|---|------|---|
| 1 | BirdNET 包安装失败（Windows 上 tflite 依赖偶尔棘手） | 双层降级（embedding+KNN → birdnetlib → none），任一层都不强依赖；模块 import 时不抛错 |
| 2 | KNN 索引文件过大被误推到 git | 在 `.gitignore` 里加 `species_monitoring_platform/backend/checkpoints/birdnet_knn/embeddings.npy` 和 `labels.npy`，metadata 文件留下 |
| 3 | 静默降级误判误用：主路径其实没坏，被 fallback 接管 | 所有降级都 logger.warning(reason=...) 写日志；前端在 `_meta` 里展示「降级中」徽标（建议 A 工程师做） |
| 4 | KNN 命中的物种和 species_mapping 不一致 | 构建索引时直接复制 species_mapping.json，索引和主模型共享同一份 mapping；如果 mapping bump，索引一并重建 |
| 5 | BirdNET 不识别本地特有种（如 Gorsachius magnificus 未必在 BirdNET 6522 类） | 这是已知 BirdNET 局限。embedding+KNN 用我们自己 labeled 数据训出来，比直接 BirdNET 分类器命中率高；这正是为什么主路径选 embedding+KNN 而不是 Tier-2 |

---

## 7. 不做（明确边界）

- **不** 在 fallback 路径做温度标定：BirdNET 的概率分布 ≠ 我们标定过的，混标定反而引入偏差
- **不** 把 KNN 输出当 calibrated probability：`_meta.temperature = None` 提示前端这是"非标定置信度"
- **不** 在 fallback 里跑 OOD 检测：v7 OOD 是 CNN 头特有的
- **不** 让 fallback 写 audit / detection store：fallback 结果默认 `_meta.write_back = False`，由调用方决定要不要持久化（避免用 fallback 数据污染统计）

---

## 8. 签字

- [ ] 算法 D：__________  日期：__________
- [ ] 项目主管 / sponsor：__________  日期：__________
