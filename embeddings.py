import os

# Suppress Keras 3 / TensorFlow backend conflict in the transformers library.
# This project uses PyTorch via sentence-transformers; TF is not needed.
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from langchain_community.embeddings import HuggingFaceEmbeddings

# BAAI/bge-small-en-v1.5: 33M params, 130MB, 512-token context, SOTA for its size
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")

# Module-level singleton — loaded once, reused on every request
_embedding_function = None


def get_embedding_function() -> HuggingFaceEmbeddings:
    global _embedding_function
    if _embedding_function is None:
        print(f"Loading embedding model: {EMBEDDING_MODEL_NAME}")
        _embedding_function = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL_NAME,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        print("Embedding model loaded.")
    return _embedding_function
