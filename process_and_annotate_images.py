import os
import csv
import base64
import fitz  # PyMuPDF
from openai import OpenAI
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()
# List of PDF files to process
PDF_FILES = [
    "Food Group .pdf",
    "Malaysian food portion size  photo album.pdf"
]
IMAGE_OUTPUT_DIR = os.path.join("data", "images")
ANNOTATION_FILE = os.path.join("data", "image_annotations.csv")
VISION_MODEL = "gpt-4o"  # GPT-4 with Vision is required for this task

# --- Initialize OpenAI Client ---
client = OpenAI()

def encode_image(image_bytes):
    """Encodes image bytes to a base64 string."""
    return base64.b64encode(image_bytes).decode('utf-8')

def get_contextual_ai_description(base64_image, page_text):
    """
    Shows an image AND the text from its page to the OpenAI Vision API
    and asks for a context-aware description.
    """
    try:
        response = client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"""
                            Analyze the following image in the context of the text provided from the same PDF page.
                            Your task is to create a concise, factual description of the food item and its specific serving size as mentioned in the text.

                            **Page Text Context:**
                            ---
                            {page_text}
                            ---

                            Based on both the image and the text, provide the description.
                            Example output: 'White rice, 1 scoop, 63g' or 'A glass of low-fat milk, 240ml'.
                            """
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=60
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        return "Description generation failed."

def process_and_annotate():
    """
    Extracts images and their surrounding text from PDFs, uses a vision model
    to generate context-aware annotations, saves the images, and creates a CSV
    of the annotations.
    """
    os.makedirs(IMAGE_OUTPUT_DIR, exist_ok=True)
    
    # Load existing annotations to avoid re-processing
    existing_annotations = {}
    if os.path.exists(ANNOTATION_FILE):
        with open(ANNOTATION_FILE, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader) # Skip header
            for row in reader:
                if row: existing_annotations[row[0]] = row[1]

    with open(ANNOTATION_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "description"])

        # First, write back the existing annotations
        for filename, description in existing_annotations.items():
            writer.writerow([filename, description])

        for pdf_file in PDF_FILES:
            if not os.path.exists(pdf_file):
                print(f"Warning: PDF file not found at '{pdf_file}'. Skipping.")
                continue

            print(f"--- Processing {pdf_file} ---")
            doc = fitz.open(pdf_file)

            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                page_text = page.get_text("text")
                image_list = page.get_images(full=True)

                for img_index, img in enumerate(image_list, start=1):
                    xref = img[0]
                    filename_prefix = os.path.splitext(os.path.basename(pdf_file))[0].replace(" ", "_")
                    image_filename = f"{filename_prefix}_p{page_num + 1}_img{img_index}.png"

                    # Check if we have already processed this image
                    if image_filename in existing_annotations:
                        print(f"Skipping '{image_filename}': Already annotated.")
                        continue

                    try:
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        
                        print(f"Annotating '{image_filename}' using page {page_num + 1} text...")
                        base64_image = encode_image(image_bytes)
                        description = get_contextual_ai_description(base64_image, page_text)
                        
                        # Save the image file
                        output_path = os.path.join(IMAGE_OUTPUT_DIR, image_filename)
                        with open(output_path, "wb") as img_file:
                            img_file.write(image_bytes)
                        
                        # Write the new annotation to the CSV
                        writer.writerow([image_filename, description])

                    except Exception as e:
                        print(f"Could not process image {img_index} on page {page_num + 1}: {e}")

            doc.close()
    
    print("\n✅ Context-aware image processing and annotation complete!")
    print(f"All images are saved in '{IMAGE_OUTPUT_DIR}'.")
    print(f"All annotations are saved in '{ANNOTATION_FILE}'.")

if __name__ == "__main__":
    process_and_annotate()