import sys
import secrets
from database import SessionLocal, add_api_client, get_api_client_by_name

def create_api_key_for_client():
    """
    A command-line script to generate and save a secure API key for a B2B client.
    """
    print("--- Create New B2B Client API Key ---")
    
    client_name = input("Enter a unique name for the client (e.g., HealthTechCo): ").strip()
    if not client_name:
        print("Client name cannot be empty. Exiting.")
        sys.exit(1)

    db_session = None
    try:
        db_session = SessionLocal()
        
        # Check if client name already exists
        if get_api_client_by_name(db_session, client_name):
            print(f"Error: A client with the name '{client_name}' already exists.")
            return

        # 1. Generate the secure API key
        # This is the key you will give to the client.
        api_key = f"nbk_live_{secrets.token_hex(32)}" # "nbk" = NutriBot Key

        # 2. Add the client and the *hashed* key to the database
        new_client = add_api_client(db_session, client_name, api_key)
        
        print("\n" + "="*40)
        print("✅ Success! Client and API Key generated.")
        print(f"   Client Name: {new_client.client_name}")
        print(f"   Client ID (for your records): {new_client.id}")
        print("\n" + "="*40)
        print("\nIMPORTANT: Give this API Key to your client.")
        print("It will not be shown again.\n")
        print(f"   {api_key}\n")
        print("="*40)

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if db_session:
            db_session.close()

if __name__ == "__main__":
    # This ensures the new ApiClient table is created
    from database import create_db_and_tables
    create_db_and_tables() 
    
    create_api_key_for_client()