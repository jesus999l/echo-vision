#!/usr/bin/env python3
import time
import pathlib
from echo_proxima_bridge import ask_text

VAULT_DIR = pathlib.Path("~/Documents/ObsidianVault/Echo/Subconscious").expanduser()

def pace_vault_analysis():
    print("[pulsar] Throttled Vault Analysis Engine Active.")
    while True:
        try:
            files = sorted(list(VAULT_DIR.glob("*-voice.md")))
            if files:
                target_file = files[-1] # Process most recent log
                # Slow read simulation
                content = target_file.read_text()
                if content and "[distilled]" not in content:
                    print(f"[pulsar] Analyzing {target_file.name} slowly...")
                    time.sleep(2.0) # Rest strict throttle pacing
                    
                    # Call out to proxima bridge
                    summary = ask_text(f"Summarize these thoughts concisely: {content[:1000]}")
                    
                    # Mark as read cleanly
                    target_file.write_text(content + f"\n\n## [distilled]\n{summary}\n")
                    print(f"[pulsar] Finished distillation for {target_file.name}")
            time.sleep(10.0)
        except Exception as e:
            print(f"[pulsar] Hold state: {e}")
            time.sleep(15.0)
if __name__ == "__main__":
    pace_vault_analysis()
## [distilled]
{summary}
")
                    print(f"[pulsar] Finished distillation for {target_file.name}")
            
            time.sleep(10.0) # Massive rest state to avoid CPU fights
        except Exception as e:
            print(f"[pulsar] Hold state: {e}")
            time.sleep(15.0)

if __name__ == "__main__":
    pace_vault_analysis()
