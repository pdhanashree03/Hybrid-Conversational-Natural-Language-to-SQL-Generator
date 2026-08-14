import re

text = "now filter by Germany"

pat1 = r'\b(?:from|in|at|located in|based in)\s+([A-Z][a-zA-Z]{2,})'
pat2 = r'\bfilter(?:ed)?\s+by\s+([A-Z][a-zA-Z]{2,})'
pat3 = r'\bby\s+([A-Z][a-zA-Z]{2,})'

print("pat1 (from/in/at):", re.findall(pat1, text, re.IGNORECASE))
print("pat2 (filter by):", re.findall(pat2, text, re.IGNORECASE))
print("pat3 (by X):", re.findall(pat3, text))