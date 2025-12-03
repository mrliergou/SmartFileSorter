# -*- coding: utf-8 -*-
"""
创建应用图标
"""
from PIL import Image, ImageDraw, ImageFont

# 创建一个256x256的图标
size = 256
img = Image.new('RGB', (size, size), color='#3498db')
draw = ImageDraw.Draw(img)

# 绘制一个文件夹图标样式
# 绘制文件夹主体
folder_color = '#f39c12'
draw.rectangle([40, 80, 216, 200], fill=folder_color, outline='#e67e22', width=3)

# 绘制文件夹标签
draw.polygon([40, 80, 40, 60, 120, 60, 130, 80], fill=folder_color, outline='#e67e22')

# 绘制箭头
arrow_color = '#2ecc71'
# 箭头主体
draw.rectangle([90, 120, 166, 140], fill=arrow_color)
# 箭头头部
draw.polygon([166, 110, 190, 130, 166, 150], fill=arrow_color)

# 保存为PNG
img.save('icon.png', 'PNG')

# 保存为ICO（多尺寸）
icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
img.save('icon.ico', format='ICO', sizes=icon_sizes)

print("图标创建成功: icon.png 和 icon.ico")
