from core.memory import EchoMemory

memory = EchoMemory("/home/jesus999l/Documents/ObsidianVault/Echo")

print("Indexing vault...")
memory.ingest_vault()

print("\nQuerying memory...\n")
results = memory.search("What have I worked on recently?")

for i, r in enumerate(results):
    print(f"\n--- Result {i+1} ---\n")
    print(r[:500])
