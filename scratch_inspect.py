import json

out = []
with open(r'C:\Users\Abdul Rehman\.gemini\antigravity-ide\brain\15aab8c1-06d6-4194-83e5-96d95985c185\.system_generated\logs\transcript_full.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        data = json.loads(line)
        step = data.get('step_index', 0)
        if step >= 15930:
            for t in data.get('tool_calls', []):
                name = t.get('name')
                target = t.get('args', {}).get('TargetFile') or t.get('args', {}).get('CommandLine')
                out.append(f"Step {step}: {name} -> {target}")

with open(r'C:\Users\Abdul Rehman\.gemini\antigravity-ide\brain\15aab8c1-06d6-4194-83e5-96d95985c185\scratch\recent_edits.txt', 'w', encoding='utf-8') as f_out:
    f_out.write('\n'.join(out))
print("Done, total actions:", len(out))
