import os
import chromadb
from chromadb.utils import embedding_functions

class EchoMemory:
    def __init__(self, vault_path):
        self.vault_path = os.path.expanduser(vault_path)

        self.client = chromadb.Client()

        self.embedder = embedding_functions.OllamaEmbeddingFunction(
            model_name="nomic-embed-text"
        )

        self.collection = self.client.get_or_create_collection(
            name="echo_memory",
            embedding_function=self.embedder
        )

    def ingest_vault(self):
        print("Indexing vault...")

        for root, _, files in os.walk(self.vault_path):
            for file in files:
                if file.endswith(".md"):
                    path = os.path.join(root, file)

                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()

                    self.collection.add(
                        documents=[content],
                        ids=[path]
                    )

    def search(self, query, k=3):
        results = self.collection.query(
            query_texts=[query],
            n_results=k
        )

        return results["documents"][0]
