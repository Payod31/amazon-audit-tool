import base64

import pandas as pd
import streamlit as st

from src.imaging.link_template import (
    BASE_COLUMNS,
    blank_df,
    build_filename,
    cell,
    column_names,
    fetch_and_inspect,
    finalize_zip,
    find_image_columns,
    load_prep_settings,
    normalize_columns,
    template_csv_bytes,
    template_xlsx_bytes,
    zoom_compare_crops,
)
from src.ui.theme import status_label, step_head

def _read_upload(uploaded):
    if uploaded.name.lower().endswith(".csv"):
        return pd.read_csv(uploaded, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    return pd.read_excel(uploaded, dtype=str)

def _column_config(cols):
    labels = {
        "Main_Name": ("Main name", "Brand or product name. Letters and numbers both work."),
        "Secondary_Name": ("Secondary name (optional)", "Leave empty to skip it in the file name."),
        "Country_Code": ("Country", "2-letter code like US, CA, DE."),
    }
    config = {}
    for c in cols:
        if c in labels:
            label, help_text = labels[c]
            config[c] = st.column_config.TextColumn(label, help=help_text, width="medium")
        else:
            config[c] = st.column_config.TextColumn(
                "Image " + c.split("_")[-1], help="Paste a direct image link.", width="large"
            )
    return config

def _render_image(container, data, caption="", width=280):
    """Plain HTML <img> (not st.image), so there's no fullscreen icon involved."""
    b64 = base64.b64encode(data).decode("ascii")
    container.markdown(
        f'<img src="data:image/jpeg;base64,{b64}" width="{width}" '
        'style="max-width:100%;border-radius:8px;" />',
        unsafe_allow_html=True,
    )
    if caption:
        container.caption(caption)

def render_link_template_tool():
    st.session_state.setdefault("lt_ver", 0)
    st.session_state.setdefault("lt_pv_ver", 0)

    # ---------- Step 1: template ----------
    with st.container(border=True):
        step_head(
            1, "Get a template",
            "Optional. Download it, fill it in Excel, then upload it back. "
            "Or skip this and type straight into the table in step 2.",
        )
        c1, c2, c3 = st.columns(3, vertical_alignment="bottom")
        n = int(c1.number_input("Number of image columns", 1, 30, 9, key="lt_n_input"))
        c2.download_button(
            "Download .xlsx template", data=template_xlsx_bytes(n),
            file_name="image_links_template.xlsx", width="stretch",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        c3.download_button(
            "Download .csv template", data=template_csv_bytes(n),
            file_name="image_links_template.csv", mime="text/csv",
            width="stretch",
        )
        with st.expander("Already filled a template? Upload it"):
            uploaded = st.file_uploader(
                "Upload filled template", type=["xlsx", "csv"],
                key="lt_upload", label_visibility="collapsed",
            )
        with st.expander("Look up images by ASIN (coming soon)"):
            st.text_area(
                "Paste ASINs, one per line", placeholder="B0ABC12345\nB0XYZ98765",
                disabled=True, key="lt_asin_box", height=90,
            )
            st.caption(
                "🚧 Work in progress: automatic lookup needs a data API key, "
                "so it can't be used yet. Add your image links in step 2."
            )

    cols = column_names(n)

    if uploaded is not None:
        sig = f"{uploaded.name}-{uploaded.size}"
        if st.session_state.get("lt_sig") != sig:
            try:
                st.session_state["lt_base"] = normalize_columns(_read_upload(uploaded))
                st.session_state["lt_sig"] = sig
                st.session_state["lt_ver"] += 1
            except Exception as e:
                st.error(f"Could not read the file: {e}")

    if "lt_base" not in st.session_state:
        st.session_state["lt_base"] = blank_df(n)
    if st.session_state.get("lt_prev_n") != n:
        last = st.session_state.get("lt_last")
        if last is not None:
            st.session_state["lt_base"] = last
        st.session_state["lt_prev_n"] = n
        st.session_state["lt_ver"] += 1

    base = st.session_state["lt_base"]
    extra = [c for _, c in find_image_columns(base) if c not in cols]
    base = base.reindex(columns=cols).fillna("")

    # ---------- Step 2: table ----------
    with st.container(border=True):
        step_head(
            2, "Add your image links",
            "Click a cell and type, or paste straight from Excel. "
            "Use the + under the table to add rows.",
        )
        if extra:
            st.warning("Your data has more image columns than the number in step 1. "
                       "Increase that number to see them.")
        edited = st.data_editor(
            base, num_rows="dynamic", width="stretch", hide_index=True,
            column_config=_column_config(cols),
            key=f"lt_editor_{st.session_state['lt_ver']}_{n}",
        )
        df = normalize_columns(pd.DataFrame(edited))
        st.session_state["lt_last"] = df

        img_cols = find_image_columns(df)
        link_count = sum(1 for _, r in df.iterrows() for _, c in img_cols if cell(r, c))

        f1, f2 = st.columns([3, 1], vertical_alignment="center")
        example = ""
        for _, r in df.iterrows():
            nums = [num for num, c in img_cols if cell(r, c)]
            if nums and cell(r, "Main_Name"):
                example = build_filename(
                    cell(r, "Main_Name"), cell(r, "Secondary_Name"),
                    cell(r, "Country_Code"), nums[0],
                )
                break
        f1.markdown(
            f"**{link_count}** links ready"
            + (f"  ·  first file will be named `{example}`" if example else ""),
        )
        if f2.button("Clear table", width="stretch"):
            st.session_state["lt_base"] = blank_df(n)
            st.session_state["lt_last"] = None
            st.session_state["lt_result"] = None
            st.session_state["lt_preview"] = None
            st.session_state["lt_ver"] += 1
            st.rerun()

    # ---------- Step 3: size and quality ----------
    with st.container(border=True):
        step_head(
            3, "Choose size and quality",
            "Pick the square size and JPG quality, then check which images would need enlarging.",
        )
        defaults = load_prep_settings()
        s1, s2 = st.columns(2, gap="large")
        with s1:
            target_size = st.number_input(
                "Target square size (px)",
                min_value=500, max_value=10000,
                value=int(defaults["target_size"]), step=100,
                key="lt_target_size",
                help="Amazon wants at least 1000px on the long edge; 2000px is a safe default.",
            )
        with s2:
            jpg_quality = st.slider(
                "JPG quality", min_value=70, max_value=100,
                value=int(defaults["jpg_quality"]), key="lt_jpg_quality",
                help="Higher is sharper but a larger file. Lowered automatically if a file "
                     "would exceed Amazon's 10MB cap.",
            )
        pad = st.checkbox(
            "Pad each image to a white square (Amazon style)",
            value=True, key="lt_pad",
        )
        mild_threshold_pct = st.slider(
            "Auto-approve enlarging up to this much, without asking (%)",
            min_value=0, max_value=100, value=15, step=5, key="lt_mild_threshold",
            help="An enlargement smaller than this is treated as invisible and done "
                 "automatically -- useful when checking a large batch. Only enlargements "
                 "bigger than this will ask you first in step 4.",
        )

        settings = {
            "target_size": target_size,
            "jpg_quality": jpg_quality,
            "min_fill_percent_warning": defaults["min_fill_percent_warning"],
        }

        signature = (tuple(pd.util.hash_pandas_object(df)), int(target_size), pad)
        stale = (
            st.session_state.get("lt_preview") is not None
            and st.session_state.get("lt_preview_sig") != signature
        )
        if stale:
            st.caption("Your links or settings changed since the last check -- check again before downloading.")

        if st.button("Check images", disabled=link_count == 0):
            bar = st.progress(0.0)
            items = fetch_and_inspect(
                df, int(target_size),
                progress=lambda done, total: bar.progress(done / max(total, 1)),
            )
            bar.empty()
            st.session_state["lt_preview"] = items
            st.session_state["lt_preview_sig"] = signature
            st.session_state["lt_pv_ver"] += 1
            st.session_state["lt_result"] = None

    # ---------- Step 4: review and download ----------
    preview = st.session_state.get("lt_preview")
    if preview is not None and not stale:
        with st.container(border=True):
            step_head(
                4, "Review and download",
                "Small enlargements are approved automatically; anything bigger gets a "
                "quick decision below.",
            )
            errors = [it for it in preview if it.get("error")]
            ok_items = [it for it in preview if not it.get("error")]
            needs_up = [it for it in ok_items if pad and it.get("needs_upscale")]
            fine = [it for it in ok_items if not (pad and it.get("needs_upscale"))]

            decisions = {}

            if not pad:
                st.caption(
                    "Padding is off, so every image downloads cleaned up (background fixed) "
                    "at its own size -- no squaring, no enlarging."
                )
            else:
                mild_cutoff = 1.0 + mild_threshold_pct / 100.0
                needs_up_mild = [it for it in needs_up if it["raw_scale"] <= mild_cutoff]
                needs_up_significant = [it for it in needs_up if it["raw_scale"] > mild_cutoff]

                for it in needs_up_mild:
                    decisions[it["key"]] = True

                st.write(
                    f"**{len(fine)}** image(s) are already large enough -- no stretching. "
                    f"**{len(needs_up_mild)}** need only a small enlarge (≤{mild_threshold_pct}%) "
                    f"and are approved automatically. **{len(needs_up_significant)}** need a "
                    f"bigger enlarge and are reviewed below. **{len(errors)}** failed to download."
                )

                needs_up_square = [it for it in needs_up_significant if it["orig_w"] == it["orig_h"]]
                needs_up_other = [it for it in needs_up_significant if it["orig_w"] != it["orig_h"]]

                show_square_detail = False
                if needs_up_square:
                    with st.container(border=True):
                        st.markdown(
                            f"**{len(needs_up_square)} image(s) are square (same width and "
                            "height) and need a noticeable enlarge.**"
                        )
                        st.warning(
                            "Enlarging a square photo keeps its proportions exactly the same -- "
                            "at normal size the softness this adds usually isn't visible to the "
                            "naked eye, though it can show up if someone zooms in closely (e.g. "
                            "Amazon's own zoom). Do you want these enlarged automatically?"
                        )
                        square_choice = st.radio(
                            "Square images that need a noticeable enlarge",
                            ["Yes, enlarge them automatically", "No, let me check each one myself"],
                            key=f"lt_sq_choice_{st.session_state['lt_pv_ver']}",
                        )
                        if square_choice.startswith("Yes"):
                            for it in needs_up_square:
                                decisions[it["key"]] = True
                        else:
                            show_square_detail = True

                detail_items = list(needs_up_other)
                if show_square_detail:
                    detail_items += needs_up_square

                if detail_items:
                    st.markdown("**Review these (sorted by how much they'd need to stretch)**")

                    groups = {}
                    for it in detail_items:
                        groups.setdefault((it["orig_w"], it["orig_h"]), []).append(it)
                    group_list = sorted(groups.items(), key=lambda kv: -kv[1][0]["raw_scale"])

                    bulk = st.radio(
                        "For everything in the table below:",
                        ["Decide for each row myself", "Enlarge all of them", "Keep all of them at original size"],
                        horizontal=True,
                        key=f"lt_bulk_{st.session_state['lt_pv_ver']}",
                    )
                    bulk_default = bulk == "Enlarge all of them"

                    table_rows = [
                        {
                            "Dimensions": f"{ow}×{oh}px",
                            "Scale": f"x{group_items[0]['raw_scale']:.2f}",
                            "Count": len(group_items),
                            "Enlarge": bulk_default if bulk != "Decide for each row myself" else False,
                        }
                        for (ow, oh), group_items in group_list
                    ]
                    df_groups = pd.DataFrame(table_rows)
                    edited_groups = st.data_editor(
                        df_groups,
                        hide_index=True, width="stretch",
                        column_config={
                            "Dimensions": st.column_config.TextColumn("Dimensions", disabled=True),
                            "Scale": st.column_config.TextColumn("Enlarge factor", disabled=True),
                            "Count": st.column_config.NumberColumn("Images this size", disabled=True),
                            "Enlarge": st.column_config.CheckboxColumn(
                                "Enlarge to fill square? (may look soft)"
                            ),
                        },
                        key=f"lt_group_table_{st.session_state['lt_pv_ver']}_{bulk}",
                    )
                    for (ow, oh), group_items in group_list:
                        row = edited_groups[
                            edited_groups["Dimensions"] == f"{ow}×{oh}px"
                        ]
                        enlarge_val = bool(row["Enlarge"].iloc[0]) if not row.empty else False
                        for it in group_items:
                            decisions[it["key"]] = enlarge_val

                    zoom_options = [
                        f"{ow}×{oh}px (x{group_items[0]['raw_scale']:.2f})"
                        for (ow, oh), group_items in group_list
                    ]
                    zoom_choice = st.selectbox(
                        "Zoom in on a specific size to compare closely (stays on this page):",
                        ["-- choose a size --"] + zoom_options,
                        key=f"lt_zoom_pick_{st.session_state['lt_pv_ver']}",
                    )
                    if zoom_choice != "-- choose a size --":
                        idx = zoom_options.index(zoom_choice)
                        (ow, oh), group_items = group_list[idx]
                        rep = group_items[0]
                        crop_orig, crop_enl = zoom_compare_crops(
                            rep["raw"], int(target_size), ow, oh,
                        )
                        zc1, zc2 = st.columns(2)
                        _render_image(zc1, crop_orig, caption="Close-up: original, not enlarged")
                        _render_image(
                            zc2, crop_enl,
                            caption=f"Close-up: enlarged x{rep['raw_scale']:.2f} -- look for softness",
                        )
                        st.caption(
                            "This close-up is cropped and zoomed in from one image this size, "
                            "so softness from enlarging is actually visible. The same scale "
                            "applies to every image in that row of the table."
                        )

            if errors:
                st.markdown("**Failed to download**")
                for it in errors:
                    st.error(f"{it.get('name') or it['url']}: {it['error']}")

            if st.button("Download images and build ZIP", type="primary", disabled=len(ok_items) == 0):
                with st.spinner("Preparing your ZIP..."):
                    zip_bytes, report = finalize_zip(preview, settings, pad=pad, decisions=decisions)
                st.session_state["lt_result"] = (zip_bytes, report)

            result = st.session_state.get("lt_result")
            if result:
                zip_bytes, report = result
                ok = int((report["Status"] == "OK").sum())
                warn = int((report["Status"] == "WARNING").sum())
                failed = int((report["Status"] == "FAILED").sum())
                m1, m2, m3 = st.columns(3)
                m1.metric("Ready", ok)
                m2.metric("With warnings", warn)
                m3.metric("Failed", failed)
                shown = report.copy()
                shown["Status"] = shown["Status"].map(status_label)
                st.dataframe(shown, width="stretch", hide_index=True)
                if ok + warn > 0:
                    st.download_button(
                        "Download ZIP", data=zip_bytes,
                        file_name="prepared_images.zip", mime="application/zip",
                        type="primary",
                    )