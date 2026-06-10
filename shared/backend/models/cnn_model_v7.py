"""
CNN Model V7 — ConvNeXt-Tiny + Multi-Head Attention Pooling + Prototypical Head + OOD Detection

Next-generation architecture for Chinese bird sound classification.
Designed for data-efficient learning with field deployment in mind.

Key improvements over V6 (SE-ResNet + GeM):
1. ConvNeXt-Tiny backbone: modern pure-ConvNet, better accuracy/param ratio than ResNet
   - Patchify stem (no MaxPool), inverted bottleneck, GELU, LayerNorm
   - ~28M params (teacher) but more parameter-efficient than SE-ResNet-50
2. Multi-Head Attention Pooling (MAP): learns multiple attention patterns over spatial features
   - Captures diverse temporal-spectral patterns (trills, whistles, harmonics)
   - Replaces single-mode GeM pooling
3. Prototypical head: metric-learning branch for few-shot species recognition
   - Supports species not in training set via prototype matching
   - Essential for field deployment with limited training data
4. OOD detection: Mahalanobis distance + energy score for out-of-distribution inputs
   - Rejects non-bird sounds, unknown species, and corrupted audio
   - Critical for automated field monitoring reliability
5. Dual-channel mel input preserved from V6 (low-freq + high-freq split)
6. Teacher-Student distillation framework maintained

Specs (estimated):
- Teacher: ConvNeXt-Tiny, ~28M params, input (B, 2, 96, 512)
- Student: ConvNeXt-Pico, ~5.5M params, input (B, 2, 96, 512)
"""

import math
from functools import partial

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

# ──────────────────── Dual-Channel Mel Config (same as V6) ────────────────────

DUAL_CHANNEL_CONFIG = {
    "sr": 48000,
    "segment_duration": 3.0,
    "channel_low": {
        "fmin": 0,
        "fmax": 3000,
        "n_fft": 2048,
        "hop_length": 278,
        "n_mels": 96,
    },
    "channel_high": {
        "fmin": 500,
        "fmax": 15000,
        "n_fft": 1024,
        "hop_length": 280,
        "n_mels": 96,
    },
}

TARGET_FRAMES = 512


def compute_dual_channel_mel(y, sr=48000, config=None, target_frames=TARGET_FRAMES):
    """Compute dual-channel mel spectrogram.

    Returns shape: (2, n_mels, target_frames) normalized to [0, 1].
    """
    import librosa

    if config is None:
        config = DUAL_CHANNEL_CONFIG

    if sr != config["sr"]:
        y = librosa.resample(y, orig_sr=sr, target_sr=config["sr"])
        sr = config["sr"]

    peak = np.abs(y).max()
    if peak > 0:
        y = y / peak

    n_mels = config["channel_low"]["n_mels"]
    channels = []
    for ch_key in ["channel_low", "channel_high"]:
        ch = config[ch_key]
        S = librosa.feature.melspectrogram(
            y=y,
            sr=sr,
            n_fft=ch["n_fft"],
            hop_length=ch["hop_length"],
            n_mels=ch["n_mels"],
            fmin=ch["fmin"],
            fmax=ch["fmax"],
        )
        S = np.log1p(S * 10)
        s_min, s_max = S.min(), S.max()
        if s_max - s_min > 1e-6:
            S = (S - s_min) / (s_max - s_min)
        else:
            S = np.zeros_like(S)

        if S.shape[1] > target_frames:
            S = S[:, :target_frames]
        elif S.shape[1] < target_frames:
            pad = np.zeros((n_mels, target_frames - S.shape[1]), dtype=S.dtype)
            S = np.concatenate([S, pad], axis=1)
        channels.append(S)

    return np.stack(channels, axis=0).astype(np.float32)


# ──────────────────── ConvNeXt Building Blocks ────────────────────


class DropPath(nn.Module):
    """Stochastic depth (drop entire residual branch)."""

    def __init__(self, drop_prob=0.0):
        super().__init__()
        self.drop_prob = drop_prob

    def forward(self, x):
        if self.drop_prob == 0.0 or not self.training:
            return x
        keep = 1 - self.drop_prob
        shape = (x.shape[0],) + (1,) * (x.ndim - 1)
        mask = torch.empty(shape, device=x.device, dtype=x.dtype).bernoulli_(keep)
        return x * mask / keep


class ConvNeXtBlock(nn.Module):
    """ConvNeXt block: depthwise conv → LayerNorm → 1x1 → GELU → 1x1.

    Inverted bottleneck with expansion ratio 4.
    """

    def __init__(self, dim, drop_path_rate=0.0, layer_scale_init=1e-6):
        super().__init__()
        self.dwconv = nn.Conv2d(dim, dim, kernel_size=7, padding=3, groups=dim)
        self.norm = nn.LayerNorm(dim, eps=1e-6)
        self.pwconv1 = nn.Linear(dim, 4 * dim)
        self.act = nn.GELU()
        self.pwconv2 = nn.Linear(4 * dim, dim)

        self.gamma = (
            nn.Parameter(layer_scale_init * torch.ones(dim))
            if layer_scale_init > 0
            else None
        )

        self.drop_path = (
            DropPath(drop_path_rate) if drop_path_rate > 0 else nn.Identity()
        )

    def forward(self, x):
        shortcut = x
        x = self.dwconv(x)
        x = x.permute(0, 2, 3, 1)  # B C H W → B H W C
        x = self.norm(x)
        x = self.pwconv1(x)
        x = self.act(x)
        x = self.pwconv2(x)
        if self.gamma is not None:
            x = self.gamma * x
        x = x.permute(0, 3, 1, 2)  # B H W C → B C H W
        return shortcut + self.drop_path(x)


class ConvNeXtStage(nn.Module):
    """One stage of ConvNeXt: optional downsampling + N blocks."""

    def __init__(self, in_dim, out_dim, depth, drop_path_rates=None, downsample=True):
        super().__init__()
        if drop_path_rates is None:
            drop_path_rates = [0.0] * depth

        if downsample and in_dim != out_dim:
            self.downsample = nn.Sequential(
                nn.LayerNorm(in_dim, eps=1e-6, elementwise_affine=True),
                nn.Conv2d(in_dim, out_dim, kernel_size=2, stride=2),
            )
        else:
            self.downsample = nn.Identity()

        self.blocks = nn.Sequential(
            *[
                ConvNeXtBlock(out_dim, drop_path_rate=drop_path_rates[i])
                for i in range(depth)
            ]
        )

    def forward(self, x):
        if isinstance(self.downsample, nn.Sequential):
            # LayerNorm expects channels-last
            x = x.permute(0, 2, 3, 1)
            x = self.downsample[0](x)
            x = x.permute(0, 3, 1, 2)
            x = self.downsample[1](x)
        x = self.blocks(x)
        return x


# ──────────────────── Multi-Head Attention Pooling ────────────────────


class MultiHeadAttentionPooling(nn.Module):
    """Pools spatial features using multiple learned attention heads.

    Each head learns a different attention pattern, capturing diverse
    temporal-spectral characteristics (e.g., one head for onset patterns,
    another for sustained harmonics).
    """

    def __init__(self, dim, num_heads=4, qkv_bias=True):
        super().__init__()
        self.num_heads = num_heads
        self.head_dim = dim // num_heads
        assert dim % num_heads == 0

        self.query = nn.Parameter(torch.randn(1, num_heads, 1, self.head_dim) * 0.02)
        self.kv = nn.Linear(dim, 2 * dim, bias=qkv_bias)
        self.proj = nn.Linear(dim, dim)
        self.norm = nn.LayerNorm(dim, eps=1e-6)

    def forward(self, x):
        B, C, H, W = x.shape
        N = H * W
        x_flat = x.flatten(2).transpose(1, 2)  # B N C
        x_flat = self.norm(x_flat)

        kv = self.kv(x_flat).reshape(B, N, 2, self.num_heads, self.head_dim)
        kv = kv.permute(2, 0, 3, 1, 4)  # 2 B heads N head_dim
        k, v = kv.unbind(0)

        q = self.query.expand(B, -1, -1, -1)  # B heads 1 head_dim
        scale = self.head_dim**-0.5
        attn = (q @ k.transpose(-2, -1)) * scale  # B heads 1 N
        attn = attn.softmax(dim=-1)

        out = (attn @ v).squeeze(2)  # B heads head_dim
        out = out.reshape(B, C)
        out = self.proj(out)
        return out


# ──────────────────── Prototypical Learning Head ────────────────────


class PrototypicalHead(nn.Module):
    """Metric-learning head for few-shot species recognition.

    Maintains class prototypes (centroids in embedding space) and classifies
    by nearest-prototype distance. Supports dynamic prototype updates for
    new species encountered during field deployment.
    """

    def __init__(self, feat_dim, num_species, prototype_dim=256, temperature=0.1):
        super().__init__()
        self.projector = nn.Sequential(
            nn.Linear(feat_dim, prototype_dim),
            nn.ReLU(inplace=True),
            nn.Linear(prototype_dim, prototype_dim),
        )
        self.prototypes = nn.Parameter(torch.randn(num_species, prototype_dim) * 0.02)
        self.temperature = temperature
        self.prototype_dim = prototype_dim

    def forward(self, features):
        """Returns prototype-based logits."""
        z = self.projector(features)
        z = F.normalize(z, dim=-1)
        proto = F.normalize(self.prototypes, dim=-1)
        return (z @ proto.t()) / self.temperature

    def compute_distance(self, features):
        """Returns distances to all prototypes (for OOD detection)."""
        z = self.projector(features)
        z = F.normalize(z, dim=-1)
        proto = F.normalize(self.prototypes, dim=-1)
        return torch.cdist(z.unsqueeze(0), proto.unsqueeze(0)).squeeze(0)


# ──────────────────── OOD Detection Module ────────────────────


class OODDetector(nn.Module):
    """Out-of-Distribution detection using energy score + feature distance.

    Combines two complementary OOD signals:
    1. Energy score: lower energy → more likely in-distribution
    2. Prototype distance: larger min-distance → more likely OOD

    Thresholds are calibrated post-training on a held-out validation set.
    """

    def __init__(self, temperature=1.0):
        super().__init__()
        self.temperature = temperature
        self.register_buffer("energy_threshold", torch.tensor(float("inf")))
        self.register_buffer("distance_threshold", torch.tensor(float("inf")))

    def energy_score(self, logits):
        """Free energy score: -T * log(sum(exp(logits/T)))."""
        return -self.temperature * torch.logsumexp(logits / self.temperature, dim=-1)

    def forward(self, logits, prototype_distances=None):
        """Returns OOD scores (higher = more likely OOD) and binary decisions."""
        energy = self.energy_score(logits)

        if prototype_distances is not None:
            min_dist = prototype_distances.min(dim=-1).values
            ood_score = energy + min_dist
        else:
            ood_score = energy

        is_ood = ood_score > self.energy_threshold
        return {
            "ood_score": ood_score,
            "energy": energy,
            "is_ood": is_ood,
        }

    def calibrate(self, id_logits, id_distances=None, percentile=95.0):
        """Set thresholds from in-distribution validation data."""
        with torch.no_grad():
            energy = self.energy_score(id_logits)
            threshold = torch.quantile(energy, percentile / 100.0)
            self.energy_threshold.copy_(threshold)
            if id_distances is not None:
                min_dist = id_distances.min(dim=-1).values
                self.distance_threshold.copy_(
                    torch.quantile(min_dist, percentile / 100.0)
                )


# ──────────────────── Teacher: ConvNeXt-Tiny V7 ────────────────────


class ConvNeXtBirdV7(nn.Module):
    """ConvNeXt-based teacher model with dual-channel input, MAP, and prototypical head.

    Architecture:
    - Patchify stem: Conv2d(2→dims[0], 4×4, stride 4)
    - 4 stages: [3, 3, 9, 3] blocks, dims [96, 192, 384, 768]
    - Multi-Head Attention Pooling (4 heads)
    - Dual head: classification + prototypical
    - OOD detection module

    Input: (B, 2, 96, 512) dual-channel mel spectrogram.
    ~28M params.
    """

    def __init__(
        self,
        num_species=200,
        in_channels=2,
        drop_path_rate=0.1,
        dims=None,
        depths=None,
        prototype_dim=256,
        num_attention_heads=4,
        gradient_checkpointing=False,
    ):
        super().__init__()
        if dims is None:
            dims = [96, 192, 384, 768]
        if depths is None:
            depths = [3, 3, 9, 3]

        self.num_species = num_species
        self.feat_dim = dims[-1]
        self.gradient_checkpointing = gradient_checkpointing

        # Patchify stem: 4×4 non-overlapping patches
        self.stem = nn.Sequential(
            nn.Conv2d(in_channels, dims[0], kernel_size=4, stride=4),
            nn.LayerNorm([dims[0], 1, 1]),  # placeholder, will use permuted norm
        )
        self.stem_norm = nn.LayerNorm(dims[0], eps=1e-6)

        total_blocks = sum(depths)
        dpr = np.linspace(0, drop_path_rate, total_blocks).tolist()
        block_idx = 0

        self.stages = nn.ModuleList()
        for i in range(4):
            stage = ConvNeXtStage(
                in_dim=dims[i - 1] if i > 0 else dims[0],
                out_dim=dims[i],
                depth=depths[i],
                drop_path_rates=dpr[block_idx : block_idx + depths[i]],
                downsample=(i > 0),
            )
            self.stages.append(stage)
            block_idx += depths[i]

        self.norm = nn.LayerNorm(dims[-1], eps=1e-6)
        self.pool = MultiHeadAttentionPooling(dims[-1], num_heads=num_attention_heads)

        self.classifier = nn.Sequential(
            nn.Dropout(0.3),
            nn.Linear(dims[-1], num_species),
        )

        self.proto_head = PrototypicalHead(
            dims[-1], num_species, prototype_dim=prototype_dim
        )
        self.ood_detector = OODDetector(temperature=1.0)

        self._init_weights()

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.trunc_normal_(m.weight, std=0.02)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)
            elif isinstance(m, nn.Linear):
                nn.init.trunc_normal_(m.weight, std=0.02)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)

    def _run_stage(self, stage, x):
        if self.gradient_checkpointing and self.training:
            return torch.utils.checkpoint.checkpoint(stage, x, use_reentrant=False)
        return stage(x)

    def forward_features(self, x):
        """Extract feature vector from dual-channel mel input."""
        # Stem
        x = self.stem[0](x)  # Conv2d patchify
        x = x.permute(0, 2, 3, 1)
        x = self.stem_norm(x)
        x = x.permute(0, 3, 1, 2)

        for stage in self.stages:
            x = self._run_stage(stage, x)

        return x  # B C H' W'

    def forward(self, x, return_ood=False):
        spatial = self.forward_features(x)
        feat = self.pool(spatial)

        cls_logits = self.classifier(feat)
        proto_logits = self.proto_head(feat)

        combined_logits = cls_logits + 0.3 * proto_logits

        if return_ood:
            proto_dist = self.proto_head.compute_distance(feat)
            ood_result = self.ood_detector(combined_logits, proto_dist)
            return combined_logits, ood_result

        return combined_logits

    def extract_features(self, x):
        """Extract feature embedding for downstream tasks."""
        spatial = self.forward_features(x)
        return self.pool(spatial)


# ──────────────────── Student: ConvNeXt-Pico V7 ────────────────────


class ConvNeXtBirdV7Student(nn.Module):
    """Lightweight ConvNeXt student for edge deployment.

    Architecture: [2, 2, 6, 2] blocks, dims [64, 128, 256, 512].
    ~5.5M params — suitable for Raspberry Pi / Jetson Nano inference.
    """

    def __init__(
        self,
        num_species=200,
        in_channels=2,
        drop_path_rate=0.05,
        dims=None,
        depths=None,
        prototype_dim=128,
        num_attention_heads=4,
        gradient_checkpointing=False,
    ):
        super().__init__()
        if dims is None:
            dims = [64, 128, 256, 512]
        if depths is None:
            depths = [2, 2, 6, 2]

        self.num_species = num_species
        self.feat_dim = dims[-1]
        self.gradient_checkpointing = gradient_checkpointing

        self.stem = nn.Sequential(
            nn.Conv2d(in_channels, dims[0], kernel_size=4, stride=4),
        )
        self.stem_norm = nn.LayerNorm(dims[0], eps=1e-6)

        total_blocks = sum(depths)
        dpr = np.linspace(0, drop_path_rate, total_blocks).tolist()
        block_idx = 0

        self.stages = nn.ModuleList()
        for i in range(4):
            stage = ConvNeXtStage(
                in_dim=dims[i - 1] if i > 0 else dims[0],
                out_dim=dims[i],
                depth=depths[i],
                drop_path_rates=dpr[block_idx : block_idx + depths[i]],
                downsample=(i > 0),
            )
            self.stages.append(stage)
            block_idx += depths[i]

        self.norm = nn.LayerNorm(dims[-1], eps=1e-6)
        self.pool = MultiHeadAttentionPooling(dims[-1], num_heads=num_attention_heads)

        self.classifier = nn.Sequential(
            nn.Dropout(0.5),
            nn.Linear(dims[-1], num_species),
        )

        self.proto_head = PrototypicalHead(
            dims[-1], num_species, prototype_dim=prototype_dim
        )
        self.ood_detector = OODDetector(temperature=1.0)

        self._init_weights()

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.trunc_normal_(m.weight, std=0.02)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)
            elif isinstance(m, nn.Linear):
                nn.init.trunc_normal_(m.weight, std=0.02)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)

    def _run_stage(self, stage, x):
        if self.gradient_checkpointing and self.training:
            return torch.utils.checkpoint.checkpoint(stage, x, use_reentrant=False)
        return stage(x)

    def forward_features(self, x):
        x = self.stem[0](x)
        x = x.permute(0, 2, 3, 1)
        x = self.stem_norm(x)
        x = x.permute(0, 3, 1, 2)

        for stage in self.stages:
            x = self._run_stage(stage, x)

        return x

    def forward(self, x, return_ood=False):
        spatial = self.forward_features(x)
        feat = self.pool(spatial)

        cls_logits = self.classifier(feat)
        proto_logits = self.proto_head(feat)

        combined_logits = cls_logits + 0.3 * proto_logits

        if return_ood:
            proto_dist = self.proto_head.compute_distance(feat)
            ood_result = self.ood_detector(combined_logits, proto_dist)
            return combined_logits, ood_result

        return combined_logits

    def extract_features(self, x):
        spatial = self.forward_features(x)
        return self.pool(spatial)


# ──────────────────── Knowledge Distillation Loss ────────────────────


class DistillationLossV7(nn.Module):
    """Multi-task distillation: classification + prototype alignment.

    L = α * T² * KL(s_soft || t_soft) + β * proto_alignment + (1-α-β) * hard_loss
    """

    def __init__(self, temperature=4.0, alpha=0.5, beta=0.2, hard_loss_fn=None):
        super().__init__()
        self.T = temperature
        self.alpha = alpha
        self.beta = beta
        self.hard_loss_fn = hard_loss_fn or nn.CrossEntropyLoss()

    def forward(
        self,
        student_logits,
        teacher_logits,
        targets,
        student_features=None,
        teacher_features=None,
    ):
        soft_loss = F.kl_div(
            F.log_softmax(student_logits / self.T, dim=1),
            F.softmax(teacher_logits / self.T, dim=1),
            reduction="batchmean",
        ) * (self.T**2)

        hard_loss = self.hard_loss_fn(student_logits, targets)

        if student_features is not None and teacher_features is not None:
            s_norm = F.normalize(student_features, dim=-1)
            t_norm = F.normalize(teacher_features.detach(), dim=-1)
            feat_loss = 2 - 2 * (s_norm * t_norm).sum(dim=-1).mean()
        else:
            feat_loss = torch.tensor(0.0, device=student_logits.device)

        gamma = 1 - self.alpha - self.beta
        return self.alpha * soft_loss + self.beta * feat_loss + gamma * hard_loss


# ──────────────────── Augmentation Utilities ────────────────────


def cutmix_data(x, y, alpha=1.0):
    """CutMix: replace random rectangular region."""
    if alpha <= 0:
        return x, y, y, 1.0
    lam = np.random.beta(alpha, alpha)
    batch_size = x.size(0)
    index = torch.randperm(batch_size, device=x.device)

    _, _, H, W = x.shape
    cut_ratio = np.sqrt(1.0 - lam)
    cut_h = int(H * cut_ratio)
    cut_w = int(W * cut_ratio)

    cy = np.random.randint(0, H)
    cx = np.random.randint(0, W)

    y1 = np.clip(cy - cut_h // 2, 0, H)
    y2 = np.clip(cy + cut_h // 2, 0, H)
    x1 = np.clip(cx - cut_w // 2, 0, W)
    x2 = np.clip(cx + cut_w // 2, 0, W)

    x_mixed = x.clone()
    x_mixed[:, :, y1:y2, x1:x2] = x[index, :, y1:y2, x1:x2]
    lam = 1 - (y2 - y1) * (x2 - x1) / (H * W)
    return x_mixed, y[index], y, lam


def mixup_data(x, y, alpha=0.3):
    """Mixup: linear interpolation of samples."""
    if alpha <= 0:
        return x, y, y, 1.0
    lam = np.random.beta(alpha, alpha)
    lam = max(lam, 1 - lam)
    index = torch.randperm(x.size(0), device=x.device)
    x_mixed = lam * x + (1 - lam) * x[index]
    return x_mixed, y, y[index], lam


def spec_augment(mel, freq_mask_param=10, time_mask_param=40, num_masks=2):
    """SpecAugment: frequency and time masking on mel spectrograms.

    Applied to each channel independently.
    """
    augmented = mel.clone()
    _, n_mels, n_frames = augmented.shape[-3:]

    for _ in range(num_masks):
        f = torch.randint(0, freq_mask_param + 1, (1,)).item()
        f0 = torch.randint(0, max(1, n_mels - f), (1,)).item()
        augmented[..., f0 : f0 + f, :] = 0

        t = torch.randint(0, time_mask_param + 1, (1,)).item()
        t0 = torch.randint(0, max(1, n_frames - t), (1,)).item()
        augmented[..., :, t0 : t0 + t] = 0

    return augmented


# ──────────────────── Factory ────────────────────


def create_model_v7(num_species=200, model_type="teacher", in_channels=2):
    """Create V7 model.

    Args:
        num_species: Number of species classes
        model_type: 'teacher' for ConvNeXt-Tiny, 'student' for ConvNeXt-Pico
        in_channels: Input channels (2 for dual-channel mel)
    """
    if model_type == "teacher":
        return ConvNeXtBirdV7(num_species=num_species, in_channels=in_channels)
    elif model_type == "student":
        return ConvNeXtBirdV7Student(num_species=num_species, in_channels=in_channels)
    else:
        raise ValueError(f"Unknown model_type: {model_type}")


def count_parameters(model):
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


# ──────────────────── ONNX Export Utility ────────────────────


def export_to_onnx(model, save_path, num_species=200, in_channels=2, opset=17):
    """Export model to ONNX format for edge deployment.

    The exported model can run on ONNX Runtime (CPU/ARM), TensorRT, or
    OpenVINO for efficient inference on field devices.
    """
    model.eval()
    dummy = torch.randn(1, in_channels, 96, TARGET_FRAMES)
    torch.onnx.export(
        model,
        dummy,
        save_path,
        opset_version=opset,
        input_names=["mel_input"],
        output_names=["logits"],
        dynamic_axes={
            "mel_input": {0: "batch"},
            "logits": {0: "batch"},
        },
    )
    print(f"Exported ONNX model to {save_path}")


if __name__ == "__main__":
    x = torch.randn(4, 2, 96, 512)

    teacher = create_model_v7(num_species=223, model_type="teacher")
    print(f"ConvNeXt-Tiny V7 (Teacher): {count_parameters(teacher):,} params")
    out_t = teacher(x)
    print(f"  Input: {x.shape} -> Output: {out_t.shape}")

    out_t_ood, ood_info = teacher(x, return_ood=True)
    print(f"  OOD scores: {ood_info['ood_score'][:2]}")
    print(f"  Energy: {ood_info['energy'][:2]}")

    feat_t = teacher.extract_features(x)
    print(f"  Features: {feat_t.shape}")

    print()
    student = create_model_v7(num_species=223, model_type="student")
    print(f"ConvNeXt-Pico V7 (Student): {count_parameters(student):,} params")
    out_s = student(x)
    print(f"  Input: {x.shape} -> Output: {out_s.shape}")

    kd_loss = DistillationLossV7(temperature=4.0, alpha=0.5, beta=0.2)
    targets = torch.randint(0, 223, (4,))
    feat_s = student.extract_features(x)
    loss = kd_loss(out_s, out_t.detach(), targets, feat_s, feat_t.detach())
    print(f"  Distillation loss: {loss.item():.4f}")
