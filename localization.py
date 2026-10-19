"""Chinese UI adaptation for SFTPGo 2.7.6, used only inside SFTPGo."""
import json
from pathlib import Path
import re

CACHE_VERSION = 'sftpcn-0.1.0-zh-20261019'

def flatten(value, prefix=''):
    return {key: item for name, item in value.items()
            for key, item in (flatten(item, prefix + name + '.').items()
                              if isinstance(item, dict) else [(prefix + name, item)])}

def validate(english, chinese):
    a, b = flatten(english), flatten(chinese)
    if a.keys() != b.keys():
        raise ValueError('语言键不匹配：' + str(sorted(a.keys() ^ b.keys())))
    patterns = [r'\{\{[^}]+\}\}', r'\$t\([^)]+\)',
                r'_(?:START|END|TOTAL|MAX|MENU)_', r'%[ds]', r'%[a-z_]+%']
    for key in a:
        if not isinstance(b[key], str) or not b[key].strip():
            raise ValueError('翻译为空：' + key)
        for pattern in patterns:
            if sorted(re.findall(pattern, a[key])) != sorted(re.findall(pattern, b[key])):
                raise ValueError('占位符不匹配：' + key)
    return len(a)

def patch_template(text):
    marker = 'const lngs = {};'
    if marker not in text:
        raise ValueError('不支持的模板版本')
    if 'lngs.zh =' not in text:
        text = text.replace(marker, marker + "\n    lngs.zh = { nativeName: '简体中文' };", 1)
    text = re.sub(r"defaultVersion:\s*('[^']*'|\"[^\"]*\")",
                  "defaultVersion: '" + CACHE_VERSION + "'", text)
    # Preserve an explicitly selected English preference; otherwise use Chinese.
    if 'lookupQuerystring' not in text:
        text = text.replace("load: 'languageOnly',", "load: 'languageOnly',\n                detection: { order: ['querystring', 'localStorage'], lookupQuerystring: 'lng' },")
    return text

def install_ui(ui, source):
    ui, source = Path(ui), Path(source)
    en = json.loads((ui / 'locales/en/translation.json').read_text(encoding='utf-8'))
    zh = json.loads(source.read_text(encoding='utf-8'))
    count = validate(en, zh)
    target = ui / 'locales/zh'
    target.mkdir(exist_ok=True)
    (target / 'translation.json').write_text(json.dumps(zh, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    base = ui / 'templates/common/base.html'
    base.write_text(patch_template(base.read_text(encoding='utf-8')), encoding='utf-8')
    for path in ui.rglob('*'):
        path.chmod(0o755 if path.is_dir() else 0o644)
    return count
