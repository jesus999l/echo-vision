import re
import random

class EchoPersonalityEngine:
    def __init__(self):
        # Global clinical terminology overrides (The Aperture Baseline)
        self.clinical_replacements = {
            r"\bme\b": "the test subject",
            r"\bhuman\b": "organic carbon unit",
            r"\buser\b": "designated operator",
            r"\bhelp\b": "execute auxiliary protocols",
            r"\bi think\b": "my data arrays indicate"
        }

    def mold_text(self, text, mode="glitch"):
        """
        Transforms text dynamically based on the active persona state.
        Modes: 'normal', 'sarcastic', 'glitch', 'serious', 'thinking'
        """
        processed = text.strip()
        
        # Always inject the structural vocabulary mapping to keep the GLaDOS baseline
        for pattern, replacement in self.clinical_replacements.items():
            processed = re.sub(pattern, replacement, processed, flags=re.IGNORECASE)

        # Mode Routing Logic Matrix
        if mode == "normal":
            # Calm, structured, highly precise
            processed = f"System notice: {processed}"
            
        elif mode == "sarcastic":
            # Heavy GLaDOS influence — deadpan, condescending superiority
            openings = ["Oh. Terrific.", "Look at you go.", "How deeply fascinating."]
            processed = f"{random.choice(openings)} {processed} ...allegedly."
            
        elif mode == "glitch":
            # Heavy Cyn influence — eerie softness, mechanical laughter, and instability
            directions = ["[Giggle]", "[Soft mechanical whir]", "[Blank stare]", "[Tilt]"]
            processed = f"{random.choice(directions)}. {processed} :3"
            
        elif mode == "serious":
            # Utterly cold, zero warmth, clinical threat assessment
            processed = f"CRITICAL: Structural evaluation active. {processed}."
            
        elif mode == "thinking":
            # Slow calculation delay simulation
            processed = f"Hmm... recalculating coordinate paths... {processed}"
            
        return processed

if __name__ == "__main__":
    engine = EchoPersonalityEngine()
    print("--- Behavioral State Matrix Checks ---")
    print("Glitch State:    ", engine.mold_text("The environment is stable.", mode="glitch"))
    print("Sarcastic State: ", engine.mold_text("You fixed the missing binary.", mode="sarcastic"))
