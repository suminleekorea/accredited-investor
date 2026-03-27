import re

def extract_financials(text):
    numbers = re.findall(r'\d{2,3},?\d{3,6}', text)
    numbers = [int(n.replace(",", "")) for n in numbers]

    income = max(numbers) if numbers else 0
    net_worth = sum(numbers) if len(numbers) > 3 else 0

    return income, net_worth

def validate(income, net_worth):
    return "PASS" if income >= 300000 or net_worth >= 2000000 else "FAIL"
