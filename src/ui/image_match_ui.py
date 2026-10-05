"""
UI for the 'Image match check' tool: given a product name (or two
identifiers, where the second is the actual name to check) paired with
its main image link, this fetches the image and scores it against that
name using a local, free CLIP model -- no API key, no per-call cost,
nothing leaves this machine once the model is cached (see
src/imaging/clip_match.py for the trade-off and how the thresholds below
were picked).

Input can come from a pasted block of 'name(s) then link' entries, or
from a spreadsheet with separate columns. Either way, only public image
links the user already has are fetched -- this refuses any link on a
Seller Central host outright, and never logs into or scrapes Amazon.
"""

import pandas as pd
import streamlit as st

from src.imaging.clip_match import (
    DEFAULT_NO_THRESHOLD,
    DEFAULT_YES_THRESHOLD,
    check_rows_clip,
)
from src.imaging.image_match import (
    build_rows_from_table,
    guess_image_column,
    guess_name1_column,
    guess_name2_column,
    non_empty_columns,
    parse_pasted_pairs,
    read_any_table,
    results_to_dataframe,
    results_to_xlsx_bytes,
)

PASTE_PLACEHOLDER = (
    "Homedics Tabletop Water Fountain, Home Decor Soothing Sound Machine\n"
    "https://m.media-amazon.com/images/I/61vEjplUwlL._AC_SL1500_.jpg\n"
    "\n"
    "Another Product Name\n"
    "https://m.media-amazon.com/images/I/xyzexample.jpg"
)


def _threshold_inputs() -> tuple[float, float]:
    with st.expander("Similarity sensitivity (advanced)", expanded=False):
        st.caption(
            "CLIP scores every image/name pair as a similarity number, not a clean "
            "yes/no -- these two cutoffs turn that number into Yes / Unsure / No. The "
            "defaults were tuned on a handful of real Amazon product photos; nudge them "
            "if your own results come back too strict or too lenient."
        )
        yes_threshold = st.slider(
            "Call it a Yes at or above",
            min_value=0.15, max_value=0.35, value=DEFAULT_YES_THRESHOLD, step=0.01,
            key="img_match_yes_threshold",
        )
        no_threshold = st.slider(
            "Call it a No below",
            min_value=0.10, max_value=0.30, value=DEFAULT_NO_THRESHOLD, step=0.01,
            key="img_match_no_threshold",
        )
        if no_threshold >= yes_threshold:
            st.warning("The 'No' cutoff should be lower than the 'Yes' cutoff, or every row will land in one bucket.")
    return yes_threshold, no_threshold


def _run_and_show(rows: list[dict], problems: list[dict], yes_threshold: float, no_threshold: float):
    if problems:
        st.warning(f"{len(problems)} entr{'y' if len(problems) == 1 else 'ies'} couldn't be used:")
        st.dataframe(pd.DataFrame(problems), use_container_width=True, hide_index=True)

    if not rows:
        st.info("Nothing to check yet.")
        return

    st.caption(f"Ready to check {len(rows)} image(s) against their name.")
    with st.expander(f"Preview the {min(len(rows), 10)} row(s) about to be checked", expanded=False):
        st.dataframe(pd.DataFrame(rows).head(10), use_container_width=True, hide_index=True)

    run = st.button("Check images", type="primary", key="img_match_run")
    if not run:
        return

    progress = st.progress(0.0, text="Starting...")

    def _progress_cb(done, total):
        progress.progress(done / total, text=f"Checked {done} of {total}")

    with st.spinner(
        "Fetching images and scoring each one against its name -- if this is the first "
        "run on this server, it also downloads the CLIP model (~600 MB) once, which can "
        "take a minute or two."
    ):
        results = check_rows_clip(
            rows, yes_threshold=yes_threshold, no_threshold=no_threshold, progress_cb=_progress_cb
        )
    progress.empty()

    df = results_to_dataframe(results)
    st.session_state["img_match_df"] = df


def _render_results():
    df = st.session_state.get("img_match_df")
    if df is None or df.empty:
        return

    counts = df["Match"].value_counts()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Yes", int(counts.get("Yes", 0)))
    m2.metric("No", int(counts.get("No", 0)))
    m3.metric("Unsure", int(counts.get("Unsure", 0)))
    m4.metric("Error", int(counts.get("Error", 0)))

    if int(counts.get("Error", 0)) > 0:
        st.caption(
            "Rows marked 'Error' usually mean the CLIP dependencies aren't installed on this "
            "server yet, or an image link couldn't be fetched -- check the Reason column."
        )

    only_flagged = st.checkbox(
        "Show only rows that didn't come back a clear Yes",
        key="img_match_only_flagged",
    )
    shown = df if not only_flagged else df[df["Match"] != "Yes"]

    st.markdown("##### Results")
    st.dataframe(shown, use_container_width=True, hide_index=True, height=min(480, 60 + 35 * len(shown)))

    st.download_button(
        "Download results (.xlsx)",
        data=results_to_xlsx_bytes(df),
        file_name="image_match_results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="img_match_download",
    )


def render_image_match_tool():
    st.subheader("Image match check")
    st.info(
        "Give a product name (or two identifiers, where the second one is the actual name to "
        "check -- e.g. 'Homedics Tabletop Water Fountain, Home Decor Soothing Sound Machine') "
        "paired with its main image link, and this fetches the image and scores it against that "
        "name with a free, local CLIP model -- no API key, nothing sent to a third-party AI "
        "service. It's a useful first pass, not a guarantee: CLIP can't explain its reasoning "
        "the way a full vision model could, and it's weaker at catching subtle mismatches (right "
        "general category, wrong color or model, for example). Only the public image link you "
        "provide is fetched -- nothing here logs into or scrapes Seller Central or any other "
        "Amazon account page."
    )

    yes_threshold, no_threshold = _threshold_inputs()
    st.divider()

    mode = st.radio(
        "How do you want to give the name + image pairs?",
        ["Paste pairs", "Upload a spreadsheet"],
        key="img_match_mode",
        horizontal=True,
    )

    if mode == "Paste pairs":
        st.caption(
            "One entry per product: the name (or 'Identifier 1, Identifier 2') on one or more "
            "lines, then the image link on the next line. Blank lines between entries are optional."
        )
        pasted = st.text_area(
            "Paste name + link pairs",
            height=220,
            key="img_match_paste",
            placeholder=PASTE_PLACEHOLDER,
        )
        if not pasted.strip():
            st.caption("Waiting for pasted text.")
            return
        rows, problems = parse_pasted_pairs(pasted)
        _run_and_show(rows, problems, yes_threshold, no_threshold)

    else:
        upload = st.file_uploader(
            "Upload a spreadsheet (.xlsx or .csv)",
            type=["xlsx", "xls", "csv"],
            key="img_match_upload",
        )
        if upload is None:
            st.caption("Waiting for a file. Nothing is sent anywhere -- this stays in the tool.")
            return

        try:
            df = read_any_table(upload.getvalue(), upload.name)
        except Exception as e:
            st.error(f"Could not read that file: {e}")
            return

        if df.empty:
            st.warning("That file doesn't have any rows.")
            return

        columns = non_empty_columns(df)
        if not columns:
            st.warning("Every column in this file is blank, so there's nothing to pick from.")
            return

        guessed_1 = guess_name1_column(columns)
        guessed_2 = guess_name2_column(columns)
        guessed_link = guess_image_column(columns)

        c1, c2, c3 = st.columns(3)
        with c1:
            id1_col = st.selectbox(
                "Identifier 1 column (optional context)",
                options=["(none)"] + columns,
                index=(columns.index(guessed_1) + 1) if guessed_1 in columns else 0,
                key="img_match_id1_col",
            )
        with c2:
            id2_col = st.selectbox(
                "Identifier 2 / name column (checked against the image)",
                options=["(none)"] + columns,
                index=(columns.index(guessed_2) + 1) if guessed_2 in columns else 0,
                key="img_match_id2_col",
            )
        with c3:
            link_col = st.selectbox(
                "Image link column",
                options=columns,
                index=columns.index(guessed_link) if guessed_link in columns else 0,
                key="img_match_link_col",
            )

        id1_col = None if id1_col == "(none)" else id1_col
        id2_col = None if id2_col == "(none)" else id2_col

        rows, problems = build_rows_from_table(df, id1_col, id2_col, link_col)
        _run_and_show(rows, problems, yes_threshold, no_threshold)

    _render_results()