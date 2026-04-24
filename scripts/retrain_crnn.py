"""
============================================================================
 CRNN FINE-TUNING SCRIPT
============================================================================
 Usage:
     python scripts/retrain_crnn.py --epochs 10 --fine-tune
     python scripts/retrain_crnn.py --epochs 50 --lr 0.0005

 Fine-tunes the existing CRNN model on the updated training dataset
 (original + feedback-generated crops). Saves the best model based
 on validation loss.
============================================================================
"""
import argparse
import os
import sys
import json
import csv
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crnn_engine import CRNN

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKPOINT_DIR = os.path.join(BASE_DIR, 'models', 'checkpoints')
DATASET_DIR = os.path.join(BASE_DIR, 'models', 'dataset')


# ── Dataset ───────────────────────────────────────────────────

class WordCropDataset(Dataset):
    """Dataset of word crop images with text labels."""

    def __init__(self, csv_path, crops_dir, char_to_idx, img_h=32, img_w=128):
        self.crops_dir = crops_dir
        self.char_to_idx = char_to_idx
        self.img_h = img_h
        self.img_w = img_w
        self.samples = []

        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                img_path = os.path.join(crops_dir, row['image_file'])
                if os.path.exists(img_path):
                    self.samples.append((row['image_file'], row['label']))

        print(f"  Loaded {len(self.samples)} samples from {os.path.basename(csv_path)}")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        fname, label = self.samples[idx]
        img = Image.open(os.path.join(self.crops_dir, fname)).convert('L')
        img = img.resize((self.img_w, self.img_h))
        img = np.array(img, dtype=np.float32) / 255.0
        img_tensor = torch.FloatTensor(img).unsqueeze(0)  # (1, H, W)

        # Encode label: map each char to index
        target = [self.char_to_idx.get(c, 0) for c in label]
        return img_tensor, torch.IntTensor(target), len(target)


def collate_fn(batch):
    """CTC-compatible collation: pad targets, stack images."""
    images, targets, lengths = zip(*batch)
    images = torch.stack(images)
    targets = torch.cat(targets)
    lengths = torch.IntTensor(list(lengths))
    return images, targets, lengths


# ── Training Loop ─────────────────────────────────────────────

def retrain(epochs=10, lr=0.0001, fine_tune=True, batch_size=32):
    print("=" * 60)
    print("  CRNN RETRAINING")
    print("=" * 60)

    # Load metadata
    meta_path = os.path.join(DATASET_DIR, 'dataset_metadata.json')
    if not os.path.exists(meta_path):
        print(f"ERROR: {meta_path} not found")
        sys.exit(1)

    with open(meta_path, 'r', encoding='utf-8') as f:
        metadata = json.load(f)

    vocab = metadata['vocab']
    char_to_idx = vocab['char_to_idx']
    num_classes = vocab['num_classes']
    img_h = metadata.get('image_height', 32)
    img_w = metadata.get('image_width', 128)

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"  Device: {device}")
    print(f"  Classes: {num_classes}")
    print(f"  Epochs: {epochs}")
    print(f"  LR: {lr}")
    print(f"  Fine-tune: {fine_tune}")

    # Load model
    model = CRNN(num_classes, lstm_hidden=256, lstm_layers=2, dropout=0.1).to(device)

    if fine_tune:
        checkpoint_path = os.path.join(CHECKPOINT_DIR, 'crnn_best.pth')
        if os.path.exists(checkpoint_path):
            model.load_state_dict(torch.load(checkpoint_path, map_location=device))
            print(f"  Loaded existing model for fine-tuning")
        else:
            print(f"  WARNING: {checkpoint_path} not found, training from scratch")

    # Datasets
    crops_dir = os.path.join(DATASET_DIR, 'word_crops')
    train_csv = os.path.join(DATASET_DIR, 'train.csv')
    val_csv = os.path.join(DATASET_DIR, 'val.csv')

    if not os.path.exists(train_csv):
        print(f"ERROR: {train_csv} not found")
        sys.exit(1)

    train_ds = WordCropDataset(train_csv, crops_dir, char_to_idx, img_h, img_w)
    val_ds = WordCropDataset(val_csv, crops_dir, char_to_idx, img_h, img_w) if os.path.exists(val_csv) else None

    if len(train_ds) == 0:
        print("ERROR: No training samples found (check word_crops directory)")
        sys.exit(1)

    train_loader = DataLoader(
        train_ds, batch_size=batch_size, shuffle=True,
        collate_fn=collate_fn, num_workers=0
    )
    val_loader = None
    if val_ds and len(val_ds) > 0:
        val_loader = DataLoader(
            val_ds, batch_size=batch_size, shuffle=False,
            collate_fn=collate_fn, num_workers=0
        )

    # Training setup
    criterion = nn.CTCLoss(blank=0, zero_infinity=True)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode='min', factor=0.5, patience=3, verbose=True
    )

    best_val_loss = float('inf')
    print(f"\n  Training on {len(train_ds)} samples...")
    print("-" * 60)

    for epoch in range(epochs):
        # ── Train ──
        model.train()
        total_loss = 0
        batch_count = 0

        for images, targets, lengths in train_loader:
            images = images.to(device)

            log_probs = model(images)  # (T, N, C)
            T, N = log_probs.shape[0], log_probs.shape[1]
            input_lengths = torch.full((N,), T, dtype=torch.long)

            loss = criterion(log_probs, targets, input_lengths, lengths)

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()

            total_loss += loss.item()
            batch_count += 1

        avg_train_loss = total_loss / max(batch_count, 1)

        # ── Validate ──
        avg_val_loss = None
        if val_loader:
            model.eval()
            val_loss = 0
            val_batches = 0
            with torch.no_grad():
                for images, targets, lengths in val_loader:
                    images = images.to(device)
                    log_probs = model(images)
                    T, N = log_probs.shape[0], log_probs.shape[1]
                    input_lengths = torch.full((N,), T, dtype=torch.long)
                    loss = criterion(log_probs, targets, input_lengths, lengths)
                    val_loss += loss.item()
                    val_batches += 1

            avg_val_loss = val_loss / max(val_batches, 1)
            scheduler.step(avg_val_loss)

            val_str = f"Val: {avg_val_loss:.4f}"

            # Save best
            if avg_val_loss < best_val_loss:
                best_val_loss = avg_val_loss
                save_path = os.path.join(CHECKPOINT_DIR, 'crnn_best.pth')
                torch.save(model.state_dict(), save_path)
                val_str += " ★ BEST"
        else:
            val_str = "Val: N/A"
            # Without validation, save every improvement in train loss
            if avg_train_loss < best_val_loss:
                best_val_loss = avg_train_loss
                save_path = os.path.join(CHECKPOINT_DIR, 'crnn_best.pth')
                torch.save(model.state_dict(), save_path)
                val_str += " ★ saved"

        print(f"  Epoch {epoch+1:3d}/{epochs} | Train: {avg_train_loss:.4f} | {val_str}")

    # ── Save latest ──
    latest_path = os.path.join(CHECKPOINT_DIR, 'crnn_latest.pth')
    torch.save(model.state_dict(), latest_path)

    print("-" * 60)
    print(f"  Best loss: {best_val_loss:.4f}")
    print(f"  Saved: crnn_best.pth, crnn_latest.pth")
    print("=" * 60)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='CRNN Fine-Tuning')
    parser.add_argument('--epochs', type=int, default=10, help='Number of epochs')
    parser.add_argument('--lr', type=float, default=0.0001, help='Learning rate')
    parser.add_argument('--batch-size', type=int, default=32, help='Batch size')
    parser.add_argument('--fine-tune', action='store_true',
                        help='Fine-tune from existing crnn_best.pth')
    args = parser.parse_args()

    retrain(
        epochs=args.epochs,
        lr=args.lr,
        fine_tune=args.fine_tune,
        batch_size=args.batch_size,
    )
