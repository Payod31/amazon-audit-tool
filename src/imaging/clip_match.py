"""
Free, local alternative to a hosted vision API for the image match check --
no API key, no per-call cost, and nothing leaves this machine once the
model weights are cached.

Uses OpenAI's open-source CLIP model (via Hugging Face's `transformers`)
to score how well a product image and a text name belong together, as a
cosine similarity in roughly [0.1, 0.35] for real product photos. This is
NOT the same kind of reasoning a vision-capable LLM does -- it can't
explain itself in words, and it's noticeably weaker at catching subtle
mismatches (right general category but wrong color/model, for example).
Treat it as a free first pass, not a guarantee.

Requires `torch`, `transformers` and `pillow` installed on the server
running this app -- these are NOT in requirements.txt by default because
they're a heavy addition (torch alone is ~200 MB+). Install with:

    pip install --index-url https://download.pytorch.org/whl/cpu torch
    pip install transformers pillow

The first call on a given machine downloads the model weights (~600 MB)
from Hugging Face and caches them under ~/.cache/huggingface -- every
call after that loads instantly from disk and runs fully offline.

Thresholds below were picked from manually checking real Amazon product
photos against correct and incorrect names: a genuine match usually lands
around 0.24-0.32 cosine similarity, a clear mismatch usually lands around
0.15-0.20. The gap between is deliberately called "Unsure" rather than
forced into Yes/No -- CLIP's absolute scores are noisy enough that a hard
cutoff there would be overconfident. Adjust the thresholds in the UI if
your own results run consistently higher or lower than that.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from src.imaging.image_match import MatchRow, fetch_image

MODEL_NAME = "openai/clip-vit-base-patch32"

DEFAULT_YES_THRESHOLD = 0.24
DEFAULT_NO_THRESHOLD = 0.19

_model = None
_processor = None
_load_error: str | None = None


def _get_model():
    """Loads the CLIP model once per server process and reuses it after
    that -- the first call pays the import/download/load cost, every call
    after is instant (module-level cache)."""
    global _model, _processor, _load_error
    if _model is not None or _load_error is not None:
        return _model, _processor, _load_error

    try:
        import torch  # noqa: F401  (import check only)
        from transformers import CLIPModel, CLIPProcessor
    except ImportError as e:
        _load_error = (
            "This needs the 'torch' and 'transformers' packages installed on the server. "
            "Install with: pip install --index-url https://download.pytorch.org/whl/cpu torch "
            f"&& pip install transformers pillow ({e})"
        )
        return None, None, _load_error

    try:
        _model = CLIPModel.from_pretrained(MODEL_NAME)
        _processor = CLIPProcessor.from_pretrained(MODEL_NAME)
        _model.eval()
    except Exception as e:
        _load_error = f"Could not load the CLIP model (first run downloads ~600 MB): {e}"
        return None, None, _load_error

    return _model, _processor, None


def model_ready() -> tuple[bool, str | None]:
    """Checks whether CLIP can be used. NOTE: calling this triggers the
    load (and, on first use on this machine, the download) -- don't call
    it just to render a status line on every page load."""
    _, _, err = _get_model()
    return err is None, err


@dataclass
class ClipScore:
    ok: bool
    cosine: float = 0.0
    error: str = ""


def score_image_against_text(image_bytes: bytes, text: str) -> ClipScore:
    model, processor, err = _get_model()
    if err:
        return ClipScore(ok=False, error=err)

    try:
        from PIL import Image
        import torch

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        inputs = processor(text=[text], images=[img], return_tensors="pt", padding=True)
        with torch.no_grad():
            out = model(**inputs)
        scale = model.logit_scale.exp().item()
        cosine = out.logits_per_image[0, 0].item() / scale
        return ClipScore(ok=True, cosine=cosine)
    except Exception as e:
        return ClipScore(ok=False, error=f"Could not score this image: {e}")


def classify(
    cosine: float,
    yes_threshold: float = DEFAULT_YES_THRESHOLD,
    no_threshold: float = DEFAULT_NO_THRESHOLD,
) -> str:
    if cosine >= yes_threshold:
        return "Yes"
    if cosine < no_threshold:
        return "No"
    return "Unsure"


def check_rows_clip(
    rows: list[dict],
    yes_threshold: float = DEFAULT_YES_THRESHOLD,
    no_threshold: float = DEFAULT_NO_THRESHOLD,
    progress_cb=None,
) -> list[MatchRow]:
    """Same batch shape as image_match.check_rows, but scored locally with
    CLIP instead of calling a hosted vision API. One row failing (bad
    link, missing dependency, bad image) never stops the rest of the
    batch -- it's recorded as that row's own 'Error' result."""
    results: list[MatchRow] = []
    total = len(rows)

    for i, row in enumerate(rows):
        id1 = str(row.get("Identifier_1", "") or "")
        id2 = str(row.get("Identifier_2", "") or "")
        url = str(row.get("Image_URL", "") or "").strip()
        name_checked = id2 or id1

        result = MatchRow(index=i, identifier_1=id1, identifier_2=id2, image_url=url)

        if not url:
            result.match, result.reason = "Error", "No image link given"
        elif not name_checked:
            result.match, result.reason = "Error", "No name to check against this image"
        else:
            fetched = fetch_image(url)
            if not fetched.ok:
                result.match, result.reason = "Error", fetched.error
            else:
                scored = score_image_against_text(fetched.data, name_checked)
                if not scored.ok:
                    result.match, result.reason = "Error", scored.error
                else:
                    result.match = classify(scored.cosine, yes_threshold, no_threshold)
                    result.reason = (
                        f"cosine similarity {scored.cosine:.2f} "
                        f"(Yes >= {yes_threshold:.2f}, No < {no_threshold:.2f})"
                    )

        results.append(result)
        if progress_cb:
            progress_cb(i + 1, total)

    return results