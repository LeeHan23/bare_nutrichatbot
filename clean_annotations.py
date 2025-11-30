import os
import csv

# --- Configuration ---
IMAGE_DIR = os.path.join("data", "images")
ANNOTATION_FILE = os.path.join("data", "image_annotations.csv")

def clean_and_sync_annotations():
    """
    Synchronizes the annotation CSV file with the actual images in the
    images folder. It removes entries for deleted images and identifies
    any new, un-annotated images.
    """
    if not os.path.exists(IMAGE_DIR):
        print(f"Error: Image directory not found at '{IMAGE_DIR}'.")
        return

    if not os.path.exists(ANNOTATION_FILE):
        print(f"Error: Annotation file not found at '{ANNOTATION_FILE}'.")
        print("Please create one first using 'process_and_annotate_images.py'.")
        return

    # 1. Get the list of actual image files
    try:
        actual_images = set(f for f in os.listdir(IMAGE_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg')))
        print(f"Found {len(actual_images)} images in the '{IMAGE_DIR}' folder.")
    except FileNotFoundError:
        print(f"Error: Could not find the image directory at '{IMAGE_DIR}'.")
        return

    # 2. Read the existing annotations
    existing_annotations = []
    try:
        with open(ANNOTATION_FILE, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            existing_annotations = list(reader)
    except FileNotFoundError:
        print(f"Annotation file not found. A new one will be created.")
    
    # 3. Synchronize: Keep only annotations for images that still exist
    cleaned_annotations = []
    removed_count = 0
    annotated_files = set()

    for row in existing_annotations:
        filename = row.get("filename")
        if filename in actual_images:
            cleaned_annotations.append(row)
            annotated_files.add(filename)
        else:
            removed_count += 1
            print(f"Removing annotation for deleted image: {filename}")

    # 4. Identify any new, un-annotated images
    unannotated_images = actual_images - annotated_files
    if unannotated_images:
        print("\nWarning: Found new images that need to be annotated.")
        for filename in sorted(unannotated_images):
            print(f"  - {filename}")
            cleaned_annotations.append({"filename": filename, "description": ""})
        print("\nIt's recommended to run 'process_and_annotate_images.py' again to automatically generate descriptions for these new files.")


    # 5. Rewrite the annotation file with the cleaned data
    try:
        with open(ANNOTATION_FILE, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ["filename", "description"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(cleaned_annotations)
    except IOError as e:
        print(f"Error writing to the annotation file: {e}")
        return

    print(f"\n✅ Success! The annotation file has been cleaned.")
    print(f"   - Removed {removed_count} entries for deleted images.")
    print(f"   - Found {len(unannotated_images)} new images that need annotation.")


if __name__ == "__main__":
    clean_and_sync_annotations()