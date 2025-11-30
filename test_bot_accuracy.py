import requests
import json
import sys
import os
import time

# Configuration
API_URL = "https://leehan23-nutribot-api.hf.space"
# API_URL = "http://localhost:8000" # Uncomment for local testing

# Categorized Test Questions
TEST_SCENARIOS = {
    "🥗 Dietetics (Nutrition Standards)": [
        "What is the RNI for protein for adult men in Malaysia?",
        "How much calcium is recommended for adolescents (10-18 years)?",
        "Explain the Malaysian Food Pyramid for children.",
        "What are the key dietary guidelines for older people?"
    ],
    "❤️ Cardiology (Clinical Guidelines)": [
        "What are the clinical signs of heart failure?",
        "What is the initial management for Acute Coronary Syndrome (ACS)?",
        "What are the risk factors for hypertension?",
        "Explain the classification of heart failure."
    ],
    "🤝 Combined (Cardio-Nutrition)": [
        "What is the recommended sodium intake for patients with hypertension?",
        "Dietary management for heart failure patients with fluid retention.",
        "Is a high-protein diet safe for someone with chronic kidney disease and heart failure?",
        "Lifestyle modifications for managing high blood pressure."
    ],
    "🙋 Common Consumer Questions": [
        "I want to lose weight, what should I eat for breakfast?",
        "Is coffee bad for my heart?",
        "What are some healthy snacks for work?",
        "How much water should I drink a day?"
    ]
}

def run_tests():
    print("🚀 Starting Robust Bot Accuracy Tests...")
    print(f"Target: {API_URL}")
    
    # Get API Key
    api_key = input("\n🔑 Enter your API Key (from reset_key.py): ").strip()
    if not api_key:
        print("❌ API Key required!")
        return

    print("\n" + "="*60)
    
    total_questions = sum(len(qs) for qs in TEST_SCENARIOS.values())
    current_q = 0

    for category, questions in TEST_SCENARIOS.items():
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
                    json={"question": question, "session_id": "test_robust_1"},
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
    print("✅ All Tests Complete!")

if __name__ == "__main__":
    run_tests()
