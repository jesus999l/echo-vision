"""
Tidy Agent — Filesystem organization and cleanup.
Usage: python tidy_agent.py --dir ~/Downloads
"""
import os
import shutil
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tidy_agent")

EXTENSIONS = {
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"],
    "Documents": [".pdf", ".docx", ".doc", ".txt", ".md", ".xlsx", ".pptx"],
    "Media": [".mp4", ".mkv", ".mov", ".mp3", ".wav", ".flac"],
    "Archives": [".zip", ".tar.gz", ".rar", ".7z"],
    "Code": [".py", ".js", ".html", ".css", ".go", ".c", ".cpp"],
}

def tidy_directory(target_dir):
    target_dir = os.path.expanduser(target_dir)
    if not os.path.exists(target_dir):
        logger.error(f"Directory not found: {target_dir}")
        return f"Error: {target_dir} not found."

    count = 0
    for filename in os.listdir(target_dir):
        filepath = os.path.join(target_dir, filename)
        if os.path.isdir(filepath):
            continue

        _, ext = os.path.splitext(filename)
        ext = ext.lower()

        moved = False
        for category, exts in EXTENSIONS.items():
            if ext in exts:
                dest_dir = os.path.join(target_dir, category)
                os.makedirs(dest_dir, exist_ok=True)
                try:
                    shutil.move(filepath, os.path.join(dest_dir, filename))
                    logger.info(f"Moved {filename} to {category}")
                    count += 1
                    moved = True
                    break
                except Exception as e:
                    logger.error(f"Failed to move {filename}: {e}")

        if not moved and ext:
            # Move to "Others"
            dest_dir = os.path.join(target_dir, "Others")
            os.makedirs(dest_dir, exist_ok=True)
            try:
                shutil.move(filepath, os.path.join(dest_dir, filename))
                logger.info(f"Moved {filename} to Others")
                count += 1
            except Exception as e:
                logger.error(f"Failed to move {filename}: {e}")

    return f"Tidy complete. Moved {count} files in {target_dir}."

if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "~/Downloads"
    print(tidy_directory(target))
