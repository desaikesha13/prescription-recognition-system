"""
==============================================================================
 CRNN VALIDATION ENGINE — Local CPU Inference
 Extracted from Colab Pipeline for standalone use
==============================================================================

 Validates medicine names by:
   1. Rendering the name as a synthetic 32×128 grayscale image
   2. Running CRNN inference (CNN + BiLSTM + CTC)
   3. Comparing CRNN output to original name

 Usage:
   from crnn_engine import CRNNValidator
   validator = CRNNValidator()
   result = validator.validate("Paracetamol")
==============================================================================
"""

import os
import json
import numpy as np
import torch
import torch.nn as nn
from PIL import Image, ImageDraw, ImageFont

# ============================================================
# MODEL ARCHITECTURE (matching notebook exactly)
# ============================================================

class CNNFeatureExtractor(nn.Module):
    def __init__(self):
        super().__init__()
        self.block1 = nn.Sequential(
            nn.Conv2d(1, 64, 3, 1, 1), nn.BatchNorm2d(64),
            nn.ReLU(True), nn.MaxPool2d(2, 2))
        self.block2 = nn.Sequential(
            nn.Conv2d(64, 128, 3, 1, 1), nn.BatchNorm2d(128),
            nn.ReLU(True), nn.MaxPool2d(2, 2))
        self.block3 = nn.Sequential(
            nn.Conv2d(128, 256, 3, 1, 1), nn.BatchNorm2d(256), nn.ReLU(True),
            nn.Conv2d(256, 256, 3, 1, 1), nn.BatchNorm2d(256), nn.ReLU(True),
            nn.MaxPool2d((2, 1), (2, 1)))
        self.block4 = nn.Sequential(
            nn.Conv2d(256, 512, 3, 1, 1), nn.BatchNorm2d(512), nn.ReLU(True),
            nn.Conv2d(512, 512, 3, 1, 1), nn.BatchNorm2d(512), nn.ReLU(True),
            nn.MaxPool2d((2, 1), (2, 1)))
        self.block5 = nn.Sequential(
            nn.Conv2d(512, 512, (2, 1), 1, 0), nn.BatchNorm2d(512), nn.ReLU(True))

    def forward(self, x):
        return self.block5(self.block4(self.block3(self.block2(self.block1(x)))))


class BiLSTMSequenceModeler(nn.Module):
    def __init__(self, input_size=512, hidden_size=256, num_layers=2, dropout=0.3):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers,
                            bidirectional=True,
                            dropout=dropout if num_layers > 1 else 0,
                            batch_first=True)

    def forward(self, x):
        output, _ = self.lstm(x)
        return output


class CRNN(nn.Module):
    def __init__(self, num_classes, lstm_hidden=256, lstm_layers=2, dropout=0.3):
        super().__init__()
        self.cnn = CNNFeatureExtractor()
        self.lstm = BiLSTMSequenceModeler(512, lstm_hidden, lstm_layers, dropout)
        self.fc = nn.Linear(lstm_hidden * 2, num_classes)
        self.dropout = nn.Dropout(dropout)
        self.log_softmax = nn.LogSoftmax(dim=2)

    def forward(self, images):
        conv = self.cnn(images)
        conv = conv.squeeze(2).permute(0, 2, 1)
        lstm_out = self.dropout(self.lstm(conv))
        output = self.log_softmax(self.fc(lstm_out))
        return output.permute(1, 0, 2)


# ============================================================
# CTC DECODER
# ============================================================

class CTCDecoder:
    def __init__(self, idx_to_char, blank_idx=0):
        self.idx_to_char = idx_to_char
        self.blank_idx = blank_idx

    def greedy_decode(self, log_probs):
        best = torch.argmax(log_probs, dim=1).cpu().numpy()
        decoded, prev = [], -1
        for idx in best:
            if idx != prev:
                decoded.append(idx)
            prev = idx
        decoded = [i for i in decoded if i != self.blank_idx]
        return ''.join([self.idx_to_char.get(i, '?') for i in decoded])


# ============================================================
# WORD IMAGE GENERATOR (synthetic rendering)
# ============================================================

def create_word_image(text, target_h=32, max_w=128):
    """Generate a synthetic grayscale word image for CRNN input."""
    img = Image.new('L', (max_w, target_h), color=255)
    draw = ImageDraw.Draw(img)
    font_size = int(target_h * 0.7)

    # Try system fonts (Windows → Linux fallbacks)
    font = None
    font_paths = [
        # Windows
        'C:/Windows/Fonts/consola.ttf',
        'C:/Windows/Fonts/arial.ttf',
        'C:/Windows/Fonts/cour.ttf',
        # Linux (Colab)
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf',
        '/usr/share/fonts/truetype/freefont/FreeMono.ttf',
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    text_h = bbox[3] - bbox[1]
    draw.text((2, (target_h - text_h) // 2), text, fill=0, font=font)
    return np.array(img)


# ============================================================
# EDIT DISTANCE (for match scoring)
# ============================================================

def edit_distance(s1, s2):
    m, n = len(s1), len(s2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i - 1] == s2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
    return dp[m][n]


# ============================================================
# CRNN VALIDATOR (main interface)
# ============================================================

class CRNNValidator:
    """
    Validates medicine names using a locally loaded CRNN model.

    Usage:
        validator = CRNNValidator()
        result = validator.validate("Paracetamol")
        # result = {'crnn_prediction': 'Paracetamol', 'crnn_confidence': 0.99,
        #           'match_score': 1.0, 'status': 'CRNN_CONFIRMED ✓'}
    """

    def __init__(self, model_dir=None):
        """
        Load CRNN model and vocabulary.

        Args:
            model_dir: Directory containing crnn_best.pth and dataset_metadata.json.
                       If None, auto-detects from known paths.
        """
        self.ready = False
        self.model = None
        self.decoder = None
        self.char_to_idx = {}
        self.device = torch.device('cpu')
        self.img_h = 32
        self.img_w = 128

        # Auto-detect paths
        base = os.path.dirname(os.path.abspath(__file__))

        # Search for model and metadata
        checkpoint_search = [
            os.path.join(base, 'models', 'checkpoints', 'crnn_best.pth'),
        ]
        metadata_search = [
            os.path.join(base, 'models', 'dataset', 'dataset_metadata.json'),
        ]

        if model_dir:
            checkpoint_search.insert(0, os.path.join(model_dir, 'crnn_best.pth'))
            metadata_search.insert(0, os.path.join(model_dir, 'dataset_metadata.json'))

        model_path = next((p for p in checkpoint_search if os.path.exists(p)), None)
        meta_path = next((p for p in metadata_search if os.path.exists(p)), None)

        if not model_path:
            print("[CRNN] ⚠ crnn_best.pth not found. CRNN validation disabled.")
            return
        if not meta_path:
            print("[CRNN] ⚠ dataset_metadata.json not found. CRNN validation disabled.")
            return

        try:
            # Load vocabulary
            with open(meta_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)

            vocab = metadata['vocab']
            self.char_to_idx = vocab['char_to_idx']
            idx_to_char = {int(k): v for k, v in vocab['idx_to_char'].items()}
            num_classes = vocab['num_classes']
            self.img_h = metadata.get('image_height', 32)
            self.img_w = metadata.get('image_width', 128)

            # Load model
            self.model = CRNN(num_classes, lstm_hidden=256, lstm_layers=2, dropout=0.0).to(self.device)
            self.model.load_state_dict(torch.load(model_path, map_location=self.device))
            self.model.eval()
            self.decoder = CTCDecoder(idx_to_char)
            self.ready = True

            print(f"[CRNN] ✓ Model loaded ({num_classes} classes, device={self.device})")

        except Exception as e:
            print(f"[CRNN] ✗ Failed to load model: {e}")
            self.ready = False

    def validate(self, medicine_name):
        """
        Validate a medicine name by generating a synthetic image and running CRNN.

        Returns dict with:
            - crnn_prediction: what CRNN read back
            - crnn_confidence: average max-probability across timesteps
            - match_score: 0.0–1.0 similarity between input and prediction
            - status: CRNN_CONFIRMED / CRNN_CLOSE_MATCH / CRNN_PARTIAL / CRNN_MISMATCH / SKIPPED
        """
        if not self.ready:
            return {
                'crnn_prediction': '',
                'crnn_confidence': 0.0,
                'match_score': 0.0,
                'status': 'N/A (model not loaded)',
            }

        # Check if all chars are in vocabulary
        valid_chars = all(ch in self.char_to_idx for ch in medicine_name)
        if not valid_chars:
            return {
                'crnn_prediction': '[chars not in vocab]',
                'crnn_confidence': 0.0,
                'match_score': 0.0,
                'status': 'SKIPPED (unsupported chars)',
            }

        # Generate synthetic word image
        word_img = create_word_image(medicine_name, self.img_h, self.img_w)
        img_normalized = word_img.astype(np.float32) / 255.0
        img_tensor = torch.FloatTensor(img_normalized).unsqueeze(0).unsqueeze(0).to(self.device)

        # Inference
        with torch.no_grad():
            log_probs = self.model(img_tensor)

        crnn_prediction = self.decoder.greedy_decode(log_probs[:, 0, :])
        probs = torch.exp(log_probs[:, 0, :])
        crnn_confidence = torch.max(probs, dim=1)[0].mean().item()

        # Compute match score
        if crnn_prediction.lower() == medicine_name.lower():
            match_score = 1.0
            status = "CRNN_CONFIRMED ✓"
        else:
            ed = edit_distance(crnn_prediction.lower(), medicine_name.lower())
            max_len = max(len(crnn_prediction), len(medicine_name), 1)
            match_score = max(0, 1.0 - (ed / max_len))

            if match_score >= 0.8:
                status = f"CRNN_CLOSE_MATCH (→ {crnn_prediction})"
            elif match_score >= 0.5:
                status = f"CRNN_PARTIAL (→ {crnn_prediction})"
            else:
                status = f"CRNN_MISMATCH (→ {crnn_prediction})"

        return {
            'crnn_prediction': crnn_prediction,
            'crnn_confidence': crnn_confidence,
            'match_score': match_score,
            'status': status,
        }


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == '__main__':
    print("=" * 50)
    print("CRNN Validator — Standalone Test")
    print("=" * 50)

    validator = CRNNValidator()

    if validator.ready:
        test_names = ['Paracetamol', 'Amoxicillin', 'Ibuprofen', 'Dolo', 'Azithromycin',
                      'Cefixime', 'Pantoprazole', 'Metformin', 'Atorvastatin']
        for name in test_names:
            result = validator.validate(name)
            conf_pct = round(result['crnn_confidence'] * 100)
            print(f"  {name:20s} → {result['status']:40s} (conf: {conf_pct}%)")
    else:
        print("Model not loaded. Check paths.")
