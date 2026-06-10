# 国家自然科学基金申请书

## 基于卷积神经网络的中国鸟类声纹智能识别与生物多样性监测平台

**项目类别：** 面上项目 / 青年科学基金项目

**申请代码：** C0305（生态学-生物多样性与保护生态学）

**关键词：** 生物声学；卷积神经网络；鸟类多样性监测；被动声学监测；海南鳽

---

## 一、立项依据与研究内容

### 1.1 研究背景

全球生物多样性正以前所未有的速度丧失（IPBES, 2019）。鸟类作为生态系统健康的重要指示类群，其多样性监测对理解和保护生态系统至关重要（Şekercioğlu et al., 2004）。中国拥有1505种鸟类，其中包括海南鳽（*Gorsachius magnificus*，EN）、朱鹮（*Nipponia nippon*，EN）等多种全球受威胁物种。

传统鸟类调查依赖样线法和样点法，受限于调查员经验、时间覆盖和空间尺度。被动声学监测（Passive Acoustic Monitoring, PAM）通过在野外部署录音设备，能够实现连续、非侵入性的鸟类群落监测（Gibb et al., 2019）。然而，海量声学数据的人工分析成本极高——每小时录音平均需要5-10小时的人工审核时间。

Sugai et al. (2026) 在 *Methods in Ecology and Evolution* 上的系统性综述明确指出：**传统声学指数（ACI、NDSI、ADI等）不适合用于生物多样性研究**。该研究从五个维度论证了声学指数的根本性缺陷：(1) 缺乏理论基础——声学生态位假说已被否定；(2) 无法识别具体物种；(3) 缺乏跨类群/生态系统通用性；(4) 统计陷阱普遍——75%研究未验证指数有效性；(5) 不支持入侵种检测和种群趋势评估等保护决策需求。论文明确推荐采用**基于物种的方法（species-based approach）**，即利用深度学习（特别是卷积神经网络）直接从声音中识别物种，再计算基于物种的多样性指标。

国际上，Cornell Lab 的 BirdNET（Kahl et al., 2021）基于 EfficientNet 架构，已覆盖全球6500+种鸟类，但在中国本土物种的识别精度有限；Google 的 Perch 生物声学基础模型尚处于研究阶段；acoupi（2025）和 OpenSoundscape 等框架提供了工具箱，但缺乏面向中国鸟类的专门优化。**目前尚无面向中国鸟类、集成深度学习识别与生物多样性评估的一体化平台**。

### 1.2 科学问题

本项目拟解决以下科学问题：

1. **物种识别精度**：如何在训练数据有限（部分物种录音<50条）的条件下，实现中国鸟类声纹的高精度物种级识别？
2. **多样性推断可靠性**：从自动化检测结果到生物多样性指标估计的链条中，如何系统性处理假阳性/假阴性，获得可靠的多样性推断？
3. **时空尺度扩展**：如何利用分布式野外设备网络，实现景观尺度的连续鸟类多样性监测？

### 1.3 研究内容

#### 内容一：ConvNeXt-Tiny 鸟类声纹识别模型优化

- 基于 ConvNeXt-Tiny 架构（Liu et al., 2022），结合双通道 Mel 频谱输入（低频 0-3kHz + 高频 500Hz-15kHz），构建覆盖中国200+种鸟类的识别模型
- 引入**原型学习头（Prototypical Head）**实现少样本物种识别，解决稀有物种（如海南鳽）训练数据匮乏的问题
- 构建 Teacher-Student 知识蒸馏框架，将 ConvNeXt-Tiny（~28M参数）蒸馏为 ConvNeXt-Pico（~5.5M参数），适配树莓派等边缘设备
- 集成 OOD（Out-of-Distribution）检测模块，基于能量分数和原型距离，自动拒绝非鸟声和未知物种输入

#### 内容二：生物多样性智能评估框架

- 基于 Sugai et al. (2026) 的推荐，直接从物种检测结果计算 Alpha 多样性（Shannon、Simpson、Chao1、Fisher's α）、Beta 多样性（Jaccard、Sørensen、Bray-Curtis、Whittaker）和功能多样性（FRic、FEve、FDis; Cadotte et al., 2011）
- 实现 Beta 多样性分解——区分周转（turnover）和嵌套（nestedness）组分（Socolar et al., 2016）
- 构建检测验证工作流：机器自动检测 → 人工审核 → 确认/拒绝，系统追踪假阳性/假阴性率
- 生成占域模型（Occupancy Modeling; MacKenzie et al., 2002）所需的检测/非检测矩阵，正确处理不完美检测

#### 内容三：实时监测与野外部署系统

- 开发基于 WebSocket 的实时音频流分析系统，支持多设备同时在线监测
- 实现地理-季节过滤机制（参考 BirdNET 的 eBird 分布过滤），根据设备位置和当前季节缩小候选物种范围
- 将 Student 模型导出为 ONNX/TFLite 格式并进行 INT8 量化，实现边缘设备（树莓派 4B + USB 麦克风）的本地推理
- 开发声学嵌入空间分析模块，利用 HDBSCAN 无监督聚类发现未知声学模式

#### 内容四：海南鳽专项监测示范

- 以海南鳽（*Gorsachius magnificus*）为示范物种，在广西弄岗、广东南昆山等已知栖息地部署监测网络
- 海南鳽为全球濒危（EN）物种，夜行性、叫声独特（主频 300-2500Hz），传统调查方法难以监测
- 利用本平台实现海南鳽叫声的自动检测、栖息地占域概率估计，并结合物种分布模型（SDM）评估潜在适宜栖息地

### 1.4 技术路线

```
Xeno-canto/Macaulay → 训练数据 → ConvNeXt-V7 模型训练
    ↓                                    ↓
双通道Mel频谱      →        Teacher → 知识蒸馏 → Student(边缘部署)
    ↓                                    ↓
原型学习 + OOD检测  →   推理引擎(PyTorch/ONNX)
    ↓                                    ↓
FastAPI 后端       →   Web平台 / CLI / 桌面.exe
    ↓                                    ↓
多样性评估框架      →   α/β/功能多样性 + 占域模型
    ↓                                    ↓
野外设备网络       →   实时监测 + 海南鳽专项示范
```

### 1.5 创新性

1. **模型创新**：首次将 ConvNeXt + 多头注意力池化 + 原型学习 + OOD 检测组合应用于鸟类声纹识别，在有限训练数据条件下兼顾精度和鲁棒性
2. **方法创新**：直接回应 Sugai et al. (2026) 对声学指数的批判，构建从物种检测到多样性推断的完整、可靠的分析链
3. **应用创新**：聚焦中国本土鸟类（特别是受威胁物种），提供从模型训练到野外部署到保护决策的一站式解决方案

---

## 二、研究基础与工作条件

### 2.1 已有工作基础

项目团队已完成以下前期工作：

1. **平台开发**：已建成 "中国鸟声智能识别与生物多样性评估平台" v7.0，包含：
   - ConvNeXt-Tiny/Pico V7 模型架构（含双通道Mel、MAP注意力池化、原型学习头、OOD检测）
   - FastAPI 后端 + React 前端，30+ API 端点
   - 实时 WebSocket 音频流分析
   - 完整的 Alpha/Beta/功能多样性计算框架
   - 检测验证工作流和占域模型数据准备
   - CLI 命令行工具和 ONNX 轻量推理引擎
   - 桌面 .exe 打包方案

2. **数据基础**：
   - 中国鸟类物种数据库（280+ 种），含分类、保护等级、功能性状、声学特征
   - 通过 Xeno-canto API 可获取中国鸟类录音数据

3. **SDM 研究**：已完成海南鳽物种分布模型研究，投稿 *Science of the Total Environment*

### 2.2 参考文献

- Cadotte, M. W., et al. (2011). Beyond species: functional diversity and the maintenance of ecological processes and services. *Journal of Applied Ecology*, 48(5), 1079-1087.
- Gibb, R., et al. (2019). Emerging opportunities and challenges for passive acoustics in ecological assessment and monitoring. *Methods in Ecology and Evolution*, 10(2), 169-185.
- Kahl, S., et al. (2021). BirdNET: A deep learning solution for avian diversity monitoring. *Ecological Informatics*, 61, 101236.
- Liu, Z., et al. (2022). A ConvNet for the 2020s. *CVPR*.
- MacKenzie, D. I., et al. (2002). Estimating site occupancy rates when detection probabilities are less than one. *Ecology*, 83(8), 2248-2255.
- Socolar, J. B., et al. (2016). How should beta-diversity inform biodiversity conservation? *Trends in Ecology & Evolution*, 31(1), 67-80.
- Sugai, L. S. M., et al. (2026). Acoustic indices are not useful for biodiversity research. *Methods in Ecology and Evolution*.
- Santiago-Alarcon, D., & MacGregor-Fors, I. (2025). acoupi: An Open-Source Python Framework for Deploying Bioacoustic AI Models on Edge Devices. *arXiv:2501.17841*.

---

## 三、经费预算

| 科目 | 金额（万元） | 说明 |
|------|-------------|------|
| 设备费 | 15 | 树莓派4B × 20台、USB麦克风 × 20、防水外壳、太阳能供电模块 |
| 材料费 | 5 | SD卡、网络SIM卡、线缆、安装材料 |
| 差旅费 | 10 | 广西弄岗、广东南昆山等野外部署与维护 |
| GPU训练费 | 8 | 云GPU租用（A100/V100），用于模型训练和优化 |
| 数据标注费 | 5 | 专家鸟声鉴定、训练数据清洗与验证 |
| 会议交流费 | 5 | 国际/国内学术会议论文发表与交流 |
| 劳务费 | 10 | 研究生助研津贴 |
| 其他 | 2 | 开源社区运维、域名、服务器 |
| **合计** | **60** | |

---

## 四、预期成果

### 4.1 学术成果
1. 发表 SCI 论文 3-4 篇（*Ecological Informatics*, *Methods in Ecology and Evolution*, *Biodiversity and Conservation*, *Biological Conservation*）
2. 申请软件著作权 1 项（平台系统）
3. 开源代码发布在 GitHub

### 4.2 应用成果
1. 开源 "中国鸟声智能识别与生物多样性评估平台"（覆盖 200+ 中国鸟类）
2. 海南鳽等濒危物种的声学监测数据集与占域概率图
3. 边缘部署方案（树莓派 + ONNX 推理）和桌面应用

### 4.3 人才培养
1. 培养博士/硕士研究生 2-3 名
2. 培训生态学研究人员使用平台工具

---

## 五、研究计划与时间安排

| 年份 | 主要工作 |
|------|---------|
| 第1年 | 数据收集（Xeno-canto + 野外录音）；模型训练与优化；平台核心功能完善 |
| 第2年 | 野外设备网络部署（弄岗、南昆山等站点）；实时监测系统联调；多样性评估验证 |
| 第3年 | 海南鳽专项监测数据分析；论文撰写与投稿；平台开源发布与推广 |

---

*本申请基于已有的平台开发基础（v7.0），重点聚焦模型训练、野外部署和科学验证三个维度，旨在填补中国鸟类声学智能监测领域的空白。*
