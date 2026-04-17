# load sentence transformer model

from sentence_transformers import SentenceTransformer

SentenceTransformer("all-MiniLM-L6-v2").save("./models/all-MiniLM-L6-v2")
