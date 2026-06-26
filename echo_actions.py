
import re, subprocess, sys
from pathlib import Path

SEARCH_ENGINES = {
    'brave':      'https://search.brave.com/search?q={}',
    'google':     'https://www.google.com/search?q={}',
    'duckduckgo': 'https://duckduckgo.com/?q={}',
    'ddg':        'https://duckduckgo.com/?q={}',
    'bing':       'https://www.bing.com/search?q={}',
    'perplexity': 'https://www.perplexity.ai/search?q={}',
    'startpage':  'https://www.startpage.com/search?q={}',
}

CONFIG_FILE = Path('/home/jesus999l/.config/driftwm/echo_actions.conf')

def get_search_engine():
    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text().splitlines():
            if line.startswith('search_engine='):
                return line.split('=', 1)[1].strip()
    return 'brave'

PATTERNS = [
    (r'\bsearch\s+(?:for\s+)?(.+)', 'search'),
    (r'\bopen\s+(.+)',              'open'),
    (r'\bplay\s+(.+)',              'play'),
    (r'\blaunch\s+(.+)',            'open'),
]

def extract_action(text):
    t = text.strip().rstrip('.!?')
    for pattern, verb in PATTERNS:
        m = re.search(pattern, t, re.IGNORECASE)
        if m:
            return verb, m.group(1).strip()
    return None

def dispatch(verb, target):
    try:
        if verb == 'search':
            engine = get_search_engine()
            template = SEARCH_ENGINES.get(engine, SEARCH_ENGINES['brave'])
            url = template.format(target.replace(' ', '+'))
            subprocess.Popen(['xdg-open', url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Searching {engine} for {target}."
        elif verb == 'open':
            result = subprocess.run(['which', target.lower().split()[0]], capture_output=True, text=True)
            if result.returncode == 0:
                subprocess.Popen([target.lower().split()[0]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(['xdg-open', target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Opening {target}."
        elif verb == 'play':
            result = subprocess.run(['playerctl', 'play-pause'], capture_output=True, text=True)
            if result.returncode != 0:
                subprocess.Popen(['mpv', '--no-video', target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Playing {target}."
    except Exception as e:
        return f"Action failed: {e}"
    return "Done."

if __name__ == '__main__':
    text = ' '.join(sys.argv[1:])
    action = extract_action(text)
    if action:
        verb, target = action
        print(f"[ACTION] {verb}: {target}")
        print(dispatch(verb, target))
    else:
        print("No action detected.")
