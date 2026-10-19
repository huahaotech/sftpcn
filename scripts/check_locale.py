from pathlib import Path
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from localization import validate
root = Path(__file__).resolve().parents[1]
en = json.loads((root / 'locale/en.json').read_text(encoding='utf-8'))
zh = json.loads((root / 'locale/zh.json').read_text(encoding='utf-8'))
count = validate(en, zh)
print(f'Locale OK: {count} keys, all placeholders preserved.')
