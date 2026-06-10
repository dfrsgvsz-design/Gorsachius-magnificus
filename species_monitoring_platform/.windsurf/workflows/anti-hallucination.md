---
description: 鸟声识别反幻觉机制 — 防止模型产生高置信度错误预测的全套规则和流程
---

# Anti-Hallucination Mechanism for Bird Sound Recognition

## 核心原则

**幻觉定义**: 模型对错误预测给出高置信度分数(>0.7)，导致用户误判物种。

**根因分析** (基于v1-v4迭代经验):
1. **过拟合** — train/val gap过大时，模型记忆训练集噪声模式
2. **置信度未校准** — softmax输出不反映真实正确概率
3. **分布外输入** — 非鸟声、未见物种、噪声被强制分类
4. **类别不平衡** — 少样本物种被错误地高置信预测为多样本物种

## 七层防线架构

### L1: 数据层 — 源头治理
- **非事件类(Non-event class)**: 训练集必须包含"背景噪声/非鸟声"类别
  - 来源: 城市噪声、风声、雨声、人声、机械声
  - 比例: 占总训练样本5-10%
- **类别平衡**: WeightedRandomSampler + Focal Loss(gamma=2.0)
- **数据增强**: SpecAugment(3 freq + 3 time masks), CutMix(35%), Mixup(30%)
- **最小样本**: 每物种≥10条录音，否则不纳入分类器

### L2: 架构层 — 结构性防御
- **双通道频谱图** (借鉴BirdNET v2.4):
  - 通道1: 0-3kHz (低频鸣叫)
  - 通道2: 500Hz-15kHz (高频鸣唱)
- **EfficientNet backbone**: 深度可分离卷积 + SE注意力，参数效率远超ResNet
- **原型学习头**: 每类4个原型，OOD检测依据原型距离
- **Dropout**: 训练时0.3-0.5，推理时可用MC Dropout估计不确定性

### L3: 训练层 — 正则化防线
- **R-Drop**: 两次前向传播KL散度约束，防止依赖特定dropout mask
- **Label Smoothing**: 0.10-0.15，防止softmax过度自信
- **Weight Decay**: ≥1e-3 (AdamW)
- **Stochastic Depth**: Drop path rate 0.1-0.2
- **EMA**: 指数移动平均权重(decay=0.999)，泛化更好
- **早停**: patience=30-40 epochs，监控val_acc
- **Gap监控**: 实时监控 train_acc - val_acc，若>15pp则触发警告

### L4: 校准层 — 置信度修正
- **温度缩放(Temperature Scaling)**: 
  - 在验证集上用NLL网格搜索最优T
  - calibrated_logits = logits / T
  - 目标: ECE < 0.05
- **校准文件**: `backend/checkpoints/calibration.json`
- **定期重校准**: 每次模型更新后必须重新校准

### L5: 推理层 — 实时防护
- **集成推理**: Teacher + Student logits平均，降低单模型偏差
- **熵阈值**: normalized_entropy > 0.7 时标记为不可靠
- **置信度阈值**: top-1 confidence < 0.3 时标记为不可靠
- **Top-1/Top-2差距**: 若 top1_conf - top2_conf < 0.05 则标记为不确定
- **TTA**: 仅在鸟声时间方向不敏感时启用(默认关闭)

### L6: 地理先验层 — 空间过滤 (借鉴BirdNET)
- **物种分布范围**: 基于eBird/中国鸟类分布数据
- **季节性过滤**: 考虑迁徙鸟类的季节性出现
- **地理置信度调整**: 不在分布范围内的物种降低置信度

### L7: 后处理层 — 最终裁决
- **可靠性标签**: 每条预测附带 `reliable: bool`
- **不确定性元数据**: entropy, mc_uncertainty, prototype_distance
- **人工复核提示**: 当预测不可靠时，前端显示"建议人工确认"

## 检查清单 (每次模型更新必须执行)

```
□ 训练完成后 train/val gap < 10pp
□ ECE < 0.05 (温度校准后)
□ 幻觉(conf>0.9的错误预测) < 总错误的3%
□ 非事件类准确率 > 80%
□ calibration.json 已更新
□ 后端 load_model() 兼容新版本
□ predict_species() 返回 reliable 标签
□ 集成推理已启用(若可用)
```

## 监控指标

| 指标 | 健康范围 | 警告阈值 | 严重阈值 |
|------|---------|---------|---------|
| Train/Val Gap | <8pp | 8-15pp | >15pp |
| ECE | <0.05 | 0.05-0.10 | >0.10 |
| 幻觉率(>0.9) | <2% | 2-5% | >5% |
| 归一化熵(均值) | 0.3-0.6 | >0.7 | >0.85 |
| Top-1准确率 | >60% | 50-60% | <50% |

## 版本演进记录

| 版本 | 架构 | Val Acc | 幻觉(>0.9) | Gap | 关键改进 |
|------|------|---------|-----------|-----|---------|
| v1 | ResNet | 54.47% | N/A | N/A | 基线 |
| v2 | ResNet+Focal+EMA | 56.83% | N/A | N/A | Focal Loss |
| v3 | SE-ResNet KD | 60.50% | 19 | +14pp | 知识蒸馏 |
| v4 | SE-ResNet+R-Drop | 61.68% | 9 | -10pp | R-Drop正则 |
| v5 | EfficientNet+Dual | 目标>70% | 目标<5 | 目标<5pp | 全新架构 |
