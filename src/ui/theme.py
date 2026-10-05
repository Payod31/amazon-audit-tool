import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');
:root{--bg:#0A0F1C;--bg2:#0E1424;--panel:#121A2C;--panel2:#18223A;--line:#26324F;--text:#E8ECF6;--muted:#93A0BF;--amber:#F5A04A;--teal:#3FE0C0;--red:#FF6B7A;}
html,body,.stApp,[data-testid="stAppViewContainer"]{font-family:'Inter',sans-serif;font-size:16px;}
.stApp{background:radial-gradient(900px 480px at 88% -8%,rgba(63,224,192,.11),transparent 60%),radial-gradient(800px 460px at 0% 0%,rgba(245,160,74,.09),transparent 55%),var(--bg);color:var(--text);}
.block-container{max-width:1180px;padding:2.4rem 2rem 4rem;}
h1,h2,h3,h4,h5{font-family:'Space Grotesk',sans-serif!important;letter-spacing:-.02em;color:var(--text);}
[data-testid="stHeader"]{background:transparent;}
[data-testid="stAppDeployButton"],.stDeployButton{display:none;}
button[title="View fullscreen"],button[aria-label="View fullscreen"],[data-testid="StyledFullScreenButton"],[data-testid="baseButton-elementToolbar"],div[data-testid="stImage"] button,div[data-testid="stImage"] [role="button"]{display:none!important;}
section[data-testid="stSidebar"]{background:var(--bg2);border-right:1px solid var(--line);}
section[data-testid="stSidebar"] .stButton>button{justify-content:flex-start;background:transparent;border:1px solid transparent;color:var(--muted);font-weight:500;padding:.6rem .85rem;border-radius:10px;width:100%;}
section[data-testid="stSidebar"] .stButton>button:hover{background:var(--panel2);color:var(--text);border-color:transparent;}
section[data-testid="stSidebar"] .stButton>button p{text-align:left;width:100%;}
.stButton>button,.stDownloadButton>button,[data-testid="stDownloadButton"] button{border-radius:10px;border:1px solid var(--line);background:var(--panel2);color:var(--text);font-weight:600;padding:.6rem 1.1rem;transition:border-color .15s,color .15s;}
.stButton>button:hover,.stDownloadButton>button:hover,[data-testid="stDownloadButton"] button:hover{border-color:var(--teal);color:var(--teal);}
button[kind="primary"],button[data-testid="stBaseButton-primary"]{background:linear-gradient(135deg,#3FE0C0,#2BB3D6)!important;color:#04141A!important;border:0!important;}
button[kind="primary"]:hover,button[data-testid="stBaseButton-primary"]:hover{filter:brightness(1.08);color:#04141A!important;}
[data-baseweb="input"],[data-baseweb="textarea"],[data-baseweb="select"]>div{background:var(--panel2)!important;border-radius:10px!important;border-color:var(--line)!important;}
[data-testid="stFileUploaderDropzone"]{background:var(--panel2);border:1.5px dashed var(--line);border-radius:14px;}
[data-testid="stVerticalBlockBorderWrapper"]{background:var(--panel);border:1px solid var(--line)!important;border-radius:18px!important;}
[data-testid="stMetric"]{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:.9rem 1.1rem;}
[data-testid="stMetricValue"]{font-family:'Space Grotesk',sans-serif;}
[data-testid="stDataFrame"],[data-testid="stDataEditor"]{border-radius:12px;overflow:hidden;}
[data-testid="stAlert"]{border-radius:12px;}
[data-testid="stExpander"]{border:1px solid var(--line)!important;border-radius:12px!important;background:var(--panel2);}
[data-baseweb="tab-list"]{gap:.4rem;border-bottom:1px solid var(--line);}
button[data-baseweb="tab"]{font-weight:600;color:var(--muted);padding:.65rem 1.1rem;}
button[data-baseweb="tab"][aria-selected="true"]{color:var(--text);}
[data-baseweb="tab-highlight"]{background:var(--teal)!important;height:3px;border-radius:3px;}

.logo-row{display:flex;align-items:center;gap:.75rem;padding:.2rem 0 1rem;}
.logo-mark{width:38px;height:38px;border-radius:11px;background:linear-gradient(135deg,#F5A04A,#3FE0C0);color:#08111C;font:700 1.2rem 'Space Grotesk',sans-serif;display:grid;place-items:center;}
.logo-name{font:700 1.15rem 'Space Grotesk',sans-serif;}
.logo-sub{color:var(--muted);font-size:.8rem;}
.nav-active{background:var(--panel2);border:1px solid var(--line);border-left:3px solid var(--teal);border-radius:10px;padding:.6rem .85rem;font-weight:600;margin-bottom:.25rem;}
.side-status{color:var(--muted);font-size:.82rem;margin-top:2rem;display:flex;align-items:center;gap:.5rem;}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block;}
.dot-off{background:var(--amber);}
.hero{display:grid;grid-template-columns:1.25fr 1fr;gap:2rem;align-items:center;background:linear-gradient(135deg,rgba(63,224,192,.08),rgba(245,160,74,.06)),var(--panel);border:1px solid var(--line);border-radius:24px;padding:2.4rem 2.4rem;margin-bottom:1.6rem;}
.hero h1{font-size:2.7rem;line-height:1.1;margin:.9rem 0 .8rem;}
.hero p{color:var(--muted);font-size:1.05rem;line-height:1.55;max-width:34rem;margin:0;}
.hero-art{display:flex;align-items:center;justify-content:center;gap:1.1rem;}
.art-col{display:flex;flex-direction:column;align-items:center;gap:.6rem;color:var(--muted);font-size:.8rem;text-align:center;}
.art-before{width:150px;height:96px;border-radius:10px;background:linear-gradient(135deg,#3A4A6B,#243049);display:grid;place-items:center;}
.art-after{width:140px;height:140px;border-radius:10px;background:#fff;display:grid;place-items:center;box-shadow:0 12px 40px rgba(0,0,0,.4);}
.art-obj{width:62%;height:62%;border-radius:8px;background:linear-gradient(135deg,#F5A04A,#E8704A);}
.art-after .art-obj{width:76%;height:46%;}
.art-arrow{font-size:1.8rem;color:var(--teal);}
.pill{display:inline-block;padding:.22rem .7rem;border-radius:999px;font-size:.8rem;font-weight:500;background:var(--panel2);border:1px solid var(--line);color:var(--muted);}
.pill-teal{color:var(--teal);border-color:rgba(63,224,192,.4);background:rgba(63,224,192,.08);}
.pill-amber{color:var(--amber);border-color:rgba(245,160,74,.4);background:rgba(245,160,74,.08);}
.pill-row{display:flex;flex-wrap:wrap;gap:.45rem;margin:.2rem 0 1rem;}
.chip{width:42px;height:42px;border-radius:12px;display:grid;place-items:center;font-size:1.3rem;margin-bottom:.8rem;}
.chip-amber{background:rgba(245,160,74,.15);}
.chip-teal{background:rgba(63,224,192,.15);}
.tool-card-title{font:700 1.35rem 'Space Grotesk',sans-serif;margin:0 0 .35rem;}
.tool-card-desc{color:var(--muted);line-height:1.5;margin:0 0 .9rem;}
.how{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin:.4rem 0 1.4rem;}
.how-item{border-left:2px solid var(--line);padding:.2rem 0 .2rem 1rem;}
.how-item b{font-family:'Space Grotesk',sans-serif;font-size:1.05rem;}
.how-item span{display:block;color:var(--muted);font-size:.92rem;margin-top:.25rem;line-height:1.45;}
.section-title{font:600 1.2rem 'Space Grotesk',sans-serif;margin:1.8rem 0 .8rem;}

.page-head{display:flex;align-items:center;gap:1rem;margin-bottom:1.4rem;}
.page-head .chip{margin:0;width:50px;height:50px;font-size:1.5rem;}
.page-head h2{margin:0;font-size:1.9rem;}
.page-head p{margin:.15rem 0 0;color:var(--muted);}
.step-head{display:flex;align-items:flex-start;gap:.85rem;margin-bottom:.8rem;}
.step-badge{min-width:30px;height:30px;border-radius:50%;background:var(--teal);color:#04141A;font:700 .95rem 'Space Grotesk',sans-serif;display:grid;place-items:center;margin-top:.1rem;}
.step-title{font:600 1.2rem 'Space Grotesk',sans-serif;}
.step-hint{color:var(--muted);font-size:.92rem;line-height:1.45;margin-top:.1rem;}
.ring{width:130px;height:130px;border-radius:50%;background:conic-gradient(var(--c) calc(var(--p)*1%),var(--line) 0);display:grid;place-items:center;margin:.3rem auto;}
.ring-in{width:100px;height:100px;border-radius:50%;background:var(--panel);display:grid;place-items:center;font:700 2rem 'Space Grotesk',sans-serif;}
.ring-label{text-align:center;color:var(--muted);font-size:.85rem;}
@media(max-width:900px){.hero{grid-template-columns:1fr;}.how{grid-template-columns:1fr;}}
</style>
"""

def inject_theme():
    st.markdown(CSS, unsafe_allow_html=True)

def page_header(icon, title, subtitle, accent="teal"):
    st.markdown(
        f"<div class='page-head'><div class='chip chip-{accent}'>{icon}</div>"
        f"<div><h2>{title}</h2><p>{subtitle}</p></div></div>",
        unsafe_allow_html=True,
    )

def step_head(num, title, hint=""):
    st.markdown(
        f"<div class='step-head'><div class='step-badge'>{num}</div>"
        f"<div><div class='step-title'>{title}</div>"
        f"<div class='step-hint'>{hint}</div></div></div>",
        unsafe_allow_html=True,
    )

def score_ring(score):
    try:
        value = max(0, min(100, float(score)))
    except (TypeError, ValueError):
        value = 0
    color = "var(--teal)" if value >= 80 else "var(--amber)" if value >= 50 else "var(--red)"
    st.markdown(
        f"<div class='ring' style='--p:{value:.0f};--c:{color}'>"
        f"<div class='ring-in'>{value:.0f}</div></div>"
        f"<div class='ring-label'>out of 100</div>",
        unsafe_allow_html=True,
    )

_STATUS = {
    "PASS": "✅ Pass", "OK": "✅ OK",
    "FAIL": "❌ Fail", "FAILED": "❌ Failed",
    "WARN": "⚠️ Warning", "WARNING": "⚠️ Warning",
    "REVIEW": "🔍 Review", "UNKNOWN": "❔ Unknown",
}

def status_label(status):
    return _STATUS.get(str(status).strip().upper(), str(status))