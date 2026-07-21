# -*- coding: utf-8 -*-
"""
============================================================================
GST INVOICE CALC ENGINE — Santosh Diesel Style (Standalone, No DB/Inventory)
============================================================================
फक्त गणित + इनव्हॉइस ग्रिड स्ट्रक्चर. कुठलीही डेटाबेस/इन्व्हेंटरी टेबल नाही.

VISIBLE BILL COLUMNS (MRP कधीही column म्हणून दिसत नाही, फक्त backend input):
    Sr.No | Description/Part No | HSN/SAC | GST% | Rate (Ex-GST) | Qty | Disc.% | Amount

PER-ROW FORMULAS:
    Ex-GST Rate   = MRP / (1 + GST%/100)
    Total Base    = Ex-GST Rate * Qty
    Row Amount    = Total Base - (Total Base * Disc%/100)      -> Taxable Value
    Row CGST      = Row Amount * (GST%/2) / 100
    Row SGST      = Row Amount * (GST%/2) / 100

FOOTER SUMMARY:
    Subtotal   = Σ Row Amount
    Total CGST = Σ Row CGST
    Total SGST = Σ Row SGST
    Round Off  = round(Grand Total) - Grand Total (raw)
    Grand Total (final) = Subtotal + Total CGST + Total SGST + Round Off

Mixed GST% (5/12/18/28) आपोआप वेगळं group होऊन Tax Breakup Table मध्ये दिसतं.
============================================================================
"""


def calculate_row(description, mrp, qty, disc_percent, gst_rate, hsn_sac="", part_no="-"):
    """एका item ची संपूर्ण row calculate करतो — MRP मागून Ex-GST Rate काढतो."""
    mrp = float(mrp or 0)
    qty = float(qty or 0)
    disc_percent = float(disc_percent or 0)
    gst_rate = float(gst_rate or 0)

    ex_gst_rate = mrp / (1 + gst_rate / 100) if gst_rate else mrp
    total_base = ex_gst_rate * qty
    row_amount = total_base - (total_base * disc_percent / 100)  # Taxable Value

    half_gst = gst_rate / 2
    row_cgst = row_amount * (half_gst / 100)
    row_sgst = row_amount * (half_gst / 100)

    return {
        "description": description,
        "part_no": part_no or "-",
        "hsn_sac": hsn_sac or "-",
        "gst_rate": gst_rate,
        "rate": ex_gst_rate,          # बिलावर दिसणारा Rate — MRP नाही
        "qty": qty,
        "disc_percent": disc_percent,
        "amount": row_amount,         # Taxable Value (बिलावरचा Amount column)
        "cgst": row_cgst,
        "sgst": row_sgst,
        "row_total": row_amount + row_cgst + row_sgst,  # या ओळीची GST-सकट रक्कम
    }


def build_invoice(items):
    """
    items : list of dict — प्रत्येकात असावं:
        {"description", "mrp", "qty", "disc_percent", "gst_rate",
         "hsn_sac" (optional), "part_no" (optional)}

    Returns:
        {
          "rows": [ {sr_no, ...calculate_row output} ],
          "subtotal": float,
          "total_cgst": float,
          "total_sgst": float,
          "round_off": float,
          "grand_total": float,          # राऊंड झालेला अंतिम आकडा
          "tax_breakup": [ {gst_rate, taxable, cgst, sgst, total}, ... ]  # GST% नुसार वेगळं
        }
    """
    rows = []
    subtotal = total_cgst = total_sgst = 0.0
    breakup = {}  # gst_rate -> {"taxable","cgst","sgst"}

    for idx, item in enumerate(items, start=1):
        row = calculate_row(
            description=item.get("description", ""),
            mrp=item.get("mrp", 0),
            qty=item.get("qty", 0),
            disc_percent=item.get("disc_percent", 0),
            gst_rate=item.get("gst_rate", 0),
            hsn_sac=item.get("hsn_sac", ""),
            part_no=item.get("part_no", "-"),
        )
        row["sr_no"] = idx
        rows.append(row)

        subtotal += row["amount"]
        total_cgst += row["cgst"]
        total_sgst += row["sgst"]

        gr = row["gst_rate"]
        grp = breakup.setdefault(gr, {"taxable": 0.0, "cgst": 0.0, "sgst": 0.0})
        grp["taxable"] += row["amount"]
        grp["cgst"] += row["cgst"]
        grp["sgst"] += row["sgst"]

    raw_grand_total = subtotal + total_cgst + total_sgst
    grand_total = round(raw_grand_total)
    round_off = grand_total - raw_grand_total

    tax_breakup = [
        {
            "gst_rate": gr,
            "taxable": v["taxable"],
            "cgst": v["cgst"],
            "sgst": v["sgst"],
            "total": v["taxable"] + v["cgst"] + v["sgst"],
        }
        for gr, v in sorted(breakup.items())
    ]

    return {
        "rows": rows,
        "subtotal": subtotal,
        "total_cgst": total_cgst,
        "total_sgst": total_sgst,
        "round_off": round_off,
        "grand_total": grand_total,
        "tax_breakup": tax_breakup,
    }


# ==========================================================================
# DISPLAY HELPER — फक्त terminal/console print साठी (कुठलाही UI dependency नाही)
# ==========================================================================
def print_invoice(invoice):
    header = f"{'Sr':<3}{'Description':<22}{'HSN':<10}{'GST%':>6}{'Rate':>10}{'Qty':>6}{'Disc%':>7}{'Amount':>10}"
    print(header)
    print("-" * len(header))
    for r in invoice["rows"]:
        print(f"{r['sr_no']:<3}{r['description'][:20]:<22}{r['hsn_sac']:<10}"
              f"{r['gst_rate']:>6.0f}{r['rate']:>10.2f}{r['qty']:>6.0f}"
              f"{r['disc_percent']:>7.0f}{r['amount']:>10.2f}")

    print("-" * len(header))
    print(f"{'Subtotal':>57}: {invoice['subtotal']:>10.2f}")
    print(f"{'Total CGST':>57}: {invoice['total_cgst']:>10.2f}")
    print(f"{'Total SGST':>57}: {invoice['total_sgst']:>10.2f}")
    print(f"{'Round Off':>57}: {invoice['round_off']:>10.2f}")
    print(f"{'GRAND TOTAL':>57}: {invoice['grand_total']:>10.2f}")

    print("\nTax Breakup (GST% wise):")
    print(f"{'GST%':<6}{'Taxable':>12}{'CGST':>12}{'SGST':>12}{'Total':>12}")
    for b in invoice["tax_breakup"]:
        print(f"{b['gst_rate']:<6.0f}{b['taxable']:>12.2f}{b['cgst']:>12.2f}"
              f"{b['sgst']:>12.2f}{b['total']:>12.2f}")


# ==========================================================================
# EXAMPLE USAGE — Mixed GST% (5%, 18%) टेस्ट
# ==========================================================================
if __name__ == "__main__":
    demo_items = [
        {"description": "Wiper Blade 14\"", "part_no": "WB-14", "hsn_sac": "85129000",
         "mrp": 250, "qty": 4, "disc_percent": 10, "gst_rate": 18},
        {"description": "Engine Oil 1L", "part_no": "EO-1L", "hsn_sac": "27101990",
         "mrp": 120, "qty": 6, "disc_percent": 5, "gst_rate": 18},
        {"description": "Battery Terminal", "part_no": "BT-01", "hsn_sac": "85446090",
         "mrp": 60, "qty": 10, "disc_percent": 0, "gst_rate": 5},
    ]

    invoice = build_invoice(demo_items)
    print_invoice(invoice)