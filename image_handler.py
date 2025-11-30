import os
import csv
import re

def load_image_annotations():
    annotation_file = os.path.join("data", "image_annotations.csv")
    if not os.path.exists(annotation_file):
        return []
    with open(annotation_file, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return [row for row in reader]

IMAGE_ANNOTATIONS = load_image_annotations()

def find_image_url(query: str) -> str | None:
    """
    Searches annotations for the best matching image file based on a
    descriptive query from the LLM, with improved keyword matching.
    """
    if not IMAGE_ANNOTATIONS:
        return None

    # --- Smarter Keyword Extraction ---
    stop_words = {'a', 'an', 'the', 'of', 'in', 'a', 'single', 'photo', 'image', 'bowl', 'plate'}
    query_words = set(query.lower().split()) - stop_words
    
    print(f"\n[DEBUG] Image search initiated.")
    print(f"  - LLM Query: '{query}'")
    print(f"  - Search Keywords: {query_words}")

    best_match = None
    highest_score = 0

    for annotation in IMAGE_ANNOTATIONS:
        description_words = set(annotation.get('description', '').lower().split()) - stop_words
        
        score = len(query_words.intersection(description_words))
        
        if score > highest_score:
            highest_score = score
            best_match = annotation.get('filename')

    if best_match and highest_score > 0: # More flexible threshold
        image_path = os.path.join("data", "images", best_match)
        print(f"  - Best Match Found: '{best_match}' (Score: {highest_score})")
        print(f"  - Returning Path: '{image_path}'")
        return image_path
    
    print(f"  - No suitable image match found.")
    return None

def parse_response_for_image(text: str) -> dict:
    match = re.search(r"\[IMAGE:\s*(.*?)\]", text)
    if match:
        query = match.group(1).strip()
        cleaned_text = text.replace(match.group(0), "").strip()
        image_url = find_image_url(query)
        return {"answer": cleaned_text, "image_url": image_url}
    else:
        return {"answer": text, "image_url": None}