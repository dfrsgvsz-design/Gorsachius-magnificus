# -*- coding: utf-8 -*-
"""Step 3: PLUS 简化版实施 - LEAS(随机森林学发展概率) + CARS(贪心分配)
留一回测：用 2010+2015 训练 → 模拟 2020 → 与实际 2020 对比 → OA/Kappa/FoM
"""
import os
import time
import numpy as np
import rasterio
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import cohen_kappa_score, classification_report
import warnings
warnings.filterwarnings('ignore')

WORK = r'E:\大学\万物春\erci\_plus_workspace'
NODATA_LU = 15
CLASSES = [1, 2, 3, 4, 5, 7, 8]  # gridcode (跳过 6)
CLASS_NAMES = {1: '耕地', 2: '林地', 3: '灌木', 4: '草地',
               5: '水域', 7: '未利用地', 8: '建设用地'}

# 读取所有栅格
print('==== 读取栅格 ====')

def read_tif(name):
    with rasterio.open(os.path.join(WORK, name)) as src:
        return src.read(1), src.nodata, src.profile.copy()

lu_2010, _, _ = read_tif('lu_2010.tif')
lu_2015, _, _ = read_tif('lu_2015.tif')
lu_2020, _, _ = read_tif('lu_2020.tif')
lu_2025, _, _ = read_tif('lu_2025.tif')
dem, dem_nd, _ = read_tif('dem.tif')
slope, slope_nd, _ = read_tif('slope.tif')
aspect, aspect_nd, _ = read_tif('aspect.tif')
dist_water, _, _ = read_tif('dist_water.tif')
dist_built, _, _ = read_tif('dist_built.tif')
dist_center, _, _ = read_tif('dist_center.tif')

print(f'  栅格 shape: {lu_2010.shape}')

# 有效像元 mask（所有图层都有效）
valid_mask = (
    (lu_2010 != NODATA_LU)
    & (lu_2015 != NODATA_LU)
    & (lu_2020 != NODATA_LU)
    & (dem != dem_nd)
    & (slope != slope_nd)
)
print(f'  有效像元: {valid_mask.sum():,} / {valid_mask.size:,}')

# 构造特征矩阵（每行一个有效像元，6 个特征）
features = np.stack([
    dem.astype(np.float32),
    slope.astype(np.float32),
    aspect.astype(np.float32),
    dist_water.astype(np.float32),
    dist_built.astype(np.float32),
    dist_center.astype(np.float32),
], axis=-1)
FEAT_NAMES = ['DEM', 'Slope', 'Aspect', 'DistWater', 'DistBuilt', 'DistCenter']

idx_valid = np.where(valid_mask.ravel())[0]
X_all = features.reshape(-1, 6)[idx_valid]
y_2010 = lu_2010.ravel()[idx_valid]
y_2015 = lu_2015.ravel()[idx_valid]
y_2020 = lu_2020.ravel()[idx_valid]
y_2025 = lu_2025.ravel()[idx_valid]
print(f'  特征矩阵: {X_all.shape}')

# ============================================================
# Phase 1: LEAS - 学习 2010→2015 的发展概率面
# 为每个目标类 c 训练二元 RF（其他像元 → c）
# ============================================================
print('\n==== LEAS: 训练 2010→2015 发展概率 ====')

# 对每个 c 训练
prob_2015 = {}  # c -> 概率向量 (n_valid,)
for c in CLASSES:
    t0 = time.time()
    # 正样本：2010!=c & 2015==c (扩展)
    expand_mask = (y_2010 != c) & (y_2015 == c)
    n_pos = expand_mask.sum()
    if n_pos < 50:
        print(f'  [c={c} {CLASS_NAMES[c]}] 扩展样本不足({n_pos})，跳过训练，使用均匀概率')
        prob_2015[c] = np.full(len(X_all), 0.01, dtype=np.float32)
        continue

    # 负样本：2010!=c & 2015!=c（未发展为 c）
    nonexpand_mask = (y_2010 != c) & (y_2015 != c)
    # 抽样负样本（与正样本 1:5）
    n_neg = min(n_pos * 5, nonexpand_mask.sum())
    neg_idx = np.where(nonexpand_mask)[0]
    np.random.seed(42)
    if len(neg_idx) > n_neg:
        neg_idx = np.random.choice(neg_idx, n_neg, replace=False)

    pos_idx = np.where(expand_mask)[0]
    train_idx = np.concatenate([pos_idx, neg_idx])
    X_tr = X_all[train_idx]
    y_tr = np.concatenate([np.ones(len(pos_idx)), np.zeros(len(neg_idx))])

    rf = RandomForestClassifier(
        n_estimators=30, max_depth=12,
        min_samples_leaf=10, n_jobs=-1, random_state=42,
    )
    rf.fit(X_tr, y_tr)
    # 在 2015 上预测概率
    prob = rf.predict_proba(X_all)[:, 1].astype(np.float32)
    prob_2015[c] = prob
    elapsed = time.time() - t0
    print(f'  [c={c} {CLASS_NAMES[c]}] 正样本={n_pos:6d} 负样本={n_neg:6d}, '
          f'mean_prob={prob.mean():.3f}, max={prob.max():.3f}, train_t={elapsed:.1f}s')


# ============================================================
# Phase 2: Markov 链需求预测
# 用 2010→2015 的转移概率 → 推算 2015→2020 需求
# ============================================================
print('\n==== Markov 需求预测 (2010→2015→2020) ====')

# 转移矩阵 T (i,j) = P(2015=j | 2010=i)
n_class = len(CLASSES)
class_to_idx = {c: i for i, c in enumerate(CLASSES)}
T = np.zeros((n_class, n_class))
for i, c_i in enumerate(CLASSES):
    mask_i = (y_2010 == c_i)
    if mask_i.sum() == 0:
        continue
    for j, c_j in enumerate(CLASSES):
        T[i, j] = ((y_2010 == c_i) & (y_2015 == c_j)).sum() / mask_i.sum()
print('转移矩阵 T:')
print('       ', '  '.join(f'{CLASS_NAMES[c]:>4s}' for c in CLASSES))
for i, c_i in enumerate(CLASSES):
    print(f'  {CLASS_NAMES[c_i]:>4s} ', '  '.join(f'{T[i,j]:.3f}' for j in range(n_class)))

# 2015 各地类像元数
n_2015 = np.array([(y_2015 == c).sum() for c in CLASSES])
# 2020 需求 = T.T @ n_2015
demand_2020 = (n_2015[:, None] * T).sum(axis=0).astype(int)
actual_2020 = np.array([(y_2020 == c).sum() for c in CLASSES])
print(f'\n  类别       2015实测    2020需求    2020实测   误差%')
for i, c in enumerate(CLASSES):
    err = (demand_2020[i] - actual_2020[i]) / actual_2020[i] * 100 if actual_2020[i] > 0 else 0
    print(f'  {CLASS_NAMES[c]:6s} {n_2015[i]:10d}  {demand_2020[i]:10d}  {actual_2020[i]:10d}  {err:+.2f}%')

# 校准需求：用实际 2020 作为 ground truth（因为是留一回测，知道答案）
# 实际 CARS 应该用 Markov 推算，这里我们故意用稍偏的 Markov 推算（更接近真实建模）
target_demand = demand_2020.copy()


# ============================================================
# Phase 3: CARS - 基于概率面贪心分配
# 起点 lu_2015，按 Markov 需求调整到 lu_2020_pred
# ============================================================
print('\n==== CARS: 模拟 2015→2020 ====')

sim_2020 = y_2015.copy()

for c_idx, c in enumerate(CLASSES):
    current = (sim_2020 == c).sum()
    target = target_demand[c_idx]
    diff = target - current
    if diff > 0:
        # 增加 c：从其他类中找 prob_c 最高的 diff 个像元转化
        prob = prob_2015[c]
        non_c_mask = (sim_2020 != c)
        # 取 non_c 中概率最高的 diff 个
        candidate_idx = np.where(non_c_mask)[0]
        if len(candidate_idx) == 0 or diff > len(candidate_idx):
            diff = len(candidate_idx)
        # 取 prob 最高的 diff 个
        top_idx = candidate_idx[np.argsort(-prob[candidate_idx])[:diff]]
        sim_2020[top_idx] = c
    elif diff < 0:
        # 减少 c：从 c 像元中找 prob_c 最低的 |diff| 个转化为别的类
        # 简化：转化为该位置的"最可能其他类"（用 2015 类）
        # 但简化为：转化为 prob 最高的非 c 目标类
        # 这一步比较复杂，简化为不主动减少（依赖前面其他 c 的增加来"挤占"）
        pass

print('  分配后各类像元数 vs 目标需求:')
for i, c in enumerate(CLASSES):
    sim_c = (sim_2020 == c).sum()
    print(f'    {CLASS_NAMES[c]:6s}: sim={sim_c:8d}, target={target_demand[i]:8d}, '
          f'actual={actual_2020[i]:8d}, diff_to_actual={sim_c - actual_2020[i]:+d}')


# ============================================================
# Phase 4: 精度评估
# ============================================================
print('\n==== 精度评估: 模拟 2020 vs 实际 2020 ====')

# 总体精度 OA
oa = (sim_2020 == y_2020).mean()
print(f'  OA (Overall Accuracy):  {oa:.4f} ({oa*100:.2f}%)')

# Kappa
kappa = cohen_kappa_score(y_2020, sim_2020, labels=CLASSES)
print(f'  Kappa:                  {kappa:.4f}')

# FoM (Figure of Merit) - 只考虑变化区域
# A = 实际变化但模拟未变化  (FN)
# B = 实际变化且模拟变化为同类 (TP)
# C = 实际变化且模拟变化为不同类 (其他错误)
# D = 实际未变化但模拟变化 (FP)
# FoM = B / (A + B + C + D)
actual_change = (y_2015 != y_2020)
sim_change = (y_2015 != sim_2020)
A = (actual_change & ~sim_change).sum()  # 实际变化但模拟没变
B = (actual_change & sim_change & (sim_2020 == y_2020)).sum()  # 变化且类对
C = (actual_change & sim_change & (sim_2020 != y_2020)).sum()  # 变化但类错
D = (~actual_change & sim_change).sum()  # 实际没变模拟变了

fom_denom = A + B + C + D
fom = B / fom_denom if fom_denom > 0 else 0
print(f'  FoM (Figure of Merit):  {fom:.4f}')
print(f'    A (miss):     {A:8d}')
print(f'    B (correct):  {B:8d}')
print(f'    C (wrong):    {C:8d}')
print(f'    D (false_chg):{D:8d}')

# 各类详细精度
print('\n  各类用户精度 (UA) / 制图精度 (PA):')
for c in CLASSES:
    pred_c = (sim_2020 == c)
    actual_c = (y_2020 == c)
    tp = (pred_c & actual_c).sum()
    fp = (pred_c & ~actual_c).sum()
    fn = (~pred_c & actual_c).sum()
    ua = tp / (tp + fp) if (tp + fp) > 0 else 0
    pa = tp / (tp + fn) if (tp + fn) > 0 else 0
    print(f'    {CLASS_NAMES[c]:6s}: UA={ua:.3f}, PA={pa:.3f}, '
          f'TP={tp:6d}, FP={fp:6d}, FN={fn:6d}')


# ============================================================
# Phase 5: 同样的方法预测 2025 (训练 2015→2020, 应用到 2020)
# 用于交叉验证 2025 PLUS 模拟的合理性
# ============================================================
print('\n==== 交叉验证: 训练 2015→2020 → 预测 2025 → vs 实际 2025 ====')

# 重训练 prob_2020
prob_2020 = {}
for c in CLASSES:
    expand_mask = (y_2015 != c) & (y_2020 == c)
    n_pos = expand_mask.sum()
    if n_pos < 50:
        prob_2020[c] = np.full(len(X_all), 0.01, dtype=np.float32)
        continue
    nonexpand_mask = (y_2015 != c) & (y_2020 != c)
    n_neg = min(n_pos * 5, nonexpand_mask.sum())
    neg_idx = np.where(nonexpand_mask)[0]
    np.random.seed(42)
    if len(neg_idx) > n_neg:
        neg_idx = np.random.choice(neg_idx, n_neg, replace=False)
    pos_idx = np.where(expand_mask)[0]
    X_tr = X_all[np.concatenate([pos_idx, neg_idx])]
    y_tr = np.concatenate([np.ones(len(pos_idx)), np.zeros(len(neg_idx))])
    rf = RandomForestClassifier(n_estimators=30, max_depth=12,
                                 min_samples_leaf=10, n_jobs=-1, random_state=42)
    rf.fit(X_tr, y_tr)
    prob_2020[c] = rf.predict_proba(X_all)[:, 1].astype(np.float32)

# Markov 2020->2025 (从 2015→2020 推算转移矩阵)
T2 = np.zeros((n_class, n_class))
for i, c_i in enumerate(CLASSES):
    mask_i = (y_2015 == c_i)
    if mask_i.sum() == 0:
        continue
    for j, c_j in enumerate(CLASSES):
        T2[i, j] = ((y_2015 == c_i) & (y_2020 == c_j)).sum() / mask_i.sum()
n_2020 = np.array([(y_2020 == c).sum() for c in CLASSES])
demand_2025 = (n_2020[:, None] * T2).sum(axis=0).astype(int)
actual_2025 = np.array([(y_2025 == c).sum() for c in CLASSES])
print(f'  类别       2020实测    2025需求    2025实测  误差%')
for i, c in enumerate(CLASSES):
    err = (demand_2025[i] - actual_2025[i]) / actual_2025[i] * 100 if actual_2025[i] > 0 else 0
    print(f'  {CLASS_NAMES[c]:6s} {n_2020[i]:10d}  {demand_2025[i]:10d}  {actual_2025[i]:10d}  {err:+.2f}%')

# CARS 模拟 2025
sim_2025 = y_2020.copy()
for c_idx, c in enumerate(CLASSES):
    current = (sim_2025 == c).sum()
    diff = demand_2025[c_idx] - current
    if diff > 0:
        prob = prob_2020[c]
        non_c_mask = (sim_2025 != c)
        candidate_idx = np.where(non_c_mask)[0]
        if diff > len(candidate_idx):
            diff = len(candidate_idx)
        top_idx = candidate_idx[np.argsort(-prob[candidate_idx])[:diff]]
        sim_2025[top_idx] = c

oa_25 = (sim_2025 == y_2025).mean()
kappa_25 = cohen_kappa_score(y_2025, sim_2025, labels=CLASSES)
actual_change25 = (y_2020 != y_2025)
sim_change25 = (y_2020 != sim_2025)
A25 = (actual_change25 & ~sim_change25).sum()
B25 = (actual_change25 & sim_change25 & (sim_2025 == y_2025)).sum()
C25 = (actual_change25 & sim_change25 & (sim_2025 != y_2025)).sum()
D25 = (~actual_change25 & sim_change25).sum()
fom_25 = B25 / (A25 + B25 + C25 + D25) if (A25 + B25 + C25 + D25) > 0 else 0
print(f'\n  2025 模拟精度:')
print(f'    OA={oa_25:.4f}, Kappa={kappa_25:.4f}, FoM={fom_25:.4f}')


# ============================================================
# 最终输出
# ============================================================
print('\n')
print('=' * 70)
print('最终精度指标 (用于论文中替换占位数值)')
print('=' * 70)
print(f'留一回测 (2010+2015 训练 → 模拟 2020 → vs 实际 2020):')
print(f'  - 总体精度 OA:     {oa*100:.2f}%')
print(f'  - Kappa 系数:      {kappa:.3f}')
print(f'  - FoM:             {fom:.3f}')
print(f'交叉验证 (2015+2020 训练 → 模拟 2025 → vs 实际 2025):')
print(f'  - 总体精度 OA:     {oa_25*100:.2f}%')
print(f'  - Kappa 系数:      {kappa_25:.3f}')
print(f'  - FoM:             {fom_25:.3f}')

# 保存结果
import json
result = {
    'leave_one_out_2020': {
        'OA': float(oa),
        'Kappa': float(kappa),
        'FoM': float(fom),
        'A_miss': int(A), 'B_correct': int(B), 'C_wrong': int(C), 'D_false': int(D),
    },
    'cross_2025': {
        'OA': float(oa_25),
        'Kappa': float(kappa_25),
        'FoM': float(fom_25),
    },
    'class_accuracy_2020': {},
    'features': FEAT_NAMES,
    'classes': {c: CLASS_NAMES[c] for c in CLASSES},
}
for c in CLASSES:
    pred_c = (sim_2020 == c)
    actual_c = (y_2020 == c)
    tp = int((pred_c & actual_c).sum())
    fp = int((pred_c & ~actual_c).sum())
    fn = int((~pred_c & actual_c).sum())
    result['class_accuracy_2020'][CLASS_NAMES[c]] = {
        'UA': tp / (tp + fp) if (tp + fp) > 0 else 0,
        'PA': tp / (tp + fn) if (tp + fn) > 0 else 0,
        'TP': tp, 'FP': fp, 'FN': fn,
    }

with open(os.path.join(WORK, 'plus_accuracy.json'), 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(f'\n精度结果保存至: {WORK}\\plus_accuracy.json')
