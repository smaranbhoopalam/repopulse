import os

path = r"d:\Hackathon\repopulse\driftguard\dashboard\static\app.js"
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(r'\`', '`')
content = content.replace(r'\${', '${')
content = content.replace(r'\\n', r'\n')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
