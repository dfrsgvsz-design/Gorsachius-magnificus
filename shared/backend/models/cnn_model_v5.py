"""
CNN Model V5 — EfficientNet + Dual-Channel Spectrogram + Prototype Learning

Architecture inspired by:
- BirdNET v2.4: Dual-channel mel spectrogram (low+high freq), EfficientNet-B0 backbone
- Perch 2.0: EfficientNet-B3 backbone, prototype learning, self-distillation
- Our innovation: Combine both with anti-hallucination prototype OOD detection

Key design choices:
1. EfficientNet-B1 backbone (pretrained ImageNet → transfer to spectrograms)
   - 7.8M params, much more efficient than SE-ResNet-50 (25M)
   - Depthwise separable convolutions + SE attention built-in
2. Dual-channel spectrogram input (BirdNET style):
   - Channel 1: 0-3kHz low-frequency (bass calls, drums)
   - Channel 2: 500Hz-15kHz high-frequency (songs, chirps)
3. Prototype learning head for OOD detection
4. Non-event class support (background noise rejection)

Target: RTX 3080 10GB — batch_size ~48 with dual-channel input
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import timm

# ──────────────────── Dual-Channel Spectrogram Config ────────────────────
DUAL_CHANNEL_CONFIG = {
    "sr": 48000,  # BirdNET uses 48kHz
    "segment_duration": 3.0,  # 3-second segments (BirdNET standard)
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


TARGET_FRAMES = 512  # Fixed time dimension for consistent batching


def compute_dual_channel_mel(y, sr=48000, config=None, target_frames=TARGET_FRAMES):
    """Compute dual-channel mel spectrogram (BirdNET-style).

    Returns shape: (2, n_mels, target_frames) normalized to [0, 1].
    Output is always padded/cropped to target_frames for consistent batching.
    """
    import librosa

    if config is None:
        config = DUAL_CHANNEL_CONFIG

    # Resample if needed
    if sr != config["sr"]:
        y = librosa.resample(y, orig_sr=sr, target_sr=config["sr"])
        sr = config["sr"]

    # Normalize audio to [-1, 1] (BirdNET convention)
    peak = np.abs(y).max()
    if peak > 0:
        y = y / peak

    n_mels = config["channel_low"]["n_mels"]  # 96
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
        # Non-linear magnitude scaling (Schlüter 2018, used by BirdNET)
        S = np.log1p(S * 10)
        # Normalize per-channel
        s_min, s_max = S.min(), S.max()
        if s_max - s_min > 1e-6:
            S = (S - s_min) / (s_max - s_min)
        else:
            S = np.zeros_like(S)

        # Fix to target_frames: pad or crop
        if S.shape[1] > target_frames:
            S = S[:, :target_frames]
        elif S.shape[1] < target_frames:
            pad = np.zeros((n_mels, target_frames - S.shape[1]), dtype=S.dtype)
            S = np.concatenate([S, pad], axis=1)
        channels.append(S)

    return np.stack(channels, axis=0).astype(np.float32)  # (2, 96, target_frames)


# ──────────────────── Prototype Learning Head ────────────────────
class PrototypeLearningHead(nn.Module):
    """Prototype-based classification head (inspired by Perch 2.0).

    Learns K prototypes per class in embedding space.
    Enables OOD detection via prototype distance.
    """

    def __init__(self, embed_dim, num_classes, num_prototypes=4):
        super().__init__()
        self.num_classes = num_classes
        self.num_prototypes = num_prototypes
        self.embed_dim = embed_dim

        # Prototypes: (num_classes * num_prototypes, embed_dim)
        self.prototypes = nn.Parameter(
            torch.randn(num_classes * num_prototypes, embed_dim) * 0.02
        )
        # Temperature for prototype similarity
        self.proto_temp = nn.Parameter(torch.tensor(0.1))

    def forward(self, embeddings):
        """
        Args:
            embeddings: (B, D) global embeddings
        Returns:
            logits: (B, num_classes) max prototype similarity per class
            distances: (B, num_classes) min distance to prototypes per class
        """
        # Normalize
        emb_norm = F.normalize(embeddings, dim=1)
        proto_norm = F.normalize(self.prototypes, dim=1)

        # Cosine similarity: (B, num_classes * num_prototypes)
        sim = torch.mm(emb_norm, proto_norm.t()) / self.proto_temp.abs().clamp(min=0.01)

        # Reshape to (B, num_classes, num_prototypes)
        sim = sim.view(-1, self.num_classes, self.num_prototypes)

        # Max similarity per class → logits
        logits, _ = sim.max(dim=2)  # (B, num_classes)

        # Euclidean distance for OOD detection
        # (B, 1, D) - (num_classes*K, D) → (B, num_classes*K)
        dists = torch.cdist(
            embeddings.unsqueeze(1), self.prototypes.unsqueeze(0)
        ).squeeze(1)
        dists = dists.view(-1, self.num_classes, self.num_prototypes)
        min_dists, _ = dists.min(dim=2)  # (B, num_classes)

        return logits, min_dists

    def orthogonal_loss(self):
        """Encourage prototype diversity within each class."""
        proto = F.normalize(self.prototypes, dim=1)
        proto = proto.view(self.num_classes, self.num_prototypes, self.embed_dim)
        # Pairwise cosine similarity within each class
        sim = torch.bmm(proto, proto.transpose(1, 2))  # (C, K, K)
        # Mask diagonal
        eye = torch.eye(self.num_prototypes, device=sim.device).unsqueeze(0)
        off_diag = sim * (1 - eye)
        return off_diag.abs().mean()


# ──────────────────── EfficientNet Bird Classifier ────────────────────
class EfficientNetBird(nn.Module):
    """EfficientNet-B1 based bird sound classifier with dual-channel input.

    Architecture:
    - Input: (B, 2, 96, T) dual-channel mel spectrogram
    - Stem conv adapts 2→3 channels for pretrained EfficientNet
    - EfficientNet-B1 backbone → 1280-dim embedding
    - Two output heads:
      1. Linear classifier (standard cross-entropy)
      2. Prototype learning (OOD detection + self-distillation)

    Params: ~8.5M (vs SE-ResNet-50 25M, SE-ResNet-18 11.5M)
    """

    def __init__(
        self,
        num_classes=217,
        dropout=0.3,
        pretrained=True,
        num_prototypes=4,
        backbone="efficientnet_b1",
        drop_path_rate=0.2,
    ):
        super().__init__()
        self.num_classes = num_classes

        # Channel adapter: 2-channel mel → 3-channel (for pretrained weights)
        self.channel_adapt = nn.Sequential(
            nn.Conv2d(2, 3, kernel_size=1, bias=False),
            nn.BatchNorm2d(3),
        )

        # EfficientNet backbone (pretrained on ImageNet)
        self.backbone = timm.create_model(
            backbone,
            pretrained=pretrained,
            num_classes=0,  # Remove classification head
            global_pool="avg",
            drop_rate=dropout,
            drop_path_rate=drop_path_rate,  # Stochastic depth for regularization
        )
        embed_dim = self.backbone.num_features  # 1280 for B1

        # Linear classification head
        self.head_dropout = nn.Dropout(dropout)
        self.head_linear = nn.Linear(embed_dim, num_classes)

        # Prototype learning head
        self.head_proto = PrototypeLearningHead(
            embed_dim, num_classes, num_prototypes=num_prototypes
        )

        self._embed_dim = embed_dim

    @property
    def embed_dim(self):
        return self._embed_dim

    def forward(self, x, return_embedding=False, return_proto=False):
        """
        Args:
            x: (B, 2, H, W) dual-channel mel spectrogram
            return_embedding: if True, also return embeddings
            return_proto: if True, also return prototype logits + distances
        Returns:
            logits: (B, num_classes)
            [optional] embedding: (B, embed_dim)
            [optional] (proto_logits, proto_dists): prototype outputs
        """
        # Adapt 2 channels → 3 for pretrained backbone
        x = self.channel_adapt(x)

        # Extract embedding
        embedding = self.backbone(x)  # (B, embed_dim)

        # Linear head
        logits = self.head_linear(self.head_dropout(embedding))

        outputs = [logits]
        if return_embedding:
            outputs.append(embedding)
        if return_proto:
            proto_logits, proto_dists = self.head_proto(embedding)
            outputs.append((proto_logits, proto_dists))

        return outputs[0] if len(outputs) == 1 else tuple(outputs)

    def extract_features(self, x):
        """Extract embedding features only."""
        x = self.channel_adapt(x)
        return self.backbone(x)


# ──────────────────── Larger variant for teacher ────────────────────
class EfficientNetBirdLarge(EfficientNetBird):
    """EfficientNet-B3 teacher model (~12M params)."""

    def __init__(
        self,
        num_classes=217,
        dropout=0.3,
        pretrained=True,
        num_prototypes=4,
        drop_path_rate=0.3,
    ):
        super().__init__(
            num_classes=num_classes,
            dropout=dropout,
            pretrained=pretrained,
            num_prototypes=num_prototypes,
            backbone="efficientnet_b3",
            drop_path_rate=drop_path_rate,
        )


# ──────────────────── Utility ────────────────────
def count_parameters(model):
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def self_distillation_loss(linear_logits, proto_logits, temperature=3.0):
    """Self-distillation: prototype head teaches linear head (Perch 2.0 style).

    Gradient does NOT flow back to prototype head (it's the teacher).
    """
    with torch.no_grad():
        teacher_probs = F.softmax(proto_logits.detach() / temperature, dim=1)
    student_log_probs = F.log_softmax(linear_logits / temperature, dim=1)
    return F.kl_div(student_log_probs, teacher_probs, reduction="batchmean") * (
        temperature**2
    )


if __name__ == "__main__":
    # Quick test
    model = EfficientNetBird(num_classes=217, pretrained=False)
    print(f"EfficientNet-B1 Bird: {count_parameters(model):,} params")
    print(f"Embedding dim: {model.embed_dim}")

    x = torch.randn(4, 2, 96, 512)
    logits, emb, (proto_logits, proto_dists) = model(
        x, return_embedding=True, return_proto=True
    )
    print(f"Input:  {x.shape}")
    print(f"Logits: {logits.shape}")
    print(f"Embed:  {emb.shape}")
    print(f"Proto:  {proto_logits.shape}, Dists: {proto_dists.shape}")

    teacher = EfficientNetBirdLarge(num_classes=217, pretrained=False)
    print(f"\nEfficientNet-B3 Teacher: {count_parameters(teacher):,} params")
