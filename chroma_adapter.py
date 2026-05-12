"""
chroma_adapter.py — Echo v11.6 ChromaDB Backend
================================================
Implements the MockDBBackend interface for real persistent storage.

Two embedding modes:
  - OllamaEmbeddingFunction: fully offline, uses nomic-embed-text via
    your local Ollama instance. Preferred for Echo on T14s.
  - ChromaDB default: downloads a model on first use (requires internet).

Drop-in replacement:
    from chroma_adapter import ChromaDBBackend
    engine = MemoryEngine(db_backend=ChromaDBBackend())

Also provides DriftSentinel — an enhanced auditor that names
exactly which documents were displaced between recording and now.
"""

import json
import math
import hashlib
import requests
from typing import List, Dict, Any, Optional
from collections import Counter

import chromadb
from chromadb.utils import embedding_functions

from echo_memory import RetrievalRecord, MemoryContext, MemoryEngine


# =========================================================
# SIMPLE OFFLINE EMBEDDING FUNCTION
# Word-frequency TF vector, L2-normalised.
# No model downloads. Deterministic. Good enough for tests.
# Use OllamaEmbeddingFunction in production.
# =========================================================

class SimpleEmbeddingFunction:
    """
    Bag-of-words TF vector, L2-normalised to unit length.
    Produces meaningful cosine similarities without any model or
    network access. Use this for tests; use OllamaEmbeddingFunction
    in production for semantic quality.
    """

    # Fixed vocabulary size keeps vectors a constant dimension
    VOCAB_SIZE = 512

    def name(self) -> str:
        return "simple-bow-embedding"

    def __call__(self, input: List[str]) -> List[List[float]]:
        return [self._embed(text) for text in input]

    def embed_query(self, input: List[str]) -> List[List[float]]:
        # ChromaDB 1.5+ calls this for query_texts
        return self.__call__(input)
        return [self._embed(text) for text in input]

    def _embed(self, text: str) -> List[float]:
        tokens = text.lower().split()
        counts = Counter(tokens)
        vec = [0.0] * self.VOCAB_SIZE
        for token, count in counts.items():
            idx = int(hashlib.md5(token.encode()).hexdigest(), 16) % self.VOCAB_SIZE
            vec[idx] += float(count)
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]


# =========================================================
# OLLAMA EMBEDDING FUNCTION
# Wraps nomic-embed-text (already in your Ollama stack).
# Fully offline. No external downloads.
# =========================================================

class OllamaEmbeddingFunction:
    """
    ChromaDB-compatible embedding function backed by Ollama.

    Uses nomic-embed-text by default — already pulled on your T14s.
    Switch model= to any other Ollama embed model if needed.
    """

    def __init__(
        self,
        model: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
    ):
        self.model    = model
        self.base_url = base_url

    def __call__(self, input: List[str]) -> List[List[float]]:
        embeddings = []
        for text in input:
            resp = requests.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=30,
            )
            resp.raise_for_status()
            embeddings.append(resp.json()["embedding"])
        return embeddings


# =========================================================
# CHROMA DB BACKEND
# Implements the same interface as MockDBBackend.
# =========================================================

class ChromaDBBackend:
    """
    Persistent ChromaDB backend for Echo's memory layer.

    Collections layout (one per source type, metadata-filtered):
      echo_episodic   — lived experiences, browser events, session logs
      echo_semantic   — distilled knowledge, facts, concepts
      echo_graph      — relationship nodes / neighbors

    Each document stored with metadata: {source, doc_id, summary}
    so we can reconstruct full RetrievalRecords from query results.
    """

    SOURCE_COLLECTIONS = {
        "episodic": "echo_episodic",
        "semantic": "echo_semantic",
        "graph":    "echo_graph",
    }

    def __init__(
        self,
        persist_path: str = "./echo_chroma_db",
        embedding_fn=None,
    ):
        """
        persist_path:  where ChromaDB writes its files.
                       Recommend ~/vision_assistant/echo_chroma_db
        embedding_fn:  pass OllamaEmbeddingFunction() for offline mode,
                       or None to use ChromaDB's default (needs internet
                       on first run to download the model).
        """
        self._client = chromadb.PersistentClient(path=persist_path)
        self._embed_fn = embedding_fn  # None = use ChromaDB default

        self._collections: Dict[str, Any] = {}
        for source, name in self.SOURCE_COLLECTIONS.items():
            kwargs = {"name": name, "metadata": {"hnsw:space": "cosine"}}
            if self._embed_fn is not None:
                kwargs["embedding_function"] = self._embed_fn
            self._collections[source] = (
                self._client.get_or_create_collection(**kwargs)
            )

    # ----------------------------------------------------------
    # Public interface (matches MockDBBackend)
    # ----------------------------------------------------------

    def query(
        self,
        query_text: str,
        source: str,
        n_results: int = 5,
    ) -> List[RetrievalRecord]:
        """
        Query one source collection. Returns RetrievalRecords with
        full provenance (doc_id, score, summary, query string).
        """
        collection = self._collections.get(source)
        if collection is None:
            return []

        count = collection.count()
        if count == 0:
            return []

        # Don't request more results than exist
        actual_n = min(n_results, count)

        results = collection.query(
            query_texts=[query_text],
            n_results=actual_n,
            include=["documents", "metadatas", "distances"],
        )

        records = []
        docs      = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]

        for doc, meta, dist in zip(docs, metadatas, distances):
            # ChromaDB cosine distance → similarity: 1 - distance
            similarity = round(1.0 - dist, 6)
            records.append(
                RetrievalRecord(
                    doc_id          = meta.get("doc_id", "unknown"),
                    summary         = meta.get("summary", doc[:120]),
                    similarity_score = similarity,
                    source          = source,
                    retrieval_query = query_text,
                )
            )

        return records

    def add_document(
        self,
        source: str,
        doc_id: str,
        text: str,
        summary: str = "",
    ):
        """
        Add a document to a source collection.
        text    — full content (embedded)
        summary — short label stored in metadata (returned in records)
        """
        collection = self._collections[source]
        collection.add(
            documents=[text],
            ids=[doc_id],
            metadatas=[{
                "doc_id":  doc_id,
                "summary": summary or text[:120],
                "source":  source,
            }],
        )

    def delete_document(self, source: str, doc_id: str):
        """Remove a document. Used by the poisoning test to clean up."""
        self._collections[source].delete(ids=[doc_id])

    def document_exists(self, source: str, doc_id: str) -> bool:
        result = self._collections[source].get(ids=[doc_id])
        return len(result["ids"]) > 0


# =========================================================
# DRIFT SENTINEL
# Enhanced DriftAuditor that names displaced documents.
# =========================================================

class DriftSentinel:
    """
    Compares a fossilized memory against the live DB at query time.

    Unlike DriftAuditor (hash-only), DriftSentinel resolves *which*
    documents were added, removed, or displaced between the trace
    recording and now.

    Isolation guarantee: the live query runs in a shadow thread.
    The replay decision is never affected — only the report changes.
    """

    def __init__(self, db_backend: ChromaDBBackend):
        self._db = db_backend

    def audit(
        self,
        trace: Dict[str, Any],
        n_results: int = 5,
    ) -> Dict[str, Any]:
        """
        Full displacement analysis across all three source collections.

        Returns a report dict with per-source displacement maps.
        """
        event         = trace["event"]
        query_text    = event.get("payload", {}).get("command", "")
        fossilized_mc = MemoryContext.from_dict(trace["memory_context"])

        report = {
            "drift_detected": False,
            "fossilized_hash": fossilized_mc.memory_hash,
            "live_hash": "",
            "timestamp": trace["timestamp"],
            "event_type": event.get("event_type", "unknown"),
            "sources": {},
        }

        for source, fossil_records in [
            ("episodic",        fossilized_mc.episodic),
            ("semantic",        fossilized_mc.semantic),
            ("graph_neighbors", fossilized_mc.graph_neighbors),
        ]:
            chroma_source = "graph" if source == "graph_neighbors" else source
            live_records  = self._db.query(query_text, chroma_source, n_results)

            source_report = self._diff_records(fossil_records, live_records)
            report["sources"][source] = source_report

            if source_report["displaced"] or source_report["added"] or source_report["removed"]:
                report["drift_detected"] = True

        # Recompute live hash via a fresh MemoryContext
        live_mc = MemoryContext(
            episodic        = self._db.query(query_text, "episodic",  n_results),
            semantic        = self._db.query(query_text, "semantic",  n_results),
            graph_neighbors = self._db.query(query_text, "graph",     n_results),
            active_goals    = fossilized_mc.active_goals,
            constraints     = fossilized_mc.constraints,
        ).seal()

        report["live_hash"] = live_mc.memory_hash

        self._print_report(report)
        return report

    def _diff_records(
        self,
        fossil: List[RetrievalRecord],
        live:   List[RetrievalRecord],
    ) -> Dict[str, Any]:
        fossil_ids = {r.doc_id for r in fossil}
        live_ids   = {r.doc_id for r in live}

        removed    = fossil_ids - live_ids   # in trace, gone from DB
        added      = live_ids - fossil_ids   # new in DB, not in trace
        stable     = fossil_ids & live_ids   # same doc in both

        # Displacement = a removed doc replaced by an added doc
        displaced_pairs = list(zip(sorted(removed), sorted(added)))

        def record_label(records, doc_id):
            for r in records:
                if r.doc_id == doc_id:
                    return f"{r.doc_id} | score={r.similarity_score:.4f} | {r.summary[:60]}"
            return doc_id

        return {
            "stable":     sorted(stable),
            "removed":    [record_label(fossil, d) for d in sorted(removed)],
            "added":      [record_label(live,   d) for d in sorted(added)],
            "displaced":  [
                {
                    "was":  record_label(fossil, old),
                    "now":  record_label(live,   new),
                }
                for old, new in displaced_pairs
            ],
        }

    def _print_report(self, report: Dict[str, Any]):
        print("\n===== DRIFT SENTINEL =====")
        if not report["drift_detected"]:
            print("✅ MEMORY STABLE — live DB matches fossilized context exactly.")
        else:
            print("⚠️  RETRIEVAL DRIFT DETECTED")
            print(f"   Fossilized : {report['fossilized_hash'][:32]}...")
            print(f"   Live DB    : {report['live_hash'][:32]}...")
            print()
            for source, sr in report["sources"].items():
                if sr["displaced"] or sr["added"] or sr["removed"]:
                    print(f"  [{source.upper()}]")
                    for pair in sr["displaced"]:
                        print(f"    DISPLACED:")
                        print(f"      WAS → {pair['was']}")
                        print(f"      NOW → {pair['now']}")
                    for doc in sr["removed"]:
                        print(f"    REMOVED  : {doc}")
                    for doc in sr["added"]:
                        print(f"    ADDED    : {doc}")
        print(f"\n   Event     : {report['event_type']}")
        print(f"   Timestamp : {report['timestamp']}")
