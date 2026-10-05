import io

import pandas as pd


def build_excel_bytes(summary, issues):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(summary).to_excel(writer, sheet_name="Summary", index=False)
        pd.DataFrame(issues).to_excel(writer, sheet_name="Issues and Fixes", index=False)

        # Make columns wide enough to read
        for sheet in writer.book.worksheets:
            for column in sheet.columns:
                longest = max(len(str(cell.value or "")) for cell in column)
                sheet.column_dimensions[column[0].column_letter].width = min(longest + 2, 60)
    return buffer.getvalue()    