"""
============================================================================
 AUTOMATED RETRAINING SCHEDULER
============================================================================
 Runs every 30 days. Extracts user feedback corrections, generates
 synthetic word crops, merges with training data, and (if GPU available)
 fine-tunes the CRNN model.

 Integration:
     from scheduler import init_scheduler
     scheduler = init_scheduler(app)
============================================================================
"""

import os
import json
import shutil
import csv
import logging
import subprocess
import numpy as np
from datetime import datetime

# ── Logging Setup ─────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger('retraining')
logger.setLevel(logging.INFO)

if not logger.handlers:
    fh = logging.FileHandler(os.path.join(LOG_DIR, 'retraining.log'))
    fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('[RETRAIN] %(message)s'))
    logger.addHandler(ch)


# ── Paths ─────────────────────────────────────────────────────

MODELS_DIR = os.path.join(BASE_DIR, 'models')
CHECKPOINTS_DIR = os.path.join(MODELS_DIR, 'checkpoints')
DATASET_DIR = os.path.join(MODELS_DIR, 'dataset')
VERSIONS_DIR = os.path.join(MODELS_DIR, 'versions')
os.makedirs(VERSIONS_DIR, exist_ok=True)


# ── Pipeline Steps ────────────────────────────────────────────

def extract_training_feedback(app):
    """
    Extract correction feedback from PostgreSQL that hasn't been used in training.
    Returns list of dicts with id, original, corrected.
    """
    with app.app_context():
        from db import db
        from model import Feedback

        feedbacks = Feedback.query.filter(
            Feedback.corrected_text.isnot(None),
            Feedback.corrected_text != '',
            Feedback.used_in_training == False,
        ).all()

        corrections = []
        for fb in feedbacks:
            if fb.corrected_text and fb.corrected_text.strip():
                corrections.append({
                    'id': fb.id,
                    'original': fb.original_text or '',
                    'corrected': fb.corrected_text.strip(),
                })

        logger.info(f"Extracted {len(corrections)} unused corrections from feedback table")
        return corrections


def generate_synthetic_crops(corrections, output_dir):
    """
    Generate synthetic word crop images for each corrected medicine name.
    Creates clean + 3 augmented versions per name.
    """
    from crnn_engine import create_word_image

    new_entries = []
    img_idx = 0

    for corr in corrections:
        name = corr['corrected']

        for aug_idx in range(4):  # clean + 3 augmentations
            img = create_word_image(name, target_h=32, max_w=128)

            if aug_idx > 0:
                img = img.astype(np.float32)
                if aug_idx == 1:
                    img = np.clip(img * 0.8, 0, 255)       # darker
                elif aug_idx == 2:
                    img = np.clip(img * 1.2, 0, 255)       # brighter
                elif aug_idx == 3:
                    noise = np.random.normal(0, 10, img.shape)
                    img = np.clip(img + noise, 0, 255)      # noisy
                img = img.astype(np.uint8)

            fname = f"feedback_{img_idx:05d}_aug{aug_idx}.png"
            try:
                from PIL import Image
                pil_img = Image.fromarray(img, mode='L')
                pil_img.save(os.path.join(output_dir, fname))
            except Exception as e:
                logger.warning(f"Failed to save crop {fname}: {e}")
                continue

            new_entries.append({
                'image_file': fname,
                'label': name,
            })
            img_idx += 1

    logger.info(f"Generated {len(new_entries)} synthetic crops from {len(corrections)} corrections")
    return new_entries


def merge_training_data(new_entries, train_csv_path):
    """Merge new synthetic crops with existing training CSV. Backs up first."""
    existing = []
    with open(train_csv_path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        existing = list(reader)

    # Backup
    timestamp = datetime.now().strftime('%Y%m%d')
    backup_path = train_csv_path + f'.backup_{timestamp}'
    if not os.path.exists(backup_path):
        shutil.copy2(train_csv_path, backup_path)
        logger.info(f"Backed up train.csv → {os.path.basename(backup_path)}")

    # Merge
    merged = existing + new_entries

    with open(train_csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['image_file', 'label'])
        writer.writeheader()
        writer.writerows(merged)

    logger.info(f"Merged: {len(existing)} existing + {len(new_entries)} new = {len(merged)} total")
    return len(merged)


def mark_feedback_used(app, correction_ids):
    """Mark feedback entries as used_in_training."""
    with app.app_context():
        from db import db
        from model import Feedback

        Feedback.query.filter(Feedback.id.in_(correction_ids)).update(
            {'used_in_training': True}, synchronize_session=False
        )
        db.session.commit()
        logger.info(f"Marked {len(correction_ids)} feedbacks as used_in_training")


def version_model(timestamp):
    """Copy current best model to versions directory with timestamp."""
    src = os.path.join(CHECKPOINTS_DIR, 'crnn_best.pth')
    if os.path.exists(src):
        dst = os.path.join(VERSIONS_DIR, f'crnn_{timestamp}.pth')
        shutil.copy2(src, dst)
        logger.info(f"Model versioned → {os.path.basename(dst)}")
        return dst
    return None


def set_reload_flag(timestamp):
    """Set a flag file so the running app knows to hot-reload the CRNN model."""
    flag_path = os.path.join(CHECKPOINTS_DIR, '.reload_requested')
    with open(flag_path, 'w') as f:
        f.write(timestamp)
    logger.info("Hot-reload flag set")


# ── Main Pipeline ─────────────────────────────────────────────

def retrain_crnn(app):
    """
    Full retraining pipeline:
    1. Extract feedback corrections
    2. Generate synthetic word crops
    3. Merge with training data
    4. Fine-tune CRNN (via subprocess if script exists)
    5. Version the model
    6. Mark feedback as used
    7. Set hot-reload flag
    """
    logger.info("=" * 60)
    logger.info("RETRAINING PIPELINE STARTED")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 60)

    try:
        # Step 1: Extract corrections
        corrections = extract_training_feedback(app)
        if not corrections:
            logger.info("No new corrections found. Skipping retraining.")
            return

        # Step 2: Generate synthetic crops
        crops_dir = os.path.join(DATASET_DIR, 'word_crops')
        os.makedirs(crops_dir, exist_ok=True)
        new_entries = generate_synthetic_crops(corrections, crops_dir)

        if not new_entries:
            logger.warning("No synthetic crops generated. Skipping.")
            return

        # Step 3: Merge with training data
        train_csv = os.path.join(DATASET_DIR, 'train.csv')
        if os.path.exists(train_csv):
            total_samples = merge_training_data(new_entries, train_csv)
        else:
            logger.warning(f"train.csv not found at {train_csv}. Saving corrections only.")

        # Step 4: Attempt fine-tuning
        retrain_script = os.path.join(BASE_DIR, 'scripts', 'retrain_crnn.py')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if os.path.exists(retrain_script):
            logger.info("Starting fine-tune training (10 epochs)...")
            try:
                result = subprocess.run(
                    ['python', retrain_script, '--epochs', '10', '--fine-tune'],
                    cwd=BASE_DIR,
                    capture_output=True,
                    text=True,
                    timeout=7200,  # 2 hour timeout
                )
                if result.returncode == 0:
                    logger.info(f"Retraining completed successfully")
                    logger.info(f"Output (last 500 chars): {result.stdout[-500:]}")
                else:
                    logger.error(f"Retraining failed (exit code {result.returncode})")
                    logger.error(f"Stderr: {result.stderr[-500:]}")
                    # Still save corrections for future use
                    _save_pending_corrections(corrections, timestamp)
                    return
            except subprocess.TimeoutExpired:
                logger.error("Retraining timed out after 2 hours")
                _save_pending_corrections(corrections, timestamp)
                return
        else:
            logger.warning("retrain_crnn.py not found. Saving corrections for manual retraining.")
            _save_pending_corrections(corrections, timestamp)
            # Still mark as used and version
            mark_feedback_used(app, [c['id'] for c in corrections])
            return

        # Step 5: Version the model
        version_model(timestamp)

        # Step 6: Mark feedback as used
        mark_feedback_used(app, [c['id'] for c in corrections])

        # Step 7: Set hot-reload flag
        set_reload_flag(timestamp)

        logger.info("=" * 60)
        logger.info("RETRAINING PIPELINE COMPLETED SUCCESSFULLY")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Retraining pipeline error: {e}", exc_info=True)


def _save_pending_corrections(corrections, timestamp):
    """Save corrections to a JSON file for manual retraining later."""
    out_path = os.path.join(
        DATASET_DIR,
        f'pending_corrections_{timestamp}.json'
    )
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(corrections, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved {len(corrections)} corrections → {os.path.basename(out_path)}")


# ── Scheduler Init ────────────────────────────────────────────

def init_scheduler(app):
    """
    Initialize and start the APScheduler background scheduler.
    Runs retrain_crnn every 30 days.
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger
    except ImportError:
        logger.warning("APScheduler not installed. Run: pip install APScheduler")
        logger.warning("Retraining scheduler NOT started.")
        return None

    scheduler = BackgroundScheduler(
        daemon=True,
        job_defaults={
            'coalesce': True,       # Merge missed runs into one
            'max_instances': 1,     # Never run two retrains at once
        }
    )

    scheduler.add_job(
        func=retrain_crnn,
        args=[app],
        trigger=IntervalTrigger(days=30),
        id='crnn_retrain',
        name='CRNN Model Retraining (30-day cycle)',
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Retraining scheduler started (interval: 30 days)")

    return scheduler
