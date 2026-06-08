"""
Patch: task priority (high/normal/low) + AI guidelines in settings.
Run: /home/jesus999l/vision_env/bin/python3 ~/vision_assistant/patch_priority_guidelines.py
"""
import subprocess

UI  = "/home/jesus999l/vision_assistant/ui.py"
MEM = "/home/jesus999l/vision_assistant/memory.py"

ui_src  = open(UI).read()
mem_src = open(MEM).read()

# ─────────────────────────────────────────────────────────────────────────────
# PART 1 — memory.py: add priority column to goals schema + add_goal
# ─────────────────────────────────────────────────────────────────────────────
old_schema = '''        CREATE TABLE IF NOT EXISTS goals ('''
# Find the full CREATE TABLE goals block
import re
m = re.search(r'(        CREATE TABLE IF NOT EXISTS goals \([^)]+\))', mem_src, re.DOTALL)
if m:
    block = m.group(1)
    if "priority" not in block:
        new_block = block.rstrip(')') + ',\n            priority    TEXT DEFAULT \'normal\'\n        )'
        mem_src = mem_src.replace(block, new_block)
        print("OK: priority column in schema")
    else:
        print("SKIP: priority already in schema")
else:
    print("FAIL: goals schema not found")

# Add priority to add_goal
old_add = '''def add_goal(title, description="", category="personal", target_date=None):'''
new_add = '''def add_goal(title, description="", category="personal", target_date=None, priority="normal"):'''
if old_add in mem_src:
    mem_src = mem_src.replace(old_add, new_add)
    print("OK: add_goal signature")
else:
    print("FAIL: add_goal signature")

old_insert = '''        "INSERT INTO goals (title,description,category,target_date,created_at) VALUES (?,?,?,?,?)",
        (title, description, category, target_date, now)'''
new_insert = '''        "INSERT INTO goals (title,description,category,target_date,created_at,priority) VALUES (?,?,?,?,?,?)",
        (title, description, category, target_date, now, priority)'''
if old_insert in mem_src:
    mem_src = mem_src.replace(old_insert, new_insert)
    print("OK: add_goal insert")
else:
    print("FAIL: add_goal insert")

# Also add ALTER TABLE migration for existing DBs
old_init = '''        CREATE TABLE IF NOT EXISTS goals ('''
if "ALTER TABLE goals ADD COLUMN priority" not in mem_src:
    # Find a good place after the CREATE TABLE goals block to add migration
    migrate = '''        CREATE TABLE IF NOT EXISTS goals ('''
    after_create = mem_src.find(migrate)
    # Find end of that schema block
    end_idx = mem_src.find("conn.commit()", after_create)
    if end_idx > 0:
        old_commit = "conn.commit()"
        inject = '''        try:
            conn.execute("ALTER TABLE goals ADD COLUMN priority TEXT DEFAULT 'normal'")
        except: pass
        conn.commit()'''
        # Only replace the first occurrence after goals table
        mem_src = mem_src[:end_idx] + inject + mem_src[end_idx + len("conn.commit()"):]
        print("OK: priority migration")
    else:
        print("FAIL: migration insertion point")

open(MEM, "w").write(mem_src)

# ─────────────────────────────────────────────────────────────────────────────
# PART 2 — ui.py: add priority dropdown to new task form
# ─────────────────────────────────────────────────────────────────────────────
old_row2 = '''        row2=tk.Frame(af,bg=BG3); row2.pack(fill="x",pady=(0,6))
        # Due date
        tk.Label(row2,text="Due:",bg=BG3,fg=TEXT3,font=FONT_TINY).pack(side="left")
        due_entry=tk.Entry(row2,bg=BG2,fg=TEXT,insertbackground=ACCENT,relief="flat",
                           font=FONT_TINY,width=10,
                           highlightthickness=1,highlightbackground=BORDER)
        due_entry.pack(side="left",padx=4,ipady=3)
        due_entry.insert(0,"YYYY-MM-DD")
        due_entry.bind("<FocusIn>",lambda e:(due_entry.delete(0,"end") if due_entry.get()=="YYYY-MM-DD" else None))
        def add_task():
            t=entry.get().strip()
            if t:
                import datetime as _dt
                due=None
                try:
                    due_str=due_entry.get().strip()
                    if due_str and due_str!="YYYY-MM-DD":
                        due=_dt.datetime.strptime(due_str,"%Y-%m-%d").timestamp()
                except: pass
                add_goal(t,category=cat_var.get(),target_date=due)
                entry.delete(0,"end")
                self.open_page("tasks")'''

new_row2 = '''        row2=tk.Frame(af,bg=BG3); row2.pack(fill="x",pady=(0,4))
        # Due date
        tk.Label(row2,text="Due:",bg=BG3,fg=TEXT3,font=FONT_TINY).pack(side="left")
        due_entry=tk.Entry(row2,bg=BG2,fg=TEXT,insertbackground=ACCENT,relief="flat",
                           font=FONT_TINY,width=10,
                           highlightthickness=1,highlightbackground=BORDER)
        due_entry.pack(side="left",padx=4,ipady=3)
        due_entry.insert(0,"YYYY-MM-DD")
        due_entry.bind("<FocusIn>",lambda e:(due_entry.delete(0,"end") if due_entry.get()=="YYYY-MM-DD" else None))
        # Priority
        row3=tk.Frame(af,bg=BG3); row3.pack(fill="x",pady=(0,6))
        tk.Label(row3,text="Priority:",bg=BG3,fg=TEXT3,font=FONT_TINY).pack(side="left")
        pri_var=tk.StringVar(value="normal")
        pri_colors={"high":DANGER,"normal":TEXT3,"low":ACCENT3}
        for val,lbl in [("high","🔴 High"),("normal","🟡 Normal"),("low","🟢 Low")]:
            tk.Radiobutton(row3,text=lbl,variable=pri_var,value=val,
                           bg=BG3,fg=TEXT,selectcolor=BG2,activebackground=BG3,
                           font=FONT_TINY,highlightthickness=0,cursor="hand2").pack(side="left",padx=4)
        def add_task():
            t=entry.get().strip()
            if t:
                import datetime as _dt
                due=None
                try:
                    due_str=due_entry.get().strip()
                    if due_str and due_str!="YYYY-MM-DD":
                        due=_dt.datetime.strptime(due_str,"%Y-%m-%d").timestamp()
                except: pass
                add_goal(t,category=cat_var.get(),target_date=due,priority=pri_var.get())
                entry.delete(0,"end")
                self.open_page("tasks")'''

if old_row2 in ui_src:
    ui_src = ui_src.replace(old_row2, new_row2)
    print("OK: priority form row")
else:
    print("FAIL: task form not found")

# ─────────────────────────────────────────────────────────────────────────────
# PART 3 — ui.py: show priority badge + sort by priority in task card/list
# ─────────────────────────────────────────────────────────────────────────────
old_sort = '''        for label,key,color in sections:
            items=buckets[key]
            if not items: continue
            tk.Label(inner,text=label,bg=BG2,fg=color,
                     font=("Segoe UI",7,"bold"),padx=10).pack(anchor="w",pady=(8,2))
            for g in items: self._goal_card(inner,g,color)'''

new_sort = '''        _PRI_ORDER = {"high": 0, "normal": 1, "low": 2}
        for label,key,color in sections:
            items=buckets[key]
            if not items: continue
            items = sorted(items, key=lambda g: _PRI_ORDER.get(g.get("priority","normal"), 1))
            tk.Label(inner,text=label,bg=BG2,fg=color,
                     font=("Segoe UI",7,"bold"),padx=10).pack(anchor="w",pady=(8,2))
            for g in items: self._goal_card(inner,g,color)'''

if old_sort in ui_src:
    ui_src = ui_src.replace(old_sort, new_sort)
    print("OK: priority sorting")
else:
    print("FAIL: sorting block")

# Add priority badge to goal card
old_card_r1 = '''        r1=tk.Frame(card,bg=bg); r1.pack(fill="x")
        done=g.get("status")=="done" or g.get("completed",0)
        tk.Label(r1,text=g["title"],bg=bg,fg=TEXT3 if done else TEXT,
                font=FONT_SMALL,anchor="w").pack(side="left",fill="x",expand=True)
        st=g.get("status","active")
        st_color={"done":ACCENT3,"abandoned":DANGER,"active":TEXT3}.get(st,TEXT3)
        tk.Label(r1,text=st.upper(),bg=bg,fg=st_color,
                font=("Segoe UI",7,"bold")).pack(side="right")'''

new_card_r1 = '''        r1=tk.Frame(card,bg=bg); r1.pack(fill="x")
        done=g.get("status")=="done" or g.get("completed",0)
        pri=g.get("priority","normal")
        pri_badge={"high":"🔴","normal":"","low":"🟢"}.get(pri,"")
        title_txt=(pri_badge+" " if pri_badge else "")+g["title"]
        tk.Label(r1,text=title_txt,bg=bg,fg=TEXT3 if done else TEXT,
                font=FONT_SMALL,anchor="w").pack(side="left",fill="x",expand=True)
        st=g.get("status","active")
        st_color={"done":ACCENT3,"abandoned":DANGER,"active":TEXT3}.get(st,TEXT3)
        tk.Label(r1,text=st.upper(),bg=bg,fg=st_color,
                font=("Segoe UI",7,"bold")).pack(side="right")'''

if old_card_r1 in ui_src:
    ui_src = ui_src.replace(old_card_r1, new_card_r1)
    print("OK: priority badge on card")
else:
    print("FAIL: goal card r1")

# ─────────────────────────────────────────────────────────────────────────────
# PART 4 — ui.py: AI GUIDELINES section in settings (before VOICE PROFILES)
# ─────────────────────────────────────────────────────────────────────────────
old_vp_section = '        # VOICE PROFILES\n        section("VOICE PROFILES", ACCENT2)'

new_guidelines = '''        # AI GUIDELINES
        section("AI GUIDELINES", ACCENT)
        gl_frame = tk.Frame(inner, bg=BG3, padx=14, pady=12)
        gl_frame.pack(fill="x", padx=10, pady=(0,6))
        tk.Label(gl_frame, text="Custom instructions for Echo (persona, tone, rules):",
                 bg=BG3, fg=TEXT3, font=FONT_TINY).pack(anchor="w", pady=(0,4))
        gl_text = tk.Text(gl_frame, bg=BG2, fg=TEXT, insertbackground=ACCENT,
                          relief="flat", font=FONT_SMALL, height=6, wrap="word",
                          highlightthickness=1, highlightbackground=BORDER)
        gl_text.pack(fill="x", pady=(0,6))
        gl_text.insert("1.0", SETTINGS.get("ai_guidelines", ""))
        tk.Label(gl_frame,
                 text="Example: 'You are Echo, a calm and focused assistant. Always be brief.'",
                 bg=BG3, fg=TEXT3, font=FONT_TINY, wraplength=280, justify="left").pack(anchor="w")

        # VOICE PROFILES
        section("VOICE PROFILES", ACCENT2)'''

if old_vp_section in ui_src:
    ui_src = ui_src.replace(old_vp_section, new_guidelines)
    print("OK: AI guidelines section")
else:
    print("FAIL: voice profiles section anchor not found")

# Save guidelines in save_s
old_save_s = '            SETTINGS["voice_id_enabled"] = voice_check_var.get()\n            save_settings(SETTINGS)'
new_save_s = '            SETTINGS["voice_id_enabled"] = voice_check_var.get()\n            SETTINGS["ai_guidelines"] = gl_text.get("1.0","end").strip()\n            save_settings(SETTINGS)'
if old_save_s in ui_src:
    ui_src = ui_src.replace(old_save_s, new_save_s)
    print("OK: save ai_guidelines")
else:
    print("FAIL: save_s not found")

open(UI, "w").write(ui_src)

# ─────────────────────────────────────────────────────────────────────────────
# PART 5 — ai.py: inject guidelines into system prompt
# ─────────────────────────────────────────────────────────────────────────────
AI = "/home/jesus999l/vision_assistant/ai.py"
ai_src = open(AI).read()

old_sys = '''def build_system_prompt():
    import time'''
new_sys = '''def build_system_prompt():
    import time
    # Inject user-defined AI guidelines
    try:
        import json as _json, os as _os
        _cfg = _json.load(open(_os.path.expanduser("~/vision_assistant/settings.json")))
        _guidelines = _cfg.get("ai_guidelines","").strip()
    except: _guidelines = ""'''

# Also need to insert guidelines into the returned prompt
# Find where the system prompt is returned/built
if "def build_system_prompt" in ai_src:
    # Find the function and inject guidelines at the end of it
    func_start = ai_src.find("def build_system_prompt()")
    # Find next def after it
    next_def = ai_src.find("\ndef ", func_start + 10)
    func_body = ai_src[func_start:next_def]
    
    if "guidelines" not in func_body:
        # Find the return statement
        ret_idx = func_body.rfind("return ")
        if ret_idx > 0:
            old_ret = func_body[ret_idx:]
            new_ret = old_ret.rstrip() + '\n    if _guidelines:\n        prompt += f"\\n\\nUser instructions:\\n{_guidelines}"\n    return prompt'
            # Only do this if there's a simple return
            if "return " in old_ret and "prompt" in func_body:
                new_func = func_body[:ret_idx] + new_ret
                ai_src = ai_src.replace(func_body, new_func)
                print("OK: guidelines injected into system prompt")
            else:
                print("SKIP: complex return in build_system_prompt")
        else:
            print("FAIL: no return in build_system_prompt")
    else:
        print("SKIP: guidelines already in ai.py")
else:
    print("FAIL: build_system_prompt not found")

open(AI, "w").write(ai_src)

# Also inject into wake_word streaming prompt
ww_src = open(WW := "/home/jesus999l/vision_assistant/wake_word.py").read()
old_ww_sys = '''    if full_context:
        try:
            from memory import build_memory_context
            ctx = build_memory_context()
        except: ctx = ""
        sys_prompt = (
            "You are Echo, a concise voice assistant. "
            "Answer in 1-3 short sentences. No markdown, no lists. "
            "Use the user context only if directly relevant."
            + (ctx[:600] if ctx else "")
        ).strip()'''

new_ww_sys = '''    if full_context:
        try:
            from memory import build_memory_context
            ctx = build_memory_context()
        except: ctx = ""
        try:
            import json as _j, os as _o
            _gl = _j.load(open(_o.path.expanduser("~/vision_assistant/settings.json"))).get("ai_guidelines","")
        except: _gl = ""
        sys_prompt = (
            "You are Echo, a concise voice assistant. "
            "Answer in 1-3 short sentences. No markdown, no lists. "
            "Use the user context only if directly relevant."
            + (("\\n\\n" + _gl) if _gl else "")
            + (ctx[:400] if ctx else "")
        ).strip()'''

if old_ww_sys in ww_src:
    ww_src = ww_src.replace(old_ww_sys, new_ww_sys)
    open(WW, "w").write(ww_src)
    print("OK: guidelines in voice AI prompt")
else:
    print("FAIL: voice AI prompt block")

# Syntax check all
for label, path in [("memory.py", MEM), ("ui.py", UI), ("ai.py", AI), ("wake_word.py", WW)]:
    r = subprocess.run(
        ["/home/jesus999l/vision_env/bin/python3", "-m", "py_compile", path],
        capture_output=True, text=True
    )
    print(f"{'OK' if r.returncode==0 else 'ERR'}: {label}")
    if r.returncode != 0: print(r.stderr)
