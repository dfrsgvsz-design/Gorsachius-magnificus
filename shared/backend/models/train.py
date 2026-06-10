"""
Training Pipeline for Bird Sound CNN Model.
Supports training from xeno-canto downloaded data or custom datasets.
"""

import os
import json
import numpy as np
from pathlib import Path

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader, random_split

try:
    from .cnn_model import create_model
    from ..processors.audio_processor import (
        load_audio,
        audio_to_mel_spectrogram,
        normalize_spectrogram,
        SEGMENT_DURATION,
        DEFAULT_SR,
        AudioAugmentor,
        SpectrogramAugmentor,
    )
except ImportError:
    from cnn_model import create_model
    from audio_processor import (
        load_audio,
        audio_to_mel_spectrogram,
        normalize_spectrogram,
        SEGMENT_DURATION,
        DEFAULT_SR,
        AudioAugmentor,
        SpectrogramAugmentor,
    )


class BirdSoundDataset(Dataset):
    """PyTorch dataset for bird sound mel-spectrograms."""

    def __init__(
        self,
        manifest_path,
        species_to_idx,
        segment_duration=SEGMENT_DURATION,
        sr=DEFAULT_SR,
        augment=False,
    ):
        with open(manifest_path, "r", encoding="utf-8") as f:
            self.manifest = json.load(f)
        self.species_to_idx = species_to_idx
        self.segment_duration = segment_duration
        self.sr = sr
        self.augment = augment
        self.audio_aug = AudioAugmentor()
        self.spec_aug = SpectrogramAugmentor()

    def __len__(self):
        return len(self.manifest)

    def __getitem__(self, idx):
        item = self.manifest[idx]
        file_path = item["file_path"]
        species = item["species_scientific"]
        label = self.species_to_idx.get(species, 0)

        try:
            y, sr = load_audio(
                file_path, sr=self.sr, duration=self.segment_duration + 1
            )
        except Exception:
            # Return zeros on error
            mel = np.zeros((128, int(self.segment_duration * self.sr / 512) + 1))
            return torch.FloatTensor(mel).unsqueeze(0), label

        # Random crop to segment_duration
        target_len = int(self.segment_duration * self.sr)
        if len(y) > target_len:
            start = np.random.randint(0, len(y) - target_len)
            y = y[start : start + target_len]
        elif len(y) < target_len:
            y = np.pad(y, (0, target_len - len(y)))

        # Audio augmentation
        if self.augment:
            if np.random.random() < 0.3:
                y = self.audio_aug.add_noise(y)
            if np.random.random() < 0.2:
                y = self.audio_aug.time_shift(y)
            if np.random.random() < 0.2:
                y = self.audio_aug.random_gain(y)

        # Convert to mel-spectrogram
        mel = audio_to_mel_spectrogram(y, sr=self.sr)
        mel = normalize_spectrogram(mel)

        # Spectrogram augmentation
        if self.augment:
            if np.random.random() < 0.3:
                mel = self.spec_aug.freq_mask(mel)
            if np.random.random() < 0.3:
                mel = self.spec_aug.time_mask(mel)

        # (1, n_mels, time_frames)
        tensor = torch.FloatTensor(mel).unsqueeze(0)
        return tensor, label


def build_species_mapping(manifest_path):
    """Build species name <-> index mapping from manifest."""
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    species = sorted(set(item["species_scientific"] for item in manifest))
    species_to_idx = {sp: i for i, sp in enumerate(species)}
    idx_to_species = {i: sp for sp, i in species_to_idx.items()}
    return species_to_idx, idx_to_species


def train_model(
    manifest_path,
    output_dir,
    num_epochs=50,
    batch_size=32,
    lr=0.001,
    val_split=0.2,
    lite=False,
):
    """
    Train the bird sound CNN model.

    Args:
        manifest_path: Path to dataset manifest.json
        output_dir: Directory to save model checkpoints
        num_epochs: Number of training epochs
        batch_size: Batch size
        lr: Learning rate
        val_split: Validation split ratio
        lite: Use lightweight model
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Build species mapping
    species_to_idx, idx_to_species = build_species_mapping(manifest_path)
    num_species = len(species_to_idx)
    print(f"Number of species: {num_species}")

    # Save mapping
    mapping_path = output_path / "species_mapping.json"
    with open(mapping_path, "w", encoding="utf-8") as f:
        json.dump(
            {"species_to_idx": species_to_idx, "idx_to_species": idx_to_species},
            f,
            ensure_ascii=False,
            indent=2,
        )

    # Create datasets
    full_dataset = BirdSoundDataset(manifest_path, species_to_idx, augment=True)
    val_size = int(len(full_dataset) * val_split)
    train_size = len(full_dataset) - val_size
    train_dataset, val_dataset = random_split(full_dataset, [train_size, val_size])

    train_loader = DataLoader(
        train_dataset, batch_size=batch_size, shuffle=True, num_workers=0
    )
    val_loader = DataLoader(
        val_dataset, batch_size=batch_size, shuffle=False, num_workers=0
    )

    # Create model
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = create_model(num_species=num_species, lite=lite).to(device)
    print(f"Model on device: {device}")
    print(f"Parameters: {sum(p.numel() for p in model.parameters()):,}")

    # Loss and optimizer
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=num_epochs)

    best_val_acc = 0.0
    history = {"train_loss": [], "val_loss": [], "train_acc": [], "val_acc": []}

    for epoch in range(num_epochs):
        # Training
        model.train()
        train_loss = 0.0
        train_correct = 0
        train_total = 0

        for batch_x, batch_y in train_loader:
            batch_x = batch_x.to(device)
            batch_y = batch_y.to(device)

            optimizer.zero_grad()
            outputs = model(batch_x)
            loss = criterion(outputs, batch_y)
            loss.backward()
            optimizer.step()

            train_loss += loss.item() * batch_x.size(0)
            _, predicted = outputs.max(1)
            train_total += batch_y.size(0)
            train_correct += predicted.eq(batch_y).sum().item()

        scheduler.step()

        train_loss /= train_total
        train_acc = train_correct / train_total

        # Validation
        model.eval()
        val_loss = 0.0
        val_correct = 0
        val_total = 0

        with torch.no_grad():
            for batch_x, batch_y in val_loader:
                batch_x = batch_x.to(device)
                batch_y = batch_y.to(device)
                outputs = model(batch_x)
                loss = criterion(outputs, batch_y)
                val_loss += loss.item() * batch_x.size(0)
                _, predicted = outputs.max(1)
                val_total += batch_y.size(0)
                val_correct += predicted.eq(batch_y).sum().item()

        val_loss /= max(val_total, 1)
        val_acc = val_correct / max(val_total, 1)

        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        history["train_acc"].append(train_acc)
        history["val_acc"].append(val_acc)

        print(
            f"Epoch [{epoch+1}/{num_epochs}] "
            f"Train Loss: {train_loss:.4f} Acc: {train_acc:.4f} | "
            f"Val Loss: {val_loss:.4f} Acc: {val_acc:.4f}"
        )

        # Save best model
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            torch.save(
                {
                    "epoch": epoch,
                    "model_state_dict": model.state_dict(),
                    "optimizer_state_dict": optimizer.state_dict(),
                    "val_acc": val_acc,
                    "num_species": num_species,
                    "lite": lite,
                },
                output_path / "best_model.pth",
            )
            print(f"  -> Best model saved (val_acc={val_acc:.4f})")

    # Save final model and history
    torch.save(
        {
            "epoch": num_epochs,
            "model_state_dict": model.state_dict(),
            "num_species": num_species,
            "lite": lite,
        },
        output_path / "final_model.pth",
    )

    with open(output_path / "training_history.json", "w") as f:
        json.dump(history, f, indent=2)

    print(f"\nTraining complete. Best val accuracy: {best_val_acc:.4f}")
    return history


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Train Bird Sound CNN")
    parser.add_argument(
        "--manifest", type=str, required=True, help="Path to manifest.json"
    )
    parser.add_argument(
        "--output", type=str, default="./checkpoints", help="Output directory"
    )
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--lite", action="store_true", help="Use lightweight model")
    args = parser.parse_args()
    train_model(
        args.manifest,
        args.output,
        num_epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        lite=args.lite,
    )
