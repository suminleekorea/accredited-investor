def risk_flags(income, net_worth):
    flags = []

    if income < 50000:
        flags.append("Low income detected")

    if net_worth < 100000:
        flags.append("Low asset value")

    return flags
