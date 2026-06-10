"""CNN model architectures for bird sound classification."""

from .cnn_model import BirdSoundCNN, BirdSoundCNNLite, create_model
from .cnn_model_v2 import SEResNet50, SEResNet18, create_model_v2, DistillationLoss
from .cnn_model_v5 import EfficientNetBird, EfficientNetBirdLarge, compute_dual_channel_mel as compute_dual_channel_mel_v5
from .cnn_model_v6 import SEResNet50V6, SEResNet18V6, create_model_v6
from .cnn_model_v7 import ConvNeXtBirdV7, ConvNeXtBirdV7Student, create_model_v7
from .train import BirdSoundDataset, train_model, build_species_mapping
