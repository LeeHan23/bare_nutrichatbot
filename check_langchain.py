try:
    import langchain
    print(f"LangChain version: {langchain.__version__}")
    
    try:
        from langchain.chains import ConversationalRetrievalChain
        print("✅ Found ConversationalRetrievalChain in langchain.chains")
    except ImportError as e:
        print(f"❌ Failed to import from langchain.chains: {e}")
        
    try:
        from langchain.chains.conversational_retrieval.base import ConversationalRetrievalChain
        print("✅ Found ConversationalRetrievalChain in langchain.chains.conversational_retrieval.base")
    except ImportError as e:
        print(f"❌ Failed to import from langchain.chains.conversational_retrieval.base: {e}")

except ImportError as e:
    print(f"❌ Failed to import langchain: {e}")
