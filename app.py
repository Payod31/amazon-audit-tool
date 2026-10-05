import tempfile

import pandas as pd
import streamlit as st

from src.audit_runner import audit_all
from src.providers.csv_provider import CsvProvider
from src.report import build_excel_bytes
from src.ui.image_match_ui import render_image_match_tool
from src.ui.link_template_ui import render_link_template_tool
from src.ui.masterfile_ui import render_masterfile_tool
from src.ui.reorganize_links_ui import render_reorganize_links_tool
from src.ui.theme import inject_theme, page_header, score_ring, status_label

st.set_page_config(page_title="ASIN Forge", page_icon="🛠️", layout="wide")
inject_theme()

if "page" not in st.session_state:
    st.session_state.page = "home"

def go(page):
    st.session_state.page = page

AUDIT_COLUMNS = [
    "asin", "marketplace", "language", "title",
    "bullet_1", "bullet_2", "bullet_3", "bullet_4", "bullet_5",
    "description", "brand", "price", "rating", "review_count",
    "image_count", "has_aplus", "buy_box_seller", "fulfilled_by",
    "image_urls", "main_image_url", "has_video",
    "aplus_basic_desktop_urls", "aplus_premium_desktop_urls", "aplus_premium_mobile_urls",
]

NAV_ITEMS = [
    ("home", "🏠", "Home"),
    ("audit", "🔎", "Audit listings"),
    ("image_prep", "🖼️", "Image prep"),
    ("masterfile", "🧩", "Masterfile"),
    ("image_match", "🔍", "Image match check"),
]

with st.sidebar:
    st.markdown(
        "<div class='logo-row'><div class='logo-mark'>A</div><div>"
        "<div class='logo-name'>ASIN Forge</div>"
        "<div class='logo-sub'>Amazon listing tools</div></div></div>",
        unsafe_allow_html=True,
    )
    for key, icon, label in NAV_ITEMS:
        if st.session_state.page == key:
            st.markdown(f"<div class='nav-active'>{icon}&nbsp; {label}</div>", unsafe_allow_html=True)
        elif st.button(f"{icon}  {label}", key=f"nav_{key}"):
            go(key)
            st.rerun()
    st.markdown(
        "<div class='side-status'><span class='dot dot-off'></span>"
        "Live ASIN lookup: not connected</div>",
        unsafe_allow_html=True,
    )

def load_provider(columns, key_prefix):
    """Upload a CSV or use the sample data. Returns a CsvProvider, or None."""
    st.markdown("##### Load listing data")

    col_a, col_b = st.columns(2, gap="large")

    with col_a:
        uploaded = st.file_uploader(
            "Drag and drop a CSV, or click to browse",
            type="csv", key=f"{key_prefix}_upload",
        )
    with col_b:
        pasted = st.text_area(
            "Paste ASINs, one per line",
            height=120, key=f"{key_prefix}_paste",
            placeholder="B00EZ6YM44\nB07XJ8C8F5",
            disabled=True,
        )
        st.caption(
            "🚧 Work in progress: looking up ASINs automatically needs a "
            "data API key, so it can't be used yet."
        )

    use_sample = st.checkbox("Use the sample data instead", key=f"{key_prefix}_sample")

    path = None

    if uploaded is not None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            tmp.write(uploaded.getvalue())
            path = tmp.name

    elif pasted.strip():
        asins = [a.strip().upper() for a in pasted.splitlines() if a.strip()]
        rows = []
        for a in asins:
            row = {c: "" for c in columns}
            row["asin"] = a
            if "marketplace" in row:
                row["marketplace"] = "amazon_us"
            if "language" in row:
                row["language"] = "en-US"
            rows.append(row)
        edited = st.data_editor(
            pd.DataFrame(rows), num_rows="dynamic", width="stretch",
            key=f"{key_prefix}_editor",
        )
        edited = edited[edited["asin"].astype(str).str.strip() != ""]
        if not edited.empty:
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=".csv", mode="w", encoding="utf-8", newline=""
            ) as tmp:
                tmp.write(edited.to_csv(index=False))
                path = tmp.name

    elif use_sample:
        path = "sample_data/sample_listings.csv"

    if path is None:
        st.info("Upload a CSV or tick the sample box to continue.")
        return None

    try:
        return CsvProvider(path)
    except Exception as e:
        st.error(f"Could not read the data: {e}")
        return None

HERO_HTML = "".join([
    "<div class='hero'><div>",
    "<span class='pill pill-teal'>Works today with your own image links and CSV files</span>",
    "<h1>Get your Amazon listings ready to publish</h1>",
    "<p>Check a listing against Amazon's rules, then prepare its images to the exact size, "
    "background and file name Amazon expects.</p></div>",
    "<div class='hero-art'>",
    "<div class='art-col'><div class='art-before'><div class='art-obj'></div></div>Your photo<br>1500 × 900</div>",
    "<div class='art-arrow'>›</div>",
    "<div class='art-col'><div class='art-after'><div class='art-obj'></div></div>White square<br>2000 × 2000</div>",
    "</div></div>",
])

HOW_HTML = "".join([
    "<div class='section-title'>How it works</div><div class='how'>",
    "<div class='how-item'><b>1. Add your data</b><span>Paste image links into a table, upload a CSV, or use the sample listings.</span></div>",
    "<div class='how-item'><b>2. Run the tool</b><span>Audit scores the listing. Image prep downloads, pads and renames the images.</span></div>",
    "<div class='how-item'><b>3. Take the result</b><span>Download a ZIP of finished images or an Excel report with fixes.</span></div>",
    "</div>",
])

PLANNED_HTML = "".join([
    "<div class='section-title'>Planned next</div><div class='pill-row'>",
    "<span class='pill'>Live ASIN lookup</span><span class='pill'>Buy Box and competitor view</span>",
    "<span class='pill'>Review themes</span><span class='pill'>AI copy rewrites</span>",
    "<span class='pill'>Bulk mode</span><span class='pill'>PDF reports</span></div>",
])

def render_home():
    st.markdown(HERO_HTML, unsafe_allow_html=True)

    cols = st.columns(2, gap="large")

    with cols[0]:
        with st.container(border=True):
            st.markdown(
                "<div class='chip chip-amber'>🔎</div>"
                "<p class='tool-card-title'>Audit listings</p>"
                "<p class='tool-card-desc'>Score a listing out of 100 on title, bullets, images, "
                "A+ Content and rating, with a specific fix for every issue.</p>"
                "<div class='pill-row'><span class='pill pill-amber'>Score out of 100</span>"
                "<span class='pill'>Excel report</span></div>",
                unsafe_allow_html=True,
            )
            if st.button("Open audit", key="open_audit", width="stretch"):
                go("audit")
                st.rerun()

    with cols[1]:
        with st.container(border=True):
            st.markdown(
                "<div class='chip chip-teal'>🖼️</div>"
                "<p class='tool-card-title'>Image prep</p>"
                "<p class='tool-card-desc'>Download images from your links and pad them onto a pure "
                "white square. No cropping, no stretching, named the way you choose.</p>"
                "<div class='pill-row'><span class='pill pill-teal'>White background</span>"
                "<span class='pill'>Under 10MB</span><span class='pill'>ZIP download</span></div>",
                unsafe_allow_html=True,
            )
            if st.button("Open image prep", key="open_prep", width="stretch"):
                go("image_prep")
                st.rerun()

    st.markdown(HOW_HTML, unsafe_allow_html=True)
    st.markdown(PLANNED_HTML, unsafe_allow_html=True)

def render_audit():
    page_header("🔎", "Audit listings",
                "Score a listing out of 100 and see exactly what to fix.", "amber")
    provider = load_provider(AUDIT_COLUMNS, "audit")
    if provider is None or not provider.list_asins():
        return

    st.divider()
    summary, issues = audit_all(provider)
    summary_df = pd.DataFrame(summary)
    issues_df = pd.DataFrame(issues)

    scores = pd.to_numeric(summary_df["Score (/100)"], errors="coerce")
    to_fix = int((~issues_df["Status"].astype(str).str.upper().isin(
        ["PASS", "OK", "UNKNOWN", "REVIEW"])).sum())
    m1, m2, m3 = st.columns(3)
    m1.metric("Listings audited", len(summary_df))
    m2.metric("Average score", f"{scores.mean():.0f} / 100")
    m3.metric("Issues to fix", to_fix)

    st.markdown("##### Summary")
    st.dataframe(summary_df, width="stretch", hide_index=True)

    st.markdown("##### Issues and fixes")
    choice = st.selectbox("Choose a listing", summary_df["ASIN"].tolist())
    one = issues_df[issues_df["ASIN"] == choice]
    score = summary_df.loc[summary_df["ASIN"] == choice, "Score (/100)"].iloc[0]

    left, right = st.columns([1, 3], gap="large")
    with left:
        with st.container(border=True):
            score_ring(score)
    with right:
        shown = one[["Check", "Status", "Severity", "Finding", "Fix"]].copy()
        shown["Status"] = shown["Status"].map(status_label)
        st.dataframe(shown, width="stretch", hide_index=True)

    st.download_button(
        "Download Excel report",
        data=build_excel_bytes(summary, issues),
        file_name="audit_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )

def render_image_prep():
    page_header("🖼️", "Image prep",
                "Turn your image links into clean, correctly named listing images.", "teal")
    tab_links, tab_reorg = st.tabs(
        ["From image links", "Reorganize links"]
    )
    with tab_links:
        render_link_template_tool()
    with tab_reorg:
        render_reorganize_links_tool()

def render_masterfile():
    page_header("🧩", "Masterfile",
                "Learn Amazon masterfiles and copy their product data into blank templates.", "amber")
    render_masterfile_tool()

def render_image_match():
    page_header("🔍", "Image match check",
                "Check whether a product's main image actually matches its name.", "teal")
    render_image_match_tool()

PAGES = {
    "home": render_home,
    "audit": render_audit,
    "image_prep": render_image_prep,
    "masterfile": render_masterfile,
    "image_match": render_image_match,
}
PAGES[st.session_state.page]()