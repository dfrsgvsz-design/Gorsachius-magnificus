"""
Enhanced CNN architectures for bird sound classification.

V2 Models:
- SE (Squeeze-and-Excitation) attention blocks for channel recalibration
- Bottleneck residual blocks (ResNet-50 style) for deeper feature extraction
- Stochastic Depth for training regularization
- Teacher (SE-ResNet-50) and Student (SE-ResNet-18) for knowledge distillation

References:
- Hu et al. (2018) "Squeeze-and-Excitation Networks" CVPR
- Huang et al. (2016) "Deep Networks with Stochastic Depth"
- Hinton et al. (2015) "Distilling the Knowledge in a Neural Network"
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np

# ──────────────────── Building Blocks ────────────────────


class SEBlock(nn.Module):
    """Squeeze-and-Excitation block for channel attention.

    Learns per-channel importance weights via global pooling → FC → sigmoid.
    Computational overhead is negligible (~0.5% params increase).
    """

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


class BottleneckBlock(nn.Module):
    """Bottleneck residual block (1x1 → 3x3 → 1x1) with SE attention.

    Expansion factor = 4: output channels = planes * 4.
    More parameter-efficient than basic blocks for deeper networks.
    """

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

        # Stochastic depth: randomly drop entire block during training
        if self.drop_path_rate > 0 and self.training:
            if torch.rand(1).item() < self.drop_path_rate:
                return identity

        out += identity
        out = self.relu(out)
        return out


class BasicSEBlock(nn.Module):
    """Basic residual block (3x3 → 3x3) with SE attention.

    For the student model (SE-ResNet-18).
    """

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


# ──────────────────── Teacher: SE-ResNet-50 ────────────────────


class SEResNet50(nn.Module):
    """SE-ResNet-50: Deep teacher model for knowledge distillation.

    Architecture: [3, 4, 6, 3] bottleneck blocks with SE attention.
    ~25M params — designed to fully utilize RTX 3080 10GB VRAM.

    Feature pyramid channels: 256 → 512 → 1024 → 2048
    """

    def __init__(self, num_species=200, drop_path_rate=0.1):
        super().__init__()
        self.num_species = num_species
        self.in_channels = 64

        # Stem
        self.conv1 = nn.Conv2d(1, 64, kernel_size=7, stride=2, padding=3, bias=False)
        self.bn1 = nn.BatchNorm2d(64)
        self.relu = nn.ReLU(inplace=True)
        self.maxpool = nn.MaxPool2d(kernel_size=3, stride=2, padding=1)

        # Stochastic depth: linearly increase drop rate
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

        # Head
        self.avgpool = nn.AdaptiveAvgPool2d((1, 1))
        self.dropout = nn.Dropout(0.3)
        self.fc = nn.Linear(512 * BottleneckBlock.expansion, num_species)

        self._init_weights()

    def _make_layer(self, planes, num_blocks, stride, drop_rates):
        layers = []
        layers.append(
            BottleneckBlock(
                self.in_channels, planes, stride=stride, drop_path_rate=drop_rates[0]
            )
        )
        self.in_channels = planes * BottleneckBlock.expansion
        for i in range(1, num_blocks):
            layers.append(
                BottleneckBlock(self.in_channels, planes, drop_path_rate=drop_rates[i])
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

    def forward(self, x):
        x = self.relu(self.bn1(self.conv1(x)))
        x = self.maxpool(x)
        x = self.layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)
        x = self.layer4(x)
        x = self.avgpool(x)
        feat = torch.flatten(x, 1)
        x = self.dropout(feat)
        x = self.fc(x)
        return x

    def extract_features(self, x):
        x = self.relu(self.bn1(self.conv1(x)))
        x = self.maxpool(x)
        x = self.layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)
        x = self.layer4(x)
        x = self.avgpool(x)
        return torch.flatten(x, 1)


# ──────────────────── Student: SE-ResNet-18 ────────────────────


class SEResNet18(nn.Module):
    """SE-ResNet-18: Compact student model with attention.

    Architecture: [2, 2, 2, 2] basic blocks with SE attention.
    ~11.5M params — fast inference with attention-enhanced features.
    """

    def __init__(self, num_species=200, drop_path_rate=0.05):
        super().__init__()
        self.num_species = num_species
        self.in_channels = 64

        self.conv1 = nn.Conv2d(1, 64, kernel_size=7, stride=2, padding=3, bias=False)
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

        self.avgpool = nn.AdaptiveAvgPool2d((1, 1))
        self.dropout = nn.Dropout(0.5)
        self.fc = nn.Linear(512, num_species)

        self._init_weights()

    def _make_layer(self, out_channels, num_blocks, stride, drop_rates):
        layers = []
        layers.append(
            BasicSEBlock(
                self.in_channels,
                out_channels,
                stride=stride,
                drop_path_rate=drop_rates[0],
            )
        )
        self.in_channels = out_channels
        for i in range(1, num_blocks):
            layers.append(
                BasicSEBlock(
                    self.in_channels, out_channels, drop_path_rate=drop_rates[i]
                )
            )
        return nn.Sequential(*layers)

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)

    def forward(self, x):
        x = self.relu(self.bn1(self.conv1(x)))
        x = self.maxpool(x)
        x = self.layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)
        x = self.layer4(x)
        x = self.avgpool(x)
        feat = torch.flatten(x, 1)
        x = self.dropout(feat)
        x = self.fc(x)
        return x

    def extract_features(self, x):
        x = self.relu(self.bn1(self.conv1(x)))
        x = self.maxpool(x)
        x = self.layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)
        x = self.layer4(x)
        x = self.avgpool(x)
        return torch.flatten(x, 1)


# ──────────────────── Knowledge Distillation Loss ────────────────────


class DistillationLoss(nn.Module):
    """Combined loss for knowledge distillation.

    L = α * T² * KL(student_soft || teacher_soft) + (1 - α) * hard_loss

    - T (temperature): softens probability distributions
    - α: balance between soft (teacher) and hard (ground truth) targets
    - Higher T → softer distributions → more "dark knowledge" transfer
    """

    def __init__(self, temperature=4.0, alpha=0.7, hard_loss_fn=None):
        super().__init__()
        self.T = temperature
        self.alpha = alpha
        self.hard_loss_fn = hard_loss_fn or nn.CrossEntropyLoss()

    def forward(self, student_logits, teacher_logits, targets):
        # Soft targets from teacher
        soft_loss = F.kl_div(
            F.log_softmax(student_logits / self.T, dim=1),
            F.softmax(teacher_logits / self.T, dim=1),
            reduction="batchmean",
        ) * (self.T**2)

        # Hard targets (ground truth)
        hard_loss = self.hard_loss_fn(student_logits, targets)

        return self.alpha * soft_loss + (1 - self.alpha) * hard_loss


# ──────────────────── CutMix Augmentation ────────────────────


def cutmix_data(x, y, alpha=1.0):
    """CutMix: replace random rectangular region with another sample's content.

    More informative than Mixup for localized features (bird calls in spectrogram).
    """
    if alpha <= 0:
        return x, y, y, 1.0

    lam = np.random.beta(alpha, alpha)
    batch_size = x.size(0)
    index = torch.randperm(batch_size, device=x.device)

    # Random bounding box
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

    # Adjust lambda based on actual area
    lam = 1 - (y2 - y1) * (x2 - x1) / (H * W)

    return x_mixed, y[index], y, lam


# ──────────────────── Factory ────────────────────


def create_model_v2(num_species=200, model_type="teacher"):
    """Factory function for v2 models.

    Args:
        model_type: 'teacher' (SE-ResNet-50) or 'student' (SE-ResNet-18)
    """
    if model_type == "teacher":
        return SEResNet50(num_species=num_species)
    elif model_type == "student":
        return SEResNet18(num_species=num_species)
    else:
        raise ValueError(f"Unknown model_type: {model_type}")


def count_parameters(model):
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


if __name__ == "__main__":
    x = torch.randn(2, 1, 128, 256)

    teacher = create_model_v2(num_species=217, model_type="teacher")
    print(f"SE-ResNet-50 (Teacher): {count_parameters(teacher):,} params")
    out_t = teacher(x)
    print(f"  Input: {x.shape} -> Output: {out_t.shape}")

    student = create_model_v2(num_species=217, model_type="student")
    print(f"SE-ResNet-18 (Student): {count_parameters(student):,} params")
    out_s = student(x)
    print(f"  Input: {x.shape} -> Output: {out_s.shape}")

    # Test distillation loss
    kd_loss = DistillationLoss(temperature=4.0, alpha=0.7)
    targets = torch.randint(0, 217, (2,))
    loss = kd_loss(out_s, out_t.detach(), targets)
    print(f"  Distillation loss: {loss.item():.4f}")
