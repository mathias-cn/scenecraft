from io import BytesIO

from PIL import Image, ImageDraw

from app.storage import compress_image


def _illustration_png() -> bytes:
    """PNG 1024x1536 no estilo ilustração (áreas lisas + alguma textura)."""
    image = Image.new("RGB", (1024, 1536), (28, 36, 64))
    draw = ImageDraw.Draw(image)
    for band in range(0, 1536, 24):
        tone = 40 + (band % 90)
        draw.rectangle([0, band, 1023, band + 23], fill=(tone, 70, 140))
    draw.ellipse([180, 220, 844, 1080], fill=(232, 188, 148), outline=(40, 22, 12), width=10)
    draw.rectangle([360, 520, 664, 900], fill=(196, 48, 54))
    draw.polygon([(512, 260), (640, 480), (384, 480)], fill=(48, 32, 96))
    noise = Image.effect_noise((1024, 1536), 48).convert("RGB")
    image = Image.blend(image, noise, 0.12)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_compress_image_returns_webp_smaller_than_png():
    png = _illustration_png()
    webp = compress_image(png, quality=82)
    assert webp.startswith(b"RIFF") and webp[8:12] == b"WEBP"
    opened = Image.open(BytesIO(webp))
    assert opened.format == "WEBP"
    assert opened.size == (1024, 1536)
    ratio = len(webp) / len(png)
    assert len(png) > 400_000, f"PNG de controle pequeno demais: {len(png)} bytes"
    assert ratio <= 0.30, (
        f"WEBP q=82 deveria ficar ~70–85% menor; PNG={len(png)} WEBP={len(webp)} ratio={ratio:.2f}"
    )


def test_compress_image_preserves_alpha():
    image = Image.new("RGBA", (32, 32), (255, 0, 0, 0))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    webp = compress_image(buffer.getvalue(), quality=82)
    opened = Image.open(BytesIO(webp))
    assert opened.mode in {"RGBA", "RGB"}
    if opened.mode == "RGBA":
        assert opened.getpixel((0, 0))[3] == 0
