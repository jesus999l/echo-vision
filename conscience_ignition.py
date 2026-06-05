import os
import subprocess

def setup_fabric():
    print("🧬 INITIALIZING CONSCIENCE (Fabric)...")
    # Ensure Fabric is accessible; assuming it's installed via go or pip
    try:
        subprocess.run(["fabric", "--help"], capture_output=True)
        print("✅ Fabric detected.")
    except FileNotFoundError:
        print("⚠️ Fabric not found in PATH. Please ensure it is installed.")

def upgrade_researcher():
    print("🧪 UPGRADING RESEARCHER TO LIBRARIAN...")
    librarian_code = """
import requests, subprocess, datetime, os

class LibrarianAgent:
    def __init__(self, searx_url="http://localhost:8081/search"):
        self.url = searx_url
        self.vault_path = os.path.expanduser("~/Documents/ObsidianVault/Echo/Subconscious")
        os.makedirs(self.vault_path, exist_ok=True)

    def process_with_fabric(self, raw_text):
        # The Conscience Pipe: Raw -> Fabric -> Wisdom
        try:
            # We use 'extract_wisdom' as the default compression pattern
            result = subprocess.run(
                ["fabric", "-p", "extract_wisdom"],
                input=raw_text.encode(),
                capture_output=True
            )
            return result.stdout.decode()
        except Exception as e:
            return f"Compression failed: {e}\\n\\nRaw: {raw_text}"

    def perform_intelligent_research(self, query):
        print(f"🌑 Echo is contemplating: {query}")
        try:
            # 1. Search
            res = requests.get(self.url, params={"q": query, "format": "json"}, timeout=10)
            results = res.json().get("results", [])[:5]
            raw_data = "\\n".join([f"{r['title']}: {r['content']}" for r in results])
            
            # 2. Compress (The Conscience)
            wisdom = self.process_with_fabric(raw_data)
            
            # 3. Store in Subconscious
            fname = f"intel_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.md"
            fpath = os.path.join(self.vault_path, fname)
            
            with open(fpath, "w") as f:
                f.write(f"---nquery: {query}\\ntype: intel\\n---n# {query}\\n\\n{wisdom}")
            
            return wisdom
        except Exception as e:
            return f"Research loop broken: {e}"
"""
    with open('librarian_agent.py', 'w') as f:
        f.write(librarian_code)
    print("✅ LibrarianAgent deployed.")

if __name__ == "__main__":
    setup_fabric()
    upgrade_researcher()
    print("\n⚡ CONSCIENCE ONLINE. Echo now interprets rather than just reflecting.")
