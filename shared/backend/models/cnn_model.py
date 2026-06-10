"""
CNN Bird Sound Classification Model
Based on ResNet architecture adapted for mel-spectrogram input.
Addresses Sugai et al. (2026) recommendation: use CNN-based species detection
instead of acoustic indices for biodiversity research.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class ResidualBlock(nn.Module):
    """Standard residual block with two conv layers and skip connection."""

    def __init__(self, in_channels, out_channels, stride=1):
        super().__init__()
        self.conv1 = nn.Conv2d(
            in_channels, out_channels, 3, stride=stride, padding=1, bias=False
        )
        self.bn1 = nn.BatchNorm2d(out_channels)
        self.conv2 = nn.Conv2d(
            out_channels, out_channels, 3, stride=1, padding=1, bias=False
        )
        self.bn2 = nn.BatchNorm2d(out_channels)

        self.shortcut = nn.Sequential()
        if stride != 1 or in_channels != out_channels:
            self.shortcut = nn.Sequential(
                nn.Conv2d(in_channels, out_channels, 1, stride=stride, bias=False),
                nn.BatchNorm2d(out_channels),
            )

    def forward(self, x):
        out = F.relu(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        out += self.shortcut(x)
        out = F.relu(out)
        return out


class BirdSoundCNN(nn.Module):
    """
    ResNet-based CNN for bird sound classification from mel-spectrograms.

    Architecture:
    - Input: 1-channel mel-spectrogram (1 x n_mels x time_frames)
    - 4 residual stages with increasing channels: 64 -> 128 -> 256 -> 512
    - Global average pooling -> FC -> num_species classes

    This follows the approach validated in BirdNET (Kahl et al.) and
    multiple BirdCLEF competitions using mel-spectrogram + CNN pipelines.
    """

    def __init__(self, num_species=200, n_mels=128):
        super().__init__()
        self.num_species = num_species

        # Initial convolution
        self.conv1 = nn.Conv2d(1, 64, kernel_size=7, stride=2, padding=3, bias=False)
        self.bn1 = nn.BatchNorm2d(64)
        self.maxpool = nn.MaxPool2d(kernel_size=3, stride=2, padding=1)

        # Residual stages
        self.layer1 = self._make_layer(64, 64, num_blocks=2, stride=1)
        self.layer2 = self._make_layer(64, 128, num_blocks=2, stride=2)
        self.layer3 = self._make_layer(128, 256, num_blocks=2, stride=2)
        self.layer4 = self._make_layer(256, 512, num_blocks=2, stride=2)

        # Classification head
        self.avgpool = nn.AdaptiveAvgPool2d((1, 1))
        self.dropout = nn.Dropout(0.5)
        self.fc = nn.Linear(512, num_species)

    def _make_layer(self, in_channels, out_channels, num_blocks, stride):
        layers = [ResidualBlock(in_channels, out_channels, stride)]
        for _ in range(1, num_blocks):
            layers.append(ResidualBlock(out_channels, out_channels, 1))
        return nn.Sequential(*layers)

    def forward(self, x):
        # x shape: (batch, 1, n_mels, time_frames)
        x = F.relu(self.bn1(self.conv1(x)))
        x = self.maxpool(x)

        x = self.layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)
        x = self.layer4(x)

        x = self.avgpool(x)
        x = torch.flatten(x, 1)
        x = self.dropout(x)
        x = self.fc(x)
        return x

    def extract_features(self, x):
        """Extract 512-dim feature embeddings (before classification head)."""
        x = F.relu(self.bn1(self.conv1(x)))
        x = self.maxpool(x)
        x = self.layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)
        x = self.layer4(x)
        x = self.avgpool(x)
        x = torch.flatten(x, 1)
        return x


class BirdSoundCNNLite(nn.Module):
    """
    Lightweight CNN for faster inference on edge devices.
    Uses depthwise separable convolutions (MobileNet-style).
    """

    def __init__(self, num_species=200):
        super().__init__()

        def _dsconv(in_c, out_c, stride=1):
            return nn.Sequential(
                nn.Conv2d(
                    in_c, in_c, 3, stride=stride, padding=1, groups=in_c, bias=False
                ),
                nn.BatchNorm2d(in_c),
                nn.ReLU(inplace=True),
                nn.Conv2d(in_c, out_c, 1, bias=False),
                nn.BatchNorm2d(out_c),
                nn.ReLU(inplace=True),
            )

        self.features = nn.Sequential(
            nn.Conv2d(1, 32, 3, stride=2, padding=1, bias=False),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            _dsconv(32, 64),
            _dsconv(64, 128, stride=2),
            _dsconv(128, 128),
            _dsconv(128, 256, stride=2),
            _dsconv(256, 256),
            _dsconv(256, 512, stride=2),
            _dsconv(512, 512),
        )
        self.avgpool = nn.AdaptiveAvgPool2d((1, 1))
        self.dropout = nn.Dropout(0.3)
        self.fc = nn.Linear(512, num_species)

    def forward(self, x):
        x = self.features(x)
        x = self.avgpool(x)
        x = torch.flatten(x, 1)
        x = self.dropout(x)
        x = self.fc(x)
        return x


def create_model(num_species=200, lite=False):
    """Factory function to create bird sound CNN model."""
    if lite:
        return BirdSoundCNNLite(num_species=num_species)
    return BirdSoundCNN(num_species=num_species)


def count_parameters(model):
    """Count trainable parameters."""
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


if __name__ == "__main__":
    model = create_model(num_species=200)
    print(f"BirdSoundCNN parameters: {count_parameters(model):,}")
    x = torch.randn(2, 1, 128, 256)
    out = model(x)
    print(f"Input shape: {x.shape} -> Output shape: {out.shape}")

    model_lite = create_model(num_species=200, lite=True)
    print(f"BirdSoundCNNLite parameters: {count_parameters(model_lite):,}")
    out_lite = model_lite(x)
    print(f"Input shape: {x.shape} -> Output shape (lite): {out_lite.shape}")
