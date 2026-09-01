def cascade_forward(base_amt, mapped_tax):
    running = base_amt
    breakdown = {}
    for category, details in mapped_tax.items():
        rate = details["rate"]
        base_before = running
        tax_amt = abs(round(base_before * (rate / 100), 4))
        running = abs(round(base_before + tax_amt, 4))
        breakdown[category] = {"base": base_before, "tax": tax_amt}
    return running, breakdown

def cascade_reverse(final_amt, mapped_tax):
    categories_reversed = list(mapped_tax.items())[::-1]
    running = final_amt
    breakdown = {}
    for category, details in categories_reversed:
        rate = details["rate"]
        taxbl = abs(round(running / (1 + rate / 100), 4))
        tax_amt = abs(round(running - taxbl, 4))
        breakdown[category] = {"taxbl": taxbl, "tax": tax_amt}
        running = taxbl
    return breakdown