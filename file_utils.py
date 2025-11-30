import os
from fastapi import UploadFile
from uploader import save_uploaded_file_as_text

BASE_INSTRUCTIONS_DIR = os.path.join("data", "instructions")

def save_instruction_file(user_id: str, uploaded_file: UploadFile):
    """
    Saves a user-uploaded file as their specific instruction text.
    """
    if not user_id or not uploaded_file:
        print("Error: User ID and an uploaded file must be provided.")
        return None

    user_instructions_dir = os.path.join(BASE_INSTRUCTIONS_DIR, str(user_id))
    os.makedirs(user_instructions_dir, exist_ok=True)
    
    try:
        saved_path = save_uploaded_file_as_text(uploaded_file, user_instructions_dir)
        print(f"Successfully saved new instructions for user '{user_id}' at: {saved_path}")
        return saved_path
        
    except Exception as e:
        print(f"Error saving instruction file for user '{user_id}': {e}")
        return None