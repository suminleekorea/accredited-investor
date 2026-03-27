import re

def extract_payment(text):
    match = re.search(r'USD\s?([\d,]+\.\d{2})', text)
    return float(match.group(1).replace(",", "")) if match else 0

def validate_payment(expected, actual):
    return "MATCH" if abs(expected - actual) < 1 else "MISMATCH"
