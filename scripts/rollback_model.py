"""
 MODEL ROLLBACK — Restore a previous CRNN model version
 Usage:
     python scripts/rollback_model.py                    # rollback to previous
     python scripts/rollback_model.py crnn_20260424.pth  # rollback to specific

 Lists available versions and restores the selected one.
 Sets the hot-reload flag so the running app picks it up.
"""
import os
import sys
import glob
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSIONS_DIR = os.path.join(BASE_DIR, 'models', 'versions')
CHECKPOINT_DIR = os.path.join(BASE_DIR, 'models', 'checkpoints')


def list_versions():
    """List all available model versions."""
    versions = sorted(glob.glob(os.path.join(VERSIONS_DIR, 'crnn_*.pth')))
    if not versions:
        print("  No versioned models found in models/versions/")
        return []

    print(f"\n  Available versions ({len(versions)}):")
    for i, v in enumerate(versions):
        size_mb = os.path.getsize(v) / (1024 * 1024)
        mtime = os.path.getmtime(v)
        from datetime import datetime
        ts = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
        name = os.path.basename(v)
        marker = " ← latest" if i == len(versions) - 1 else ""
        print(f"    [{i+1}] {name} ({size_mb:.1f} MB, {ts}){marker}")

    return versions


def rollback(version_file=None):
    print("=" * 60)
    print("  CRNN MODEL ROLLBACK")
    print("=" * 60)

    versions = list_versions()

    if version_file is None:
        if len(versions) < 2:
            print("\n  ERROR: Need at least 2 versions for automatic rollback.")
            print("  Specify a version file explicitly.")
            return False
        version_path = versions[-2]  # Second-to-last
    else:
        # Check if it's just a filename
        if not os.path.isabs(version_file):
            # Try in versions dir
            candidate = os.path.join(VERSIONS_DIR, version_file)
            if os.path.exists(candidate):
                version_path = candidate
            else:
                print(f"\n  ERROR: Version file not found: {version_file}")
                return False
        else:
            version_path = version_file

    if not os.path.exists(version_path):
        print(f"\n  ERROR: File not found: {version_path}")
        return False

    target = os.path.join(CHECKPOINT_DIR, 'crnn_best.pth')

    # Backup current model before rollback
    if os.path.exists(target):
        backup = target + '.pre_rollback'
        shutil.copy2(target, backup)
        print(f"\n  Backed up current model → crnn_best.pth.pre_rollback")

    # Copy versioned model to active location
    shutil.copy2(version_path, target)
    print(f"  Restored: {os.path.basename(version_path)} → crnn_best.pth")

    # Set hot-reload flag
    flag_path = os.path.join(CHECKPOINT_DIR, '.reload_requested')
    with open(flag_path, 'w') as f:
        f.write('rollback')
    print(f"  Hot-reload flag set")

    print(f"\n Rollback complete. Model will reload on next request.")
    return True


if __name__ == '__main__':
    if len(sys.argv) > 1:
        rollback(sys.argv[1])
    else:
        rollback()
