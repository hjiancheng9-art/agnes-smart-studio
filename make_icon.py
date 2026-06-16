#!/usr/bin/env python3
"""生成 Agnes Smart Studio 应用图标 (agnes.ico)"""
from PIL import Image, ImageDraw

def create_icon():
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 圆角矩形背景
    margin = 12
    radius = 40
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=radius,
        fill=(0, 188, 212),  # #00BCD4 主题色
    )

    # 中心 "A" 字母
    cx, cy = size // 2, size // 2
    # 简易 A 字母 - 两条斜线 + 横线
    a_w, a_h = 80, 100
    x0, y0 = cx - a_w // 2, cy + a_h // 2 - 10
    x1, y1 = cx, cy - a_h // 2 + 10
    x2, y2 = cx + a_w // 2, cy + a_h // 2 - 10
    # 左斜
    draw.line([(x0, y0), (x1, y1)], fill="white", width=18)
    # 右斜
    draw.line([(x1, y1), (x2, y2)], fill="white", width=18)
    # 横线
    draw.line([(x0 + 22, cy + 8), (x2 - 22, cy + 8)], fill="white", width=14)

    # 保存为 ico (包含多尺寸)
    ico_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    icon_path = "agnes.ico"
    img.save(icon_path, format="ICO", sizes=ico_sizes)
    print(f"图标已保存: {icon_path}")

    # 同时导出 PNG 预览
    img.save("agnes_icon_preview.png")
    print(f"预览已保存: agnes_icon_preview.png")

if __name__ == "__main__":
    create_icon()
