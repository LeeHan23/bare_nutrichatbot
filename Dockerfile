# Match the host .venv's Python version (3.13) exactly. Building on 3.11 sent
# pip's resolver into 200k+ backtracking rounds trying to satisfy
# unstructured[pdf,docx]'s extras tree against the pinned langchain versions,
# and separately, scikit-network (a ragas dependency) only ships a prebuilt
# wheel for cp313 — on 3.11 pip fell back to building from source, which
# hits scikit-network's legacy setup.py hardcoding numpy==1.20.0 (incompatible
# with 3.11 anyway). Pinning to the exact host-proven versions on the same
# Python version sidesteps both problems entirely.
FROM python:3.13-slim

# Install system dependencies needed for libmagic
RUN apt-get update && apt-get install -y libmagic1 poppler-utils libreoffice \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# deploy/requirements.lock.txt is `pip freeze` from the host .venv — a flat
# list of every package (incl. transitive deps) already proven to work
# together in production. --no-deps skips pip's constraint resolver (which
# rejects it on paper: langchain 0.1.20 declares numpy<2, but numpy 2.4.6 is
# what's actually installed and working) and just installs exactly this set.
COPY deploy/requirements.lock.txt .
RUN pip install --no-cache-dir --no-deps -r requirements.lock.txt

# Copy the rest of the application's code into the container
COPY . .

# Copy data to a seed directory (so we can populate the persistent volume if empty)
COPY data /app/data_seed

# Default command runs the patient chat bot (app:app). docker-compose.yml
# overrides this for the docs_api service (docs_api:app, no patient DB access).
CMD gunicorn -w 1 -k uvicorn.workers.UvicornWorker app:app --bind 0.0.0.0:$PORT
