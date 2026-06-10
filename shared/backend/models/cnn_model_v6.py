"""
CNN Model V6 — SE-ResNet + Dual-Channel Mel + GeM Pooling

Refactored architecture combining best elements from V1-V5:
- SE-ResNet backbone with Stochastic Depth (V3: +3.67pp via distillation)
- Dual-channel mel spectrogram input (V5: BirdNET-style freq split)
- GeM (Generalized Mean) pooling (replaces GAP, learnable)
- Knowledge Distillation: Teacher SE-ResNet-50 → Student SE-ResNet-18

V6 changes vs V3:
1. Dual-channel mel: low-freq (0-3kHz) + high-freq (500Hz-15kHz)
   → captures bass calls AND high-pitched songs simultaneously
2. GeM pooling: learnable generalization of avg/max pooling
3. 48kHz sampling, 3s segments (BirdNET standard)
4. Configurable in_channels (2 for dual-channel)

Specs (RTX 3080 10GB):
- Teacher: SE-ResNet-50, ~26M params, input (B, 2, 96, 512)
- Student: SE-ResNet-18, ~11.4M params, input (B, 2, 96, 512)
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

# ──────────────────── Dual-Channel Mel Config ────────────────────

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
    """Compute dual-channel mel spectrogram (BirdNET-style).

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


# ──────────────────── Building Blocks ────────────────────


class SEBlock(nn.Module):
    """Squeeze-and-Excitation block for channel attention."""

    def __init__(self, channels, reduction=16):
        super().__init__()
        mid = max(channels // reduction, 8)
        self.squeeze = nn.AdaptiveAvgPool2d(1)
        self.excitation = nn.Sequential(
            nn.Linear(channels, mid, bias=False),
            nn.ReLU(inplace=True),
            nn.Linear(mid, channels, bias=False),
            nn.Sigmoid(),
        )

    def forward(self, x):
        b, c, _, _ = x.shape
        w = self.squeeze(x).view(b, c)
        w = self.excitation(w).view(b, c, 1, 1)
        return x * w


class GeM(nn.Module):
    """Generalized Mean Pooling.

    Learnable p parameter interpolates between average (p=1) and max (p→∞) pooling.
    Shown to outperform GAP in retrieval/classification tasks.
    """

    def __init__(self, p=3.0, eps=1e-6):
        super().__init__()
        self.p = nn.Parameter(torch.tensor(p))
        self.eps = eps

    def forward(self, x):
        return x.clamp(min=self.eps).pow(self.p).mean(dim=[-2, -1]).pow(1.0 / self.p)


class BottleneckBlock(nn.Module):
    """Bottleneck residual block (1x1 → 3x3 → 1x1) with SE attention."""

    expansion = 4

    def __init__(
        self, in_channels, planes, stride=1, se_reduction=16, drop_path_rate=0.0
    ):
        super().__init__()
        out_channels = planes * self.expansion

        self.conv1 = nn.Conv2d(in_channels, planes, 1, bias=False)
        self.bn1 = nn.BatchNorm2d(planes)
        self.conv2 = nn.Conv2d(planes, planes, 3, stride=stride, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(planes)
        self.conv3 = nn.Conv2d(planes, out_channels, 1, bias=False)
        self.bn3 = nn.BatchNorm2d(out_channels)
        self.se = SEBlock(out_channels, se_reduction)
        self.relu = nn.ReLU(inplace=True)

        self.shortcut = nn.Sequential()
        if stride != 1 or in_channels != out_channels:
            self.shortcut = nn.Sequential(
                nn.Conv2d(in_channels, out_channels, 1, stride=stride, bias=False),
                nn.BatchNorm2d(out_channels),
            )

        self.drop_path_rate = drop_path_rate

    def forward(self, x):
        identity = self.shortcut(x)

        out = self.relu(self.bn1(self.conv1(x)))
        out = self.relu(self.bn2(self.conv2(out)))
        out = self.bn3(self.conv3(out))
        out = self.se(out)

        if self.drop_path_rate > 0 and self.training:
            if torch.rand(1).item() < self.drop_path_rate:
                return identity

        out += identity
        out = self.relu(out)
        return out


class BasicSEBlock(nn.Module):
    """Basic residual block (3x3 → 3x3) with SE attention."""

    expansion = 1

    def __init__(
        self, in_channels, out_channels, stride=1, se_reduction=16, drop_path_rate=0.0
    ):
        super().__init__()
        self.conv1 = nn.Conv2d(
            in_channels, out_channels, 3, stride=stride, padding=1, bias=False
        )
        self.bn1 = nn.BatchNorm2d(out_channels)
        self.conv2 = nn.Conv2d(out_channels, out_channels, 3, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(out_channels)
        self.se = SEBlock(out_channels, se_reduction)
        self.relu = nn.ReLU(inplace=True)

        self.shortcut = nn.Sequential()
        if stride != 1 or in_channels != out_channels:
            self.shortcut = nn.Sequential(
                nn.Conv2d(in_channels, out_channels, 1, stride=stride, bias=False),
                nn.BatchNorm2d(out_channels),
            )

        self.drop_path_rate = drop_path_rate

    def forward(self, x):
        identity = self.shortcut(x)

        out = self.relu(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        out = self.se(out)

        if self.drop_path_rate > 0 and self.training:
            if torch.rand(1).item() < self.drop_path_rate:
                return identity

        out += identity
        out = self.relu(out)
        return out


# ──────────────────── Teacher: SE-ResNet-50 V6 ────────────────────


class SEResNet50V6(nn.Module):
    """SE-ResNet-50 teacher with dual-channel input and GeM pooling.

    Architecture: [3, 4, 6, 3] bottleneck blocks.
    Input: (B, 2, 96, 512) dual-channel mel spectrogram.
    ~26M params.
    """

    def __init__(
        self,
        num_species=200,
        in_channels=2,
        drop_path_rate=0.1,
        gradient_checkpointing=False,
    ):
        super().__init__()
        self.num_species = num_species
        self.in_ch = 64

        # Stem: adapted for dual-channel mel input
        self.conv1 = nn.Conv2d(
            in_channels, 64, kernel_size=7, stride=2, padding=3, bias=False
        )
        self.bn1 = nn.BatchNorm2d(64)
        self.relu = nn.ReLU(inplace=True)
        self.maxpool = nn.MaxPool2d(kernel_size=3, stride=2, padding=1)

        block_counts = [3, 4, 6, 3]
        total_blocks = sum(block_counts)
        dpr = np.linspace(0, drop_path_rate, total_blocks).tolist()

        idx = 0
        self.layer1 = self._make_layer(
            64, block_counts[0], stride=1, drop_rates=dpr[idx : idx + block_counts[0]]
        )
        idx += block_counts[0]
        self.layer2 = self._make_layer(
            128, block_counts[1], stride=2, drop_rates=dpr[idx : idx + block_counts[1]]
        )
        idx += block_counts[1]
        self.layer3 = self._make_layer(
            256, block_counts[2], stride=2, drop_rates=dpr[idx : idx + block_counts[2]]
        )
        idx += block_counts[2]
        self.layer4 = self._make_layer(
            512, block_counts[3], stride=2, drop_rates=dpr[idx : idx + block_counts[3]]
        )

        # Head: GeM pooling → dropout → FC
        self.pool = GeM(p=3.0)
        self.dropout = nn.Dropout(0.3)
        self.fc = nn.Linear(512 * BottleneckBlock.expansion, num_species)
        self.gradient_checkpointing = gradient_checkpointing

        self._init_weights()

    def _make_layer(self, planes, num_blocks, stride, drop_rates):
        layers = []
        layers.append(
            BottleneckBlock(
                self.in_ch, planes, stride=stride, drop_path_rate=drop_rates[0]
            )
        )
        self.in_ch = planes * BottleneckBlock.expansion
        for i in range(1, num_blocks):
            layers.append(
                BottleneckBlock(self.in_ch, planes, drop_path_rate=drop_rates[i])
            )
        return nn.Sequential(*layers)

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)
            elif isinstance(m, nn.Linear):
                nn.init.normal_(m.weight, 0, 0.01)
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)

    def _run_layer(self, layer, x):
        if self.gradient_checkpointing and self.training:
            return torch.utils.checkpoint.checkpoint(layer, x, use_reentrant=False)
        return layer(x)

    def forward(self, x):
        x = self.relu(self.bn1(self.conv1(x)))
        x = self.maxpool(x)
        x = self.layer1(x)
        x = self._run_layer(self.layer2, x)
        x = self._run_layer(self.layer3, x)
        x = self._run_layer(self.layer4, x)
        feat = self.pool(x)
        x = self.dropout(feat)
        x = self.fc(x)
        return x

    def extract_features(self, x):
        x = self.relu(self.bn1(self.conv1(x)))
        x = self.maxpool(x)
        x = self.layer1(x)
        x = self._run_layer(self.layer2, x)
        x = self._run_layer(self.layer3, x)
        x = self._run_layer(self.layer4, x)
        return self.pool(x)


# ──────────────────── Student: SE-ResNet-18 V6 ────────────────────


class SEResNet18V6(nn.Module):
    """SE-ResNet-18 student with dual-channel input and GeM pooling.

    Architecture: [2, 2, 2, 2] basic blocks.
    Input: (B, 2, 96, 512) dual-channel mel spectrogram.
    ~11.4M params.
    """

    def __init__(
        self,
        num_species=200,
        in_channels=2,
        drop_path_rate=0.05,
        gradient_checkpointing=False,
    ):
        super().__init__()
        self.num_species = num_species
        self.in_ch = 64
        self.gradient_checkpointing = gradient_checkpointing

        self.conv1 = nn.Conv2d(
            in_channels, 64, kernel_size=7, stride=2, padding=3, bias=False
        )
        self.bn1 = nn.BatchNorm2d(64)
        self.relu = nn.ReLU(inplace=True)
        self.maxpool = nn.MaxPool2d(kernel_size=3, stride=2, padding=1)

        block_counts = [2, 2, 2, 2]
        total_blocks = sum(block_counts)
        dpr = np.linspace(0, drop_path_rate, total_blocks).tolist()

        idx = 0
        self.layer1 = self._make_layer(
            64, block_counts[0], stride=1, drop_rates=dpr[idx : idx + block_counts[0]]
        )
        idx += block_counts[0]
        self.layer2 = self._make_layer(
            128, block_counts[1], stride=2, drop_rates=dpr[idx : idx + block_counts[1]]
        )
        idx += block_counts[1]
        self.layer3 = self._make_layer(
            256, block_counts[2], stride=2, drop_rates=dpr[idx : idx + block_counts[2]]
        )
        idx += block_counts[2]
        self.layer4 = self._make_layer(
            512, block_counts[3], stride=2, drop_rates=dpr[idx : idx + block_counts[3]]
        )

        self.pool = GeM(p=3.0)
        self.dropout = nn.Dropout(0.5)
        self.fc = nn.Linear(512, num_species)

        self._init_weights()

    def _make_layer(self, out_channels, num_blocks, stride, drop_rates):
        layers = []
        layers.append(
            BasicSEBlock(
                self.in_ch, out_channels, stride=stride, drop_path_rate=drop_rates[0]
            )
        )
        self.in_ch = out_channels
        for i in range(1, num_blocks):
            layers.append(
                BasicSEBlock(self.in_ch, out_channels, drop_path_rate=drop_rates[i])
            )
        return nn.Sequential(*layers)

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)

    def _run_layer(self, layer, x):
        if self.gradient_checkpointing and self.training:
            return torch.utils.checkpoint.checkpoint(layer, x, use_reentrant=False)
        return layer(x)

    def forward(self, x):
        x = self.relu(self.bn1(self.conv1(x)))
        x = self.maxpool(x)
        x = self.layer1(x)
        x = self._run_layer(self.layer2, x)
        x = self._run_layer(self.layer3, x)
        x = self._run_layer(self.layer4, x)
        feat = self.pool(x)
        x = self.dropout(feat)
        x = self.fc(x)
        return x

    def extract_features(self, x):
        x = self.relu(self.bn1(self.conv1(x)))
        x = self.maxpool(x)
        x = self.layer1(x)
        x = self._run_layer(self.layer2, x)
        x = self._run_layer(self.layer3, x)
        x = self._run_layer(self.layer4, x)
        return self.pool(x)


# ──────────────────── Knowledge Distillation Loss ────────────────────


class DistillationLoss(nn.Module):
    """L = α * T² * KL(student_soft || teacher_soft) + (1 - α) * hard_loss"""

    def __init__(self, temperature=4.0, alpha=0.7, hard_loss_fn=None):
        super().__init__()
        self.T = temperature
        self.alpha = alpha
        self.hard_loss_fn = hard_loss_fn or nn.CrossEntropyLoss()

    def forward(self, student_logits, teacher_logits, targets):
        soft_loss = F.kl_div(
            F.log_softmax(student_logits / self.T, dim=1),
            F.softmax(teacher_logits / self.T, dim=1),
            reduction="batchmean",
        ) * (self.T**2)

        hard_loss = self.hard_loss_fn(student_logits, targets)

        return self.alpha * soft_loss + (1 - self.alpha) * hard_loss


# ──────────────────── CutMix / Mixup ────────────────────


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


# ──────────────────── Factory ────────────────────


def create_model_v6(num_species=200, model_type="teacher", in_channels=2):
    if model_type == "teacher":
        return SEResNet50V6(num_species=num_species, in_channels=in_channels)
    elif model_type == "student":
        return SEResNet18V6(num_species=num_species, in_channels=in_channels)
    else:
        raise ValueError(f"Unknown model_type: {model_type}")


def count_parameters(model):
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


if __name__ == "__main__":
    x = torch.randn(4, 2, 96, 512)

    teacher = create_model_v6(num_species=223, model_type="teacher")
    print(f"SE-ResNet-50 V6 (Teacher): {count_parameters(teacher):,} params")
    out_t = teacher(x)
    print(f"  Input: {x.shape} -> Output: {out_t.shape}")

    student = create_model_v6(num_species=223, model_type="student")
    print(f"SE-ResNet-18 V6 (Student): {count_parameters(student):,} params")
    out_s = student(x)
    print(f"  Input: {x.shape} -> Output: {out_s.shape}")

    kd_loss = DistillationLoss(temperature=4.0, alpha=0.7)
    targets = torch.randint(0, 223, (4,))
    loss = kd_loss(out_s, out_t.detach(), targets)
    print(f"  Distillation loss: {loss.item():.4f}")
