import ollama
from core.memory import EchoMemory

memory = EchoMemory("/home/jesus999l/Documents/ObsidianVault/Echo")

def classify_and_route(user_input):
    # 1. RECALL MEMORY
    related_notes = memory.search(user_input, k=3)
    context = "\n---\n".join(related_notes)

    # 2. BUILD CONTEXT-AWARE PROMPT
    prompt = f"""
You are Echo's Router.

Use the user's past memory to understand intent.

CONTEXT:
{context}

USER INPUT:
{user_input}

Classify into ONE:
BUILD, RESEARCH, MEMORY, CHAT

Respond ONLY with the category name.
"""

    # 3. CLASSIFY
    response = ollama.generate(
        model="qwen2.5:0.5b",
        prompt=prompt
    )

    return response["response"].strip()
