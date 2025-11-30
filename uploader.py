import os
import docx
from fastapi import UploadFile
from datetime import datetime
from io import BytesIO
from pypdf import PdfReader

async def save_uploaded_file_as_text(uploaded_file: UploadFile, destination_folder: str) -> str:
    """
    Asynchronously reads an uploaded .docx or .pdf file, extracts its text content,
    and saves it as a .txt file.
    """
    try:
        original_filename = getattr(uploaded_file, 'filename', getattr(uploaded_file, 'name', 'unknown_file'))

        base_filename = os.path.splitext(original_filename)[0]
        sanitized_filename = "".join(c for c in base_filename if c.isalnum() or c in (' ', '_')).rstrip()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_filename = f"{sanitized_filename}_{timestamp}.txt"
        save_path = os.path.join(destination_folder, new_filename)

        print(f"Processing upload: '{original_filename}' -> '{new_filename}'")

        # --- FIX: Asynchronously read the file content ---
        file_content = await uploaded_file.read()

        content = ""

        if original_filename.endswith(".docx"):
            print("Detected .docx file. Parsing with python-docx.")
            doc = docx.Document(BytesIO(file_content))
            full_text = [para.text for para in doc.paragraphs]
            content = '\n'.join(full_text)
        
        elif original_filename.endswith(".pdf"):
            print("Detected .pdf file. Parsing with pypdf.")
            reader = PdfReader(BytesIO(file_content))
            full_text = [page.extract_text() for page in reader.pages if page.extract_text()]
            content = '\n'.join(full_text)

        if not content.strip():
            print(f"Warning: The uploaded document '{original_filename}' appears to be empty or could not be parsed.")

        with open(save_path, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"Successfully saved extracted text to: {save_path}")
        return save_path

    except Exception as e:
        print(f"Error processing uploaded file '{original_filename}': {e}")
        raise

