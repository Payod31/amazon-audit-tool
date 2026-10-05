"""
UI for the 'Masterfile' page: two related tools --

1. Learn a masterfile -- upload an Amazon flat-file masterfile (.xlsx or
   .xlsm) and store its schema (labels, required levels, dropdown values)
   per product type, merging into whatever is already on record.
   TEMPORARILY DISABLED -- see ENABLE_LEARN_MASTERFILE_TAB below.
2. Amplifi template -- upload a FILLED file (a masterfile or an Amplifi
   import with real product data) and its data gets copied into the
   stored blank template, labeled for whichever Amazon marketplace you
   pick. Operational columns (Collection Folder, Import Type, Roles,
   ...) in the blank template are never touched -- those are filled by
   the user's own team.
3. SEO requirements check -- pick whether the masterfile is for creating
   a new product, a full update, or a partial update (a partial update
   skips the "this field is blank" findings, since that's expected there),
   then upload an Amazon masterfile (not an Amplifi file) and check its
   Item Name, Bullet Points, Product Description and Generic Keywords
   against Amazon's general style-guide rules. Every issue is written
   back as a cell comment on a downloadable copy of the same masterfile.

Nothing here talks to Amazon or Seller Central. Everything is a file the
user already has; this only reorganizes/copies/checks data in files.
"""

import os

import pandas as pd
import streamlit as st

from src.masterfile.fill_template import (
    DEFAULT_BLANK_TEMPLATE_PATH,
    extract_filled_rows,
    fill_blank_template,
    load_default_blank_template,
    save_default_blank_template,
)
from src.masterfile.marketplaces import (
    country_for_label,
    default_label,
    locale_for_country,
    marketplace_labels,
)
from src.masterfile.schema import list_stored_product_types, parse_masterfile, save_schema
from src.masterfile.seo_check import (
    check_and_annotate_masterfile,
    default_mode_label,
    mode_help_for_label,
    mode_key_for_label,
    mode_labels,
    summarize_by_sku,
)

# Flip this back to True to bring the "Learn a masterfile" tab back --
# it's hidden for now because it doesn't match the current requirement.
# The tab's code below is untouched, so re-enabling is just this one flag.
ENABLE_LEARN_MASTERFILE_TAB = False


def _learn_masterfile_section():
    st.subheader("Learn a masterfile")
    st.info(
        "Upload an Amazon masterfile (the flat-file export from Seller Central's "
        "bulk upload tool) to store its field labels, required levels and real "
        "dropdown values for its product type. Uploading the same product type "
        "again merges in anything new rather than starting over."
    )

    stored = list_stored_product_types()
    if stored:
        st.caption(f"Already on record: {', '.join(stored)}")

    upload = st.file_uploader(
        "Upload a masterfile (.xlsx or .xlsm)",
        type=["xlsx", "xlsm"],
        key="mf_learn_upload",
    )
    if upload is None:
        return

    try:
        schema = parse_masterfile(upload.getvalue(), upload.name)
    except Exception as e:
        st.error(f"Could not read this as an Amazon masterfile: {e}")
        return

    from collections import Counter
    req_counts = Counter(f.required_level for f in schema.fields)
    with_dropdown = sum(1 for f in schema.fields if f.dropdown_values)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Product type(s)", ", ".join(schema.product_types))
    m2.metric("Fields", len(schema.fields))
    m3.metric("With dropdown values", with_dropdown)
    m4.metric("Sections", len(schema.groups()))
    st.caption("Required-level breakdown: " + ", ".join(f"{k}: {v}" for k, v in req_counts.items()))

    if st.button("Store this schema", type="primary", key="mf_learn_save"):
        reports = save_schema(schema)
        for r in reports:
            verb = "Stored new" if r.is_new else "Merged into existing"
            st.success(
                f"{verb} schema for {r.product_type}: {r.total_fields} fields total "
                f"({len(r.added_fields)} added, {len(r.changed_fields)} updated)."
            )


def _fill_template_section():
    st.subheader("Amplifi template")
    st.info(
        "Upload a FILLED file (a masterfile or an Amplifi import that already has "
        "real product data in it) and its data gets copied straight into the "
        "stored blank template -- just the masterfile is needed. Only "
        "product-attribute columns are copied; Collection Folder, Import Type, "
        "Roles and the other operational columns in the blank template are left "
        "exactly as they are, for your team to fill in."
    )

    labels = marketplace_labels()
    chosen_label = st.selectbox(
        "Which Amazon marketplace is this masterfile for?",
        labels,
        index=labels.index(default_label()),
        key="mf_fill_country",
        help=(
            "Decides the locale the attribute columns get labeled with in the "
            "filled template -- e.g. '- en-US' for the US, '- de-DE' for "
            "Germany, '- fr-FR' for France. Pick the marketplace the uploaded "
            "masterfile's data actually belongs to, not just the default."
        ),
    )
    country_code = country_for_label(chosen_label)
    locale = locale_for_country(country_code)
    st.caption(f"Attribute columns will be labeled for locale: {locale}")

    blank_bytes, blank_name = None, os.path.basename(DEFAULT_BLANK_TEMPLATE_PATH)
    try:
        blank_bytes = load_default_blank_template()
        st.caption(f"Target template on file: {blank_name}")
    except FileNotFoundError as e:
        st.error(str(e))

    with st.expander("Use a different blank template instead", expanded=False):
        override_upload = st.file_uploader(
            "Upload a replacement blank template",
            type=["xlsx", "xlsm"],
            key="mf_fill_target_override",
        )
        if override_upload is not None:
            blank_bytes = override_upload.getvalue()
            blank_name = override_upload.name
            st.caption(f"Using {blank_name} for this run instead of the stored template.")
            if st.checkbox(
                "Also replace the stored default with this one",
                key="mf_fill_target_save_default",
            ):
                save_default_blank_template(blank_bytes)
                st.success(f"Stored template replaced with {blank_name}.")

    filled_upload = st.file_uploader(
        "Filled source file (masterfile or Amplifi import)",
        type=["xlsx", "xlsm"],
        key="mf_fill_source",
        help="A masterfile or Amplifi file that already has one or more products filled in.",
    )

    if filled_upload is None or blank_bytes is None:
        st.caption("Waiting for the filled source file.")
        return

    try:
        rows, kind = extract_filled_rows(filled_upload.getvalue(), filled_upload.name)
    except Exception as e:
        st.error(f"Could not read the filled source file: {e}")
        return

    kind_label = "Amazon masterfile" if kind == "amazon_masterfile" else "Amplifi import"
    st.caption(f"Source recognized as: {kind_label}. Found {len(rows)} filled product row(s).")

    if not rows:
        st.warning("No filled product rows were found in the source file.")
        return

    with st.expander(f"Preview the {len(rows)} row(s) that will be copied", expanded=False):
        for i, row in enumerate(rows):
            sku = next((v for k, v in row.items() if "sku" in k.lower()), None)
            name = next((v for k, v in row.items() if "item_name" in k.lower()), None)
            st.caption(f"Row {i+1}: {sku or '(no SKU found)'} -- {name or ''} -- {len(row)} field(s) filled")

    if st.button("Fill the blank template", type="primary", key="mf_fill_run"):
        try:
            out_bytes = fill_blank_template(blank_bytes, rows, header_suffix=f" - {locale}")
        except Exception as e:
            st.error(f"Could not fill the template: {e}")
            return
        st.success(f"Filled {len(rows)} row(s) into the template.")
        st.download_button(
            "Download filled template",
            data=out_bytes,
            file_name=f"filled_{blank_name}",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="mf_fill_download",
        )


def _seo_check_section():
    st.subheader("SEO requirements check")
    st.info(
        "Upload an Amazon masterfile (the Seller Central flat-file export -- "
        "not an Amplifi file) and this checks every product row's Item Name, "
        "Bullet Points (Key Product Features), Product Description and "
        "Generic Keywords against Amazon's general style-guide rules -- "
        "length limits, promotional language, HTML, contact info, and so on. "
        "Every issue is written as a comment directly on the cell it's "
        "about, in a copy of the same masterfile, so you can open it and "
        "see exactly what to fix. Exact limits can vary by category, so "
        "treat this as a first-pass check, not a guarantee Amazon will "
        "approve the listing. Nothing here is sent to Seller Central -- it "
        "only reads the file you upload."
    )

    labels = mode_labels()
    chosen_mode_label = st.radio(
        "What is this masterfile for?",
        labels,
        index=labels.index(default_mode_label()),
        key="mf_seo_mode",
        help=(
            "A field being mandatory in Amazon's schema doesn't mean it has to be "
            "filled in THIS file -- a partial update legitimately leaves untouched "
            "fields (brand, parentage, and sometimes the SEO fields too) blank, "
            "inherited from whatever's already live. Creating a new product or "
            "doing a full update is expected to carry everything."
        ),
    )
    st.caption(mode_help_for_label(chosen_mode_label))
    mode = mode_key_for_label(chosen_mode_label)

    upload = st.file_uploader(
        "Upload an Amazon masterfile (.xlsx or .xlsm) -- not an Amplifi file",
        type=["xlsx", "xlsm"],
        key="mf_seo_upload",
    )
    if upload is None:
        return

    try:
        findings, skus_checked, annotated_bytes = check_and_annotate_masterfile(
            upload.getvalue(), upload.name, mode=mode,
        )
    except Exception as e:
        st.error(f"Could not check this file: {e}")
        return

    if not skus_checked:
        st.warning("No filled product rows were found in this file.")
        return

    summary_rows = summarize_by_sku(findings, skus_checked)
    summary_df = pd.DataFrame(summary_rows)

    blocked = sum(1 for r in summary_rows if r["Status"] == "Blocked")
    total_errors = sum(r["Errors"] for r in summary_rows)
    total_warnings = sum(r["Warnings"] for r in summary_rows)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Products checked", len(summary_rows))
    m2.metric("Blocked (hard errors)", blocked)
    m3.metric("Total errors", total_errors)
    m4.metric("Total warnings", total_warnings)

    is_xlsm = upload.name.lower().endswith(".xlsm")
    mime = (
        "application/vnd.ms-excel.sheet.macroEnabled.12" if is_xlsm
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    st.success(
        f"Checked {len(summary_rows)} product(s). Every issue below has been written "
        "as a comment on the exact cell it's about, in the file below -- open it in "
        "Excel (or Google Sheets) and look for the little red/orange triangle in the "
        "top-right corner of a cell to see the note."
    )
    st.download_button(
        "⬇ Download your masterfile with comments added",
        data=annotated_bytes,
        file_name=f"commented_{upload.name}",
        mime=mime,
        type="primary",
        key="mf_seo_download_annotated",
        width="stretch",
    )

    st.markdown("##### Per-product status (preview -- open the downloaded file for the full comments)")
    st.dataframe(summary_df, width="stretch", hide_index=True)

    st.markdown("##### Detailed findings (preview only -- these are the comments added to the file above)")
    sku_choice = st.selectbox(
        "Choose a SKU", [r["SKU"] for r in summary_rows], key="mf_seo_sku_choice",
    )
    detail = [f.to_dict() for f in findings if f.sku == sku_choice]
    if detail:
        st.dataframe(pd.DataFrame(detail), width="stretch", hide_index=True)
    else:
        st.success("No issues found for this SKU.")


def render_masterfile_tool():
    tab_defs = []
    if ENABLE_LEARN_MASTERFILE_TAB:
        tab_defs.append(("Learn a masterfile", _learn_masterfile_section))
    tab_defs.append(("Amplifi template", _fill_template_section))
    tab_defs.append(("SEO requirements check", _seo_check_section))

    tabs = st.tabs([label for label, _ in tab_defs])
    for tab, (_, renderer) in zip(tabs, tab_defs):
        with tab:
            renderer()