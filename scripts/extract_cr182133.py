"""Extract CR-182133 Table VI as structured rows; print rows for target codes."""
import fitz  # pymupdf

doc = fitz.open(".cache_CR182133.pdf")
targets = {"44135", "44155", "44355", "44145", "44144"}

out = []
for i in range(26, 40):
    page = doc[i]
    try:
        tabs = page.find_tables()
    except Exception as e:
        out.append(f"[page {i}] find_tables error: {e}")
        continue
    for ti, tab in enumerate(tabs):
        rows = tab.extract()
        if not rows:
            continue
        flat0 = " ".join(str(c) for c in rows[0] if c)
        out.append(f"\n===== page {i} table {ti}  ({len(rows)}x{len(rows[0])}) header: {flat0[:90]}")
        for r in rows:
            joined = "|".join("" if c is None else str(c).strip() for c in r)
            if any(t in joined for t in targets) or "RUNCODE" in joined.upper() \
               or "Ma" in joined or "Pt" in joined or "Tc" in joined or "Pc" in joined:
                out.append(joined)

with open(".cache_CR182133_rows.txt", "w", encoding="utf-8") as fh:
    fh.write("\n".join(out))
print("wrote", len(out), "lines")
