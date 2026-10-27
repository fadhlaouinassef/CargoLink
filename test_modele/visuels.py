"""Graphiques PNG reproductibles avec Pillow (déjà utilisé par le projet)."""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1600, 1000
BLUE, ORANGE, GREEN = "#2563eb", "#d97706", "#059669"


def font(size):
    for path in ("C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def canvas(title, subtitle):
    im = Image.new("RGB", (WIDTH, HEIGHT), "#f8fafc")
    draw = ImageDraw.Draw(im)
    draw.text((65, 35), title, fill="#0f172a", font=font(34))
    draw.text((65, 95), subtitle, fill="#475569", font=font(21))
    draw.text((65, 955), "CargoLink | Évaluation reproductible | Labels de pertinence simulés", fill="#64748b", font=font(20))
    return im, draw


def save(im, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)


def table(path, title, subtitle, headers, rows):
    im, draw = canvas(title, subtitle)
    left, top, width = 65, 160, 1470
    col = width / len(headers)
    row_height = min(68, 730 / (len(rows) + 1))
    for i, row in enumerate([headers] + list(rows)):
        y = top + i * row_height
        bg = "#1e3a8a" if i == 0 else ("#e2e8f0" if i % 2 else "#ffffff")
        draw.rectangle((left, y, left + width, y + row_height), fill=bg)
        for j, value in enumerate(row):
            text = str(value)
            # Réduire les cellules longues sans couper les valeurs numériques.
            size = min(23, max(12, int(col / max(len(text), 1) * 1.7)))
            draw.text((left + j * col + 10, y + 12), text, fill="white" if i == 0 else "#0f172a", font=font(size))
    save(im, path)


def bars(path, title, subtitle, labels, series, maximum=None):
    im, draw = canvas(title, subtitle)
    left, right, top, bottom = 140, 1520, 205, 790
    maximum = maximum or max(max(values) for _, values, _ in series) * 1.15 or 1
    for tick in np.linspace(0, maximum, 6):
        y = bottom - tick / maximum * (bottom - top)
        draw.line((left, y, right, y), fill="#cbd5e1", width=1)
        draw.text((25, y - 12), f"{tick:.2f}" if maximum <= 1 else f"{tick:.0f}", fill="#475569", font=font(21))
    group = (right - left) / len(labels)
    bar_width = group * .72 / len(series)
    for j, (name, values, color) in enumerate(series):
        draw.rectangle((left + j * 410, 155, left + j * 410 + 22, 177), fill=color)
        draw.text((left + j * 410 + 32, 151), name, fill="#0f172a", font=font(21))
        for i, value in enumerate(values):
            x = left + group * i + group * .14 + j * bar_width
            y = bottom - value / maximum * (bottom - top)
            draw.rectangle((x, y, x + bar_width - 4, bottom), fill=color)
            draw.text((x, y - 30), f"{value:.3f}" if maximum <= 1 else f"{value:.0f}", fill="#0f172a", font=font(19))
    for i, label in enumerate(labels):
        draw.text((left + group * i + 8, bottom + 22), label, fill="#0f172a", font=font(21))
    save(im, path)


def lines(path, title, subtitle, curves, xlabel, ylabel, diagonal=False):
    im, draw = canvas(title, subtitle)
    left, right, top, bottom = 140, 1500, 220, 830
    point = lambda x, y: (left + float(x) * (right - left), bottom - float(y) * (bottom - top))
    for t in np.linspace(0, 1, 6):
        x, y = point(t, t)
        draw.line((left, y, right, y), fill="#cbd5e1")
        draw.line((x, top, x, bottom), fill="#cbd5e1")
        draw.text((x - 16, bottom + 12), f"{t:.1f}", fill="#475569", font=font(20))
        draw.text((70, y - 10), f"{t:.1f}", fill="#475569", font=font(20))
    if diagonal:
        draw.line([point(0, 0), point(1, 1)], fill="#94a3b8", width=3)
    for i, (name, xs, ys, color) in enumerate(curves):
        points = [point(x, y) for x, y in zip(xs, ys)]
        if len(points) >= 2:
            draw.line(points, fill=color, width=4)
        draw.text((150 + i * 650, 162), name, fill=color, font=font(23))
    draw.text((620, 894), xlabel, fill="#0f172a", font=font(24))
    draw.text((140, 190), ylabel, fill="#0f172a", font=font(22))
    save(im, path)


def heatmap(path, title, subtitle, matrix, labels, normalized=False):
    im, draw = canvas(title, subtitle)
    matrix = np.asarray(matrix)
    n = len(labels)
    left, top, side = 340, 240, min(620 / n, 280)
    finite = np.abs(matrix[np.isfinite(matrix)])
    scale = max(float(finite.max()) if finite.size else 0, 1e-12)
    for i in range(n):
        row_label = f"{i + 1}. {labels[i]}" if n > 4 else labels[i]
        column_label = str(i + 1) if n > 4 else labels[i]
        draw.text((65, top + i * side + side / 2 - 12), row_label, fill="#0f172a", font=font(18 if n > 4 else 25))
        draw.text((left + i * side + 8, top - 48), column_label, fill="#0f172a", font=font(20 if n > 4 else 24))
        for j in range(n):
            value = float(matrix[i, j])
            intensity = abs(value) / scale if np.isfinite(value) else 0
            color = (int(239 - 202 * intensity), int(246 - 147 * intensity), int(255 - 20 * intensity))
            x, y = left + j * side, top + i * side
            draw.rectangle((x, y, x + side - 2, y + side - 2), fill=color)
            label = (f"{value:.2f}" if normalized else str(int(value))) if np.isfinite(value) else "—"
            draw.text((x + side * .28, y + side * .43), label, fill="white" if intensity > .55 else "#0f172a", font=font(20 if n > 4 else 40))
    save(im, path)
