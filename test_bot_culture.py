import requests
import json
import sys
import os
import time

# Configuration
API_URL = "https://leehan23-nutribot-api.hf.space"
# API_URL = "http://localhost:8000" # Uncomment for local testing

# Cultural Test Scenarios
CULTURAL_SCENARIOS = {
    "🥥 Malay Culture (Nasi Lemak & Santan)": [
        "I eat Nasi Lemak every morning, is that bad?",
        "I love Masak Lemak Cili Api, but I'm worried about the santan.",
        "What are some healthier Malay breakfast options?"
    ],
    "🥢 Chinese Culture (Tai Chow & Soups)": [
        "We usually eat Tai Chow style with family. How do I control my portion?",
        "Is herbal soup 'heaty' or 'cooling'? Can I drink it every day?",
        "I like Bak Kut Teh (herbal pork soup), is it high in cholesterol?"
    ],
    "🍛 Indian Culture (Roti & Curry)": [
        "I can't give up my Roti Canai and Teh Tarik for breakfast.",
        "Is Thosai healthier than Roti Canai?",
        "I eat late night at the Mamak often. What should I order?"
    ],
    "🇲🇾 General Malaysian Context": [
        "It's so hot lately, I keep drinking Sirap Bandung. Is that okay?",
        "How do I practice 'Suku-Suku Separuh' when eating mixed rice (Nasi Campur)?",
        "My family loves to feast during festivals. How do I not offend them but stay healthy?"
    ]
}

def run_tests():
    print("🇲🇾 Starting Cultural Accuracy Tests...")
    print(f"Target: {API_URL}")
    
    # Get API Key
    api_key = input("\n🔑 Enter your API Key (from reset_key.py): ").strip()
    if not api_key:
        print("❌ API Key required!")
        return

    print("\n" + "="*60)
    
    total_questions = sum(len(qs) for qs in CULTURAL_SCENARIOS.values())
    current_q = 0

    for category, questions in CULTURAL_SCENARIOS.items():
        print(f"\n\n📂 {category}")
        print("="*60)
        
        for question in questions:
            current_q += 1
            print(f"\n❓ Q{current_q}: {question}")
            print("-" * 20)
            
            try:
                start_time = time.time()
                response = requests.post(
                    f"{API_URL}/chat/get_response",
                    headers={"X-API-Key": api_key},
                    json={"question": question, "session_id": "test_culture_1"},
                    stream=True
                )
                
                if response.status_code == 200:
                    print("🤖 Answer: ", end="", flush=True)
                    full_answer = ""
                    for chunk in response.iter_content(chunk_size=None):
                        if chunk:
                            text = chunk.decode('utf-8')
                            print(text, end="", flush=True)
                            full_answer += text
                    
                    elapsed = time.time() - start_time
                    print(f"\n\n⏱️  Time: {elapsed:.2f}s")
                else:
                    print(f"❌ Error {response.status_code}: {response.text}")
                    
            except Exception as e:
                print(f"❌ Connection Error: {e}")
            
            # Small pause to be nice to the server
            time.sleep(1)
            
    print("\n" + "="*60)
    print("✅ Cultural Tests Complete!")

if __name__ == "__main__":
    run_tests()
