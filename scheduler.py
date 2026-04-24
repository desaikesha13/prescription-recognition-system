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


MODELS_DIR = os.path.join(BASE_DIR, 'models')
CHECKPOINTS_DIR = os.path.join(MODELS_DIR, 'checkpoints')
DATASET_DIR = os.path.join(MODELS_DIR, 'dataset')
VERSIONS_DIR = os.path.join(MODELS_DIR, 'versions')
os.makedirs(VERSIONS_DIR, exist_ok=True)


def extract_training_feedback(app):
    """Extract unused correction feedback from database."""
    with app.app_context():
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

        logger.info(f"Extracted {len(corrections)} unused corrections")
        return corrections


def generate_synthetic_crops(corrections, output_dir):
    """Generate synthetic images for corrected medicine names."""
    from crnn_engine import create_word_image
    from PIL import Image

    new_entries = []
    img_idx = 0

    for corr in corrections:
        name = corr['corrected']

        for aug_idx in range(4):
            img = create_word_image(name, target_h=32, max_w=128)

            if aug_idx > 0:
                img = img.astype(np.float32)
                if aug_idx == 1:
                    img = np.clip(img * 0.8, 0, 255)
                elif aug_idx == 2:
                    img = np.clip(img * 1.2, 0, 255)
                elif aug_idx == 3:
                    noise = np.random.normal(0, 10, img.shape)
                    img = np.clip(img + noise, 0, 255)
                img = img.astype(np.uint8)

            fname = f"feedback_{img_idx:05d}_aug{aug_idx}.png"
            try:
                Image.fromarray(img, mode='L').save(os.path.join(output_dir, fname))
            except Exception as e:
                logger.warning(f"Failed to save crop {fname}: {e}")
                continue

            new_entries.append({
                'image_file': fname,
                'label': name,
            })
            img_idx += 1

    logger.info(f"Generated {len(new_entries)} synthetic crops")
    return new_entries


def merge_training_data(new_entries, train_csv_path):
    """Merge new synthetic crops into training CSV with backup."""
    with open(train_csv_path, 'r', newline='', encoding='utf-8') as f:
        existing = list(csv.DictReader(f))

    timestamp = datetime.now().strftime('%Y%m%d')
    backup_path = train_csv_path + f'.backup_{timestamp}'
    if not os.path.exists(backup_path):
        shutil.copy2(train_csv_path, backup_path)
        logger.info(f"Backup created: {os.path.basename(backup_path)}")

    merged = existing + new_entries

    with open(train_csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['image_file', 'label'])
        writer.writeheader()
        writer.writerows(merged)

    logger.info(f"Merged dataset size: {len(merged)}")
    return len(merged)


def mark_feedback_used(app, correction_ids):
    """Mark feedback entries as used."""
    with app.app_context():
        from db import db
        from model import Feedback

        Feedback.query.filter(Feedback.id.in_(correction_ids)).update(
            {'used_in_training': True}, synchronize_session=False
        )
        db.session.commit()

        logger.info(f"Marked {len(correction_ids)} feedback entries")


def version_model(timestamp):
    """Save versioned model copy."""
    src = os.path.join(CHECKPOINTS_DIR, 'crnn_best.pth')
    if os.path.exists(src):
        dst = os.path.join(VERSIONS_DIR, f'crnn_{timestamp}.pth')
        shutil.copy2(src, dst)
        logger.info(f"Model versioned: {os.path.basename(dst)}")
        return dst
    return None


def set_reload_flag(timestamp):
    """Trigger model reload flag."""
    flag_path = os.path.join(CHECKPOINTS_DIR, '.reload_requested')
    with open(flag_path, 'w') as f:
        f.write(timestamp)
    logger.info("Reload flag set")


def retrain_crnn(app):
    """Run full retraining pipeline."""
    logger.info("RETRAINING STARTED")

    try:
        corrections = extract_training_feedback(app)
        if not corrections:
            logger.info("No new corrections found")
            return

        crops_dir = os.path.join(DATASET_DIR, 'word_crops')
        os.makedirs(crops_dir, exist_ok=True)
        new_entries = generate_synthetic_crops(corrections, crops_dir)

        if not new_entries:
            logger.warning("No synthetic data generated")
            return

        train_csv = os.path.join(DATASET_DIR, 'train.csv')
        if os.path.exists(train_csv):
            merge_training_data(new_entries, train_csv)

        retrain_script = os.path.join(BASE_DIR, 'scripts', 'retrain_crnn.py')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if os.path.exists(retrain_script):
            try:
                result = subprocess.run(
                    ['python', retrain_script, '--epochs', '10', '--fine-tune'],
                    cwd=BASE_DIR,
                    capture_output=True,
                    text=True,
                    timeout=7200,
                )
                if result.returncode != 0:
                    logger.error("Retraining failed")
                    _save_pending_corrections(corrections, timestamp)
                    return
            except subprocess.TimeoutExpired:
                logger.error("Retraining timeout")
                _save_pending_corrections(corrections, timestamp)
                return
        else:
            _save_pending_corrections(corrections, timestamp)
            mark_feedback_used(app, [c['id'] for c in corrections])
            return

        version_model(timestamp)
        mark_feedback_used(app, [c['id'] for c in corrections])
        set_reload_flag(timestamp)

        logger.info("RETRAINING COMPLETED")

    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)


def _save_pending_corrections(corrections, timestamp):
    """Save corrections for later retraining."""
    out_path = os.path.join(DATASET_DIR, f'pending_corrections_{timestamp}.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(corrections, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved {len(corrections)} pending corrections")


def init_scheduler(app):
    """Initialize APScheduler for periodic retraining."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger
    except ImportError:
        logger.warning("APScheduler not installed")
        return None

    scheduler = BackgroundScheduler(
        daemon=True,
        job_defaults={
            'coalesce': True,
            'max_instances': 1,
        }
    )

    scheduler.add_job(
        func=retrain_crnn,
        args=[app],
        trigger=IntervalTrigger(days=30),
        id='crnn_retrain',
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started (30-day interval)")

    return scheduler
