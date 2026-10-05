"""
UI for the 'Reorganize links' tab: takes a jumbled export (one row per
image, name and link mixed together) and turns it into one row per
product with the image links laid out horizontally and numbered.

This only reorganizes a file the user already has -- nothing is
downloaded from Amazon or any marketplace here.
"""

import streamlit as st

from src.imaging.reorganize_links import (
    build_horizontal_table,
    guess_link_column,
    guess_name_column,
    non_empty_columns,
    read_any_table,
    result_to_csv_bytes,
    result_to_xlsx_bytes,
)


def render_reorganize_links_tool():
    st.subheader("Reorganize links")
    st.info(
        "Upload an export where each row is one image (a filename plus a link). "
        "This groups rows by product and lays each product's images out "
        "horizontally -- Main_Name, Secondary_Name, then Image_1, Image_2, "
        "Image_3... -- instead of the usual one-link-per-row, A-Z-sort-then-"
        "transpose-by-hand process."
    )

    upload = st.file_uploader(
        "Upload the export (.xlsx or .csv)",
        type=["xlsx", "xls", "csv"],
        key="reorg_upload",
    )
    if upload is None:
        st.caption("Waiting for a file. Nothing is sent anywhere -- this stays in the tool.")
        return

    file_bytes = upload.getvalue()
    sig = (upload.name, len(file_bytes))
    if st.session_state.get("reorg_sig") != sig:
        st.session_state["reorg_sig"] = sig
        st.session_state.pop("reorg_result", None)

    try:
        df = read_any_table(file_bytes, upload.name)
    except Exception as e:
        st.error(f"Could not read that file: {e}")
        return

    if df.empty:
        st.warning("That file doesn't have any rows.")
        return

    all_columns = list(df.columns)
    columns = non_empty_columns(df)
    skipped = len(all_columns) - len(columns)
    guessed_name = guess_name_column(columns)
    guessed_link = guess_link_column(columns)

    caption = f"Found {len(df):,} rows and {len(all_columns)} columns."
    if skipped:
        caption += f" {skipped} column(s) are blank for every row, so they're left out of the pickers below."
    st.caption(caption)

    if not columns:
        st.warning("Every column in this file is blank, so there's nothing to pick from.")
        return

    c1, c2 = st.columns(2)
    with c1:
        name_col = st.selectbox(
            "Column with the image filename",
            options=columns,
            index=columns.index(guessed_name) if guessed_name in columns else 0,
            key="reorg_name_col",
            help="The column that holds names like MAIN_SECONDARY_US_ISP_05.jpg.",
        )
    with c2:
        link_col = st.selectbox(
            "Column with the image link",
            options=columns,
            index=columns.index(guessed_link) if guessed_link in columns else 0,
            key="reorg_link_col",
            help="The column that holds the actual image URL for that row.",
        )

    with st.expander("Parsing options", expanded=False):
        delimiter = st.text_input(
            "Segment separator in the filename",
            value="_",
            max_chars=3,
            key="reorg_delim",
            help="Most Pattern exports separate name segments with underscores.",
        )
        has_secondary = st.checkbox(
            "Filenames include a secondary name segment (2nd part of the name)",
            value=True,
            key="reorg_has_secondary",
            help=(
                "On: MAIN_SECONDARY_..._05.jpg -> Main_Name=MAIN, Secondary_Name=SECONDARY. "
                "Off: everything before the trailing number is treated as Main_Name only."
            ),
        )
        st.caption(
            "The image number is always read as the digits at the very end of the "
            "filename, right before the extension -- whatever sits between the name "
            "and that number (country code, tag, etc.) is ignored and dropped."
        )

    if st.button("Reorganize", type="primary", key="reorg_run"):
        with st.spinner("Grouping and arranging..."):
            result = build_horizontal_table(
                df,
                name_col=name_col,
                link_col=link_col,
                delimiter=delimiter or "_",
                has_secondary=has_secondary,
            )
        st.session_state["reorg_result"] = result

    result = st.session_state.get("reorg_result")
    if result is None:
        return

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Input rows", f"{result.row_count:,}")
    m2.metric("Products found", f"{result.group_count:,}")
    m3.metric("Image columns", result.max_images)
    m4.metric("Rows with a problem", f"{len(result.problems):,}")

    if result.table.empty:
        st.warning(
            "Nothing could be grouped. Double-check the filename column, the "
            "separator, and whether filenames actually end in a number."
        )
    else:
        st.caption("Preview -- sorted A to Z by Main_Name, then Secondary_Name.")
        st.dataframe(result.table, width="stretch", height=360)

    if not result.problems.empty:
        st.warning(
            f"{len(result.problems)} row(s) couldn't be placed (shown below and "
            "included on a 'Problems' sheet in the download) -- nothing was silently "
            "dropped."
        )
        st.dataframe(result.problems, width="stretch", height=220)

    if not result.table.empty:
        st.markdown("#### Download")
        d1, d2 = st.columns(2)
        with d1:
            st.download_button(
                "Download as Excel (.xlsx)",
                data=result_to_xlsx_bytes(result),
                file_name="reorganized_image_links.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="reorg_dl_xlsx",
            )
        with d2:
            st.download_button(
                "Download as CSV",
                data=result_to_csv_bytes(result),
                file_name="reorganized_image_links.csv",
                mime="text/csv",
                key="reorg_dl_csv",
            )