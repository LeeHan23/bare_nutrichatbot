import os
from fastapi import UploadFile
from file_utils import save_instruction_file as save_file

# Define the base directory for all user-specific instructions
BASE_INSTRUCTIONS_DIR = os.path.join("data", "instructions")

def save_instruction_file(user_id: str, uploaded_file: UploadFile):
    """
    Saves a user-uploaded .docx file as their specific instruction text.

    This function takes an uploaded file, converts it to a plain text file
    using the utility from the uploader module, and saves it to a
    user-specific directory. Each user will have their own folder,
    and the instruction file will be named consistently to allow for easy retrieval.

    Args:
        user_id (str): The unique identifier for the user.
        uploaded_file (UploadFile): The .docx file uploaded by the user.
    
    Returns:
        str: The path to the saved text file, or None if an error occurred.
    """
    return save_file(user_id, uploaded_file)