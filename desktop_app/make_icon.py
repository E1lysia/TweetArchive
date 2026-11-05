from pathlib import Path
from PIL import Image, ImageDraw

image = Image.new('RGBA', (256, 256), (16, 25, 29, 255))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((20, 20, 236, 236), radius=48, fill='#1d3e3b')
draw.rounded_rectangle((51, 58, 205, 198), radius=14, outline='#76dfbf', width=9)
draw.line((53, 94, 203, 94), fill='#76dfbf', width=8)
draw.polygon([(112, 119), (112, 174), (157, 147)], fill='#b5f2dd')
image.save(Path(__file__).parent / 'launcher/archive.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
