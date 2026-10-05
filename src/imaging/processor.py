import io

from PIL import Image

MAX_FILE_BYTES = 10 * 1024 * 1024  # Amazon's 10 MB cap


def normalize_to_rgb(img):
    """
    Converts any image mode (RGBA, P with transparency, CMYK, grayscale...)
    into plain RGB, flattening any transparency onto a white background.
    Amazon does not accept CMYK, and a transparent PNG uploaded as a main
    image just becomes white anyway -- so we do it ourselves, on purpose.
    """
    if img.mode == "CMYK":
        img = img.convert("RGB")
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        white_bg = Image.new("RGB", img.size, (255, 255, 255))
        white_bg.paste(img, mask=img.split()[-1])
        return white_bg
    return img.convert("RGB")


def fit_and_pad(img, target_w, target_h, bg_rgb=(255, 255, 255)):
    """
    Resizes the image to fit INSIDE the target square without cropping or
    stretching (preserves aspect ratio), then centers it on a canvas of
    exactly target_w x target_h filled with bg_rgb. Returns the new image,
    the % of the frame the product now fills, and how much it was
    upscaled (None if it wasn't enlarged).
    """
    img = normalize_to_rgb(img)
    src_w, src_h = img.size
    scale = min(target_w / src_w, target_h / src_h)

    new_w = max(1, round(src_w * scale))
    new_h = max(1, round(src_h * scale))
    resized = img.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGB", (target_w, target_h), bg_rgb)
    paste_x = (target_w - new_w) // 2
    paste_y = (target_h - new_h) // 2
    canvas.paste(resized, (paste_x, paste_y))

    fill_percent = round((new_w * new_h) / (target_w * target_h) * 100, 1)
    upscale_factor = round(scale, 2) if scale > 1 else None
    return canvas, fill_percent, upscale_factor


def save_jpg_under_size_limit(img, quality, max_bytes=MAX_FILE_BYTES):
    """
    Saves as JPEG, stepping quality down automatically if the file would
    exceed Amazon's 10 MB cap. Returns (bytes, quality_actually_used).
    """
    q = quality
    while True:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=q)
        data = buf.getvalue()
        if len(data) <= max_bytes or q <= 60:
            return data, q
        q -= 10