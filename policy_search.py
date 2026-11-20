from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Sequence

from fastembed import TextEmbedding


MODEL_NAME = "BAAI/bge-small-en-v1.5"
MIN_RELEVANCE_SCORE = 0.65
MIN_SEMANTIC_WITH_KEYWORDS = 0.35
MIN_KEYWORD_OVERLAP = 2
WORD_ALIASES = {
    "returns": "return", "returned": "return", "refunds": "refund", "refunded": "refund",
    "opened": "open", "defective": "defect", "defects": "defect", "flickering": "flicker",
    "damaged": "damage", "accessories": "accessory", "days": "day", "back": "return",
    "send": "return", "mail": "return", "packages": "package", "parcels": "parcel",
    "arrived": "arrive", "arrival": "arrive", "delivered": "delivery",
    "shipping": "ship", "shipped": "ship", "ships": "ship", "shipment": "ship", "shipments": "ship",
    "cancellation": "cancel", "cancellations": "cancel", "cancelled": "cancel", "cancelling": "cancel",
    "changes": "change", "addresses": "address", "receipts": "receipt", "invoices": "invoice",
    "charges": "charge", "charged": "charge", "batteries": "battery", "chargers": "charger",
    "troubleshooting": "troubleshoot",
    "water": "liquid", "scratch": "cosmetic", "swollen": "battery",
    "apart": "modify", "courier": "carrier", "postage": "shipping",
    "blinking": "flicker", "scanned": "scan", "scans": "scan",
}
QUERY_EXPANSIONS = {
    "water": "liquid ingress",
    "scratch": "cosmetic wear",
    "swollen": "swollen battery safety",
    "apart": "open modify product",
    "postage": "return shipping label",
    "box": "return accessories proof of purchase",
    "money": "refund return payment",
    "courier": "carrier tracking parcel",
    "warehouse": "fulfillment packed dispatch",
    "unsealed": "opened product return",
    "blinking": "flickering display",
    "protection": "limited warranty one year delivery date",
    "cancellation": "order cancellation before fulfillment",
    "cancel": "order cancellation before fulfillment",
    "defective": "defective product return refund replacement",
}


def _normalize(vector: Sequence[float]) -> tuple[float, ...]:
    values = tuple(float(value) for value in vector)
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0:
        raise ValueError("The embedding model returned a zero-length vector.")
    return tuple(value / norm for value in values)


class PolicyRetriever:
    def __init__(
        self,
        policies: Sequence[dict[str, Any]],
        model: TextEmbedding | None = None,
    ) -> None:
        if not policies:
            raise ValueError("PolicyRetriever requires at least one policy passage.")

        self._policies = list(policies)
        if model is None:
            cache_dir = Path.home() / ".cache" / "fastembed"
            model = TextEmbedding(model_name=MODEL_NAME, cache_dir=str(cache_dir))
        self._model = model
        passages = [
            f'{policy["title"]}. Topics: {", ".join(sorted(policy["terms"]))}. {policy["text"]}'
            for policy in self._policies
        ]
        self._embeddings = [
            _normalize(vector)
            for vector in self._model.embed(passages)
        ]
        if len(self._embeddings) != len(self._policies):
            raise RuntimeError("The embedding model did not return one vector per policy passage.")

    def search(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        if not query.strip() or limit <= 0:
            return []

        query_words = re.findall(r"[a-z0-9]+", query.lower())
        expansions = {
            QUERY_EXPANSIONS[word]
            for word in query_words
            if word in QUERY_EXPANSIONS
        }
        semantic_query = " ".join([query, *sorted(expansions)])
        query_embedding = next(self._model.embed([semantic_query]), None)
        if query_embedding is None:
            raise RuntimeError("The embedding model returned no vector for the policy query.")
        normalized_query = _normalize(query_embedding)
        words = {
            WORD_ALIASES.get(word, word)
            for word in re.findall(r"[a-z0-9]+", semantic_query.lower())
        }

        scored = []
        for policy, embedding in zip(self._policies, self._embeddings):
            semantic_score = sum(left * right for left, right in zip(normalized_query, embedding))
            terms = {
                WORD_ALIASES.get(term, term)
                for term in policy["terms"]
            }
            lexical_score = len(words & terms)
            score = semantic_score + min(lexical_score, 4) * 0.08
            if (
                semantic_score >= MIN_RELEVANCE_SCORE
                or (
                    lexical_score >= MIN_KEYWORD_OVERLAP
                    and semantic_score >= MIN_SEMANTIC_WITH_KEYWORDS
                )
            ):
                scored.append((score, semantic_score, policy))

        scored.sort(key=lambda result: result[0], reverse=True)
        return [
            {
                "title": policy["title"],
                "citation": f'{policy["section"]}, p. {policy["page"]}',
                "excerpt": policy["text"],
                "score": round(semantic_score, 4),
            }
            for _, semantic_score, policy in scored[:limit]
        ]
