r"""Makes launch\monitor\icons\monitor.ico (a pulse line on a dark rounded square). Run once with the .venv Python."""
from pathlib import Path

from PIL import Image, ImageDraw

out = Path(__file__).resolve().parent / "icons" / "monitor.ico"
out.parent.mkdir(exist_ok=True)
S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([8, 8, S - 8, S - 8], radius=48, fill=(17, 20, 24, 255), outline=(62, 207, 142, 255), width=10)
pts = [(36, 140), (88, 140), (112, 80), (144, 190), (170, 120), (220, 120)]
d.line(pts, fill=(62, 207, 142, 255), width=18, joint="curve")
img.save(out, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(out)
