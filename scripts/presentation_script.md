# NutriChatbot — Presentation Script

> **Audience:** UiTM / hospital client, supervising dietitian, project stakeholders  
> **Duration:** ~20 minutes  
> **Setup before presenting:**  
> - Open `https://nutribot.computationalrd.com` in a browser (full screen)  
> - Have a terminal ready with the project folder open  
> - Run `python scripts/demo_extractor.py --reset --patient-id 4` once beforehand to confirm Ollama is live  
> - Increase terminal font size to 20pt+

---

## SECTION 1 — Opening (2 min)

**[No screen action yet. Face the audience.]**

> "Healthcare workers in Malaysia see dozens of patients every day. When a patient comes in for dietary counselling — maybe someone with diabetes and kidney disease — the dietitian needs to know their medications, restrictions, what they eat at home, whether they take their pills. That's a lot of context to gather, and a lot of advice to personalise.
>
> NutriChatbot is a system that gives that personalised dietary guidance 24/7 — through a chat interface — using the patient's own medical profile to shape every single answer. It understands Malaysian food, Bahasa Malaysia, and the specific dietary rules for cardiac, kidney, and diabetic patients.
>
> Let me show you how it works."

---

## SECTION 2 — Patient Login (3 min)

**[Switch to browser. Navigate to `https://nutribot.computationalrd.com`]**

> "This is the patient-facing interface. It's designed for clinic tablets or phones — no app to install, just a URL."

**[Type the name: `Mohd Hafizuddin`]**

> "The patient types their name. The system does a fuzzy search against the clinic's patient database."

**[When prompted for IC, type: `800512-14-6731`]**

> "To confirm identity, they enter their Malaysian IC number. No password to remember. The system auto-formats it as they type."

**[After login — point to the sidebar]**

> "Once logged in, look at the sidebar. This is automatically pulled from the clinic's patient record — his conditions, his medications, his dietary restrictions. The dietitian loaded this once; the patient never needs to type any of it."
>
> "Hafizuddin has Dyslipidaemia and Obesity Class I. He's on a statin. He eats mainly at roadside stalls — murtabak, roti canai. He smokes. This is all in his profile."

---

## SECTION 3 — Personalised Chat (5 min)

**[In the chat box, type:]**

> `What can I eat for breakfast?`

**[Wait for the response to stream. While it streams:]**

> "The system is retrieving clinical guidelines — Malaysian CPGs, WHO nutrition guidance — and combining them with Hafizuddin's profile. Watch how it responds."

**[After the response appears — point out specific elements:]**

> "Notice what it does. It names specific local foods — what to choose, what to avoid. It knows he should reduce saturated fat because of his dyslipidaemia. It knows he's Malay and suggests Halal-appropriate options. It's not generic advice — it's advice built around his exact conditions and his food culture."

**[Type a follow-up:]**

> `Is roti canai okay for me?`

> "Follow-up questions work too — it remembers the conversation context. It knows who he is, what we just discussed."

**[After response:]**

> "This is what makes it different from a general chatbot. A generic AI would say 'roti canai has carbohydrates and fat, eat in moderation.' This system says 'given your dyslipidaemia and obesity, the saturated fat from the ghee and the refined flour are specific concerns — here's what to watch for and what to substitute.'"

---

## SECTION 4 — Dynamic Data Collection (6 min)

**[Switch to terminal. Run:]**
```
python scripts/demo_extractor.py --reset --patient-id 4
```

> "Now I want to show you something that happens silently in the background during every conversation."
>
> "When the hospital registers a patient, they load the clinical data — conditions, medications, restrictions. But there's a lot the hospital doesn't know: how much water does the patient actually drink each day? Do they take their medication consistently? What cooking oils do they use at home? What type of exercise, if any?"
>
> "The system learns this automatically from chat. Every message the patient sends is analysed in the background, and if they mention something relevant, it's recorded into their profile."

**[The script shows the profile BEFORE — all empty. Press Enter to start.]**

> "Right now, Hafizuddin's supplementary fields are all empty — the hospital gave us the clinical data, but nothing about his daily habits."

**[First message runs — Malay, fluid intake. Wait for extraction. Press Enter.]**

> "His first message is in Bahasa Malaysia. He mentions he drinks about 6 glasses of water a day. The system sends that to the AI in the background — temperature zero, deterministic extraction — and it correctly converts 6 glasses to 1,500 mL and saves it."

**[Second message — medication compliance. Press Enter.]**

> "He mentions he sometimes forgets his evening blood pressure pill. The system classifies this as 'variable' compliance — not poor, not good — and saves it. A dietitian reviewing his profile tomorrow will see this without the patient ever having filled in a form."

**[Third message — fat intake + sources. Press Enter.]**

> "He says he fries everything in palm oil every day. Two fields extracted: fat intake level is 'high', and the source is palm oil. Relevant for his dyslipidaemia."

**[Fourth message — religion, alcohol, tobacco. Press Enter.]**

> "He mentions he's Muslim and doesn't drink or smoke. Three fields in one sentence — religion, zero alcohol per week, and tobacco status 'never smoked'. The system doesn't repeat itself — once a field is filled, it's never re-extracted."

**[Fifth message — activity. Press Enter.]**

> "Finally, he describes his exercise in Malay. The system extracts frequency, duration, activity type, and intensity — all from one natural sentence."

**[Profile AFTER appears.]**

> "From five natural messages — mixed Malay and English — we went from a profile with no lifestyle data to one with nine fields filled. None of it required the patient to answer a questionnaire. It happened during a normal conversation."

---

## SECTION 5 — Architecture (2 min)

**[Switch to browser or terminal. Optional — only for technical audience.]**

> "Briefly on the technical side:"
>
> "The system runs on two machines. The FastAPI server and database are on our server here in the lab. The AI models — the primary language model and the orchestration model — run on a separate Mac Studio with a 96GB chip. They're connected over private Cloudflare tunnels."
>
> "The knowledge base is 58 clinical PDFs — Malaysian clinical practice guidelines, WHO nutrition guidance, international cardiac and kidney nutrition standards — about 24,000 chunks stored in a vector database. Every query retrieves the most relevant passages and combines them with the patient's profile before generating an answer."
>
> "Multi-tenant: if another clinic or hospital joins, they get their own isolated knowledge base. Their patients and documents are completely separate. One deployment, multiple clients."

---

## SECTION 6 — What's Built, What's Next (2 min)

**[Face the audience. No screen action needed.]**

> "What's live today:"
> - Patient login with IC verification
> - Personalised chat in English and Bahasa Malaysia
> - Multi-tenant knowledge base with 58 clinical documents
> - Dynamic profile collection — 13 supplementary fields, running silently in background
> - Personalization levels — L0 to L3 — so advice is calibrated to how serious the patient's condition is
> - API-first — any front-end can connect, including WhatsApp

> "What's coming:"
> - WhatsApp delivery — patients chat on the platform they already use
> - Conversation history persistence — so the bot remembers across sessions and restarts
> - Hospital API integration — when the hospital system is ready, patient records sync directly instead of being seeded manually

> "The foundation is production-ready. The architecture is designed so that swapping from a local database to the hospital's system is a one-line change."

---

## TALKING POINTS — If Asked

**Q: Is patient data safe?**
> "Patient data in production will live on the hospital's own server. The bot connects to it via API. The AI models never store or log patient data — they process a request and return a response."

**Q: What if the AI gives wrong advice?**
> "The system retrieves from vetted clinical documents — it cannot fabricate guidelines that aren't in the knowledge base. For high-risk patients like post-surgery cardiac patients, the personalization level (L3) restricts the system to recommending medical supervision only."

**Q: Can it handle Malay fully?**
> "The embedding model (bge-m3) natively handles Bahasa Malaysia and English in the same query. The extraction model understands mixed Malay-English (Manglish). Clinical documents in Malay are ingested with Malay-language OCR."

**Q: What does it cost per patient?**
> "Running locally on hardware you own: near zero per query once set up. The only ongoing cost is the server. There's no per-request API fee because the models run on your hardware."

---

## EMERGENCY FALLBACK — If Live Demo Breaks

If `nutribot.computationalrd.com` is down (Cloudflare timeout, model cold-start):

1. Run the extractor demo standalone — it only needs the local DB and Ollama:
   ```
   python scripts/demo_extractor.py --reset --patient-id 4
   ```
2. Show the ARCHITECTURE.md in the browser or a text editor — section 7.5 has the full extractor diagram.
3. Explain that the first request after idle takes ~60s (model warm-up); subsequent requests are 10-30s.

---

*Script version: May 2026 | Prepared by: Lee Yean Han*
