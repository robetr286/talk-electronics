"""
Generate simple template images for symbol detection.
Creates black-and-white PNG templates of electronic components.
"""

from pathlib import Path

from PIL import Image, ImageDraw


def create_resistor_template(width: int = 60, height: int = 20) -> Image.Image:
    """
    Create a resistor symbol template (zigzag pattern).

    Args:
        width: Template width in pixels
        height: Template height in pixels

    Returns:
        PIL Image with resistor symbol
    """
    img = Image.new("L", (width, height), color=255)  # White background
    draw = ImageDraw.Draw(img)

    # Resistor zigzag pattern
    y_center = height // 2
    x_start = 5
    x_end = width - 5
    zigzag_width = x_end - x_start
    segment_width = zigzag_width // 6

    points = [
        (x_start, y_center),
        (x_start + segment_width * 0.5, y_center - 6),
        (x_start + segment_width * 1.5, y_center + 6),
        (x_start + segment_width * 2.5, y_center - 6),
        (x_start + segment_width * 3.5, y_center + 6),
        (x_start + segment_width * 4.5, y_center - 6),
        (x_start + segment_width * 5.5, y_center + 6),
        (x_end, y_center),
    ]

    draw.line(points, fill=0, width=2)  # Black line

    return img


def create_capacitor_template(width: int = 40, height: int = 30) -> Image.Image:
    """
    Create a capacitor symbol template (two parallel lines).

    Args:
        width: Template width in pixels
        height: Template height in pixels

    Returns:
        PIL Image with capacitor symbol
    """
    img = Image.new("L", (width, height), color=255)  # White background
    draw = ImageDraw.Draw(img)

    # Two parallel vertical lines
    x_center = width // 2
    gap = 4
    line_height = int(height * 0.7)
    y_start = (height - line_height) // 2
    y_end = y_start + line_height

    # Left plate
    draw.line([(x_center - gap, y_start), (x_center - gap, y_end)], fill=0, width=2)
    # Right plate
    draw.line([(x_center + gap, y_start), (x_center + gap, y_end)], fill=0, width=2)

    # Connection wires
    draw.line([(5, height // 2), (x_center - gap, height // 2)], fill=0, width=2)
    draw.line([(x_center + gap, height // 2), (width - 5, height // 2)], fill=0, width=2)

    return img


def create_inductor_template(width: int = 60, height: int = 25) -> Image.Image:
    """
    Create an inductor symbol template (series of arcs/coils).

    Args:
        width: Template width in pixels
        height: Template height in pixels

    Returns:
        PIL Image with inductor symbol
    """
    img = Image.new("L", (width, height), color=255)  # White background
    draw = ImageDraw.Draw(img)

    y_center = height // 2
    x_start = 5
    x_end = width - 5
    coil_width = (x_end - x_start) // 4
    arc_height = int(height * 0.6)

    # Draw 4 coils as arcs
    for i in range(4):
        x_left = x_start + i * coil_width
        x_right = x_left + coil_width
        bbox = [x_left, y_center - arc_height // 2, x_right, y_center + arc_height // 2]
        draw.arc(bbox, start=180, end=0, fill=0, width=2)

    return img


def create_diode_template(width: int = 40, height: int = 30) -> Image.Image:
    """
    Create a diode symbol template (triangle with line).

    Args:
        width: Template width in pixels
        height: Template height in pixels

    Returns:
        PIL Image with diode symbol
    """
    img = Image.new("L", (width, height), color=255)  # White background
    draw = ImageDraw.Draw(img)

    x_center = width // 2
    y_center = height // 2
    triangle_size = int(height * 0.5)

    # Triangle (anode)
    triangle = [
        (x_center - triangle_size // 2, y_center - triangle_size // 2),
        (x_center - triangle_size // 2, y_center + triangle_size // 2),
        (x_center + triangle_size // 2, y_center),
    ]
    draw.polygon(triangle, fill=0, outline=0)

    # Cathode line
    draw.line(
        [
            (x_center + triangle_size // 2, y_center - triangle_size // 2),
            (x_center + triangle_size // 2, y_center + triangle_size // 2),
        ],
        fill=0,
        width=2,
    )

    # Connection wires
    draw.line([(5, y_center), (x_center - triangle_size // 2, y_center)], fill=0, width=2)
    draw.line([(x_center + triangle_size // 2, y_center), (width - 5, y_center)], fill=0, width=2)

    return img


def create_op_amp_template(width: int = 70, height: int = 50) -> Image.Image:
    """
    Create an op-amp symbol template (triangle with input/output pins).

    Args:
        width: Template width in pixels
        height: Template height in pixels

    Returns:
        PIL Image with op-amp symbol
    """
    img = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(img)

    x_center = width // 2
    y_center = height // 2

    # Triangle pointing right
    triangle = [
        (x_center - width // 2 + 5, y_center - height // 2 + 5),
        (x_center - width // 2 + 5, y_center + height // 2 - 5),
        (x_center + width // 2 - 5, y_center),
    ]
    draw.polygon(triangle, outline=0, width=2)

    # Input pins (+/-)
    offset = height // 4
    draw.line(
        [(x_center - width // 2 - 5, y_center - offset), (x_center - width // 2 + 5, y_center - offset)],
        fill=0,
        width=2,
    )
    draw.line(
        [(x_center - width // 2 - 5, y_center + offset), (x_center - width // 2 + 5, y_center + offset)],
        fill=0,
        width=2,
    )
    draw.text((x_center - width // 2 - 12, y_center - offset - 6), "+", fill=0)
    draw.text((x_center - width // 2 - 12, y_center + offset - 6), "-", fill=0)

    # Output pin
    draw.line([(x_center + width // 2 - 5, y_center), (x_center + width // 2 + 8, y_center)], fill=0, width=2)

    return img


def create_transistor_template(width: int = 40, height: int = 40) -> Image.Image:
    """
    Create a transistor symbol template (NPN type).

    Args:
        width: Template width in pixels
        height: Template height in pixels

    Returns:
        PIL Image with transistor symbol
    """
    img = Image.new("L", (width, height), color=255)  # White background
    draw = ImageDraw.Draw(img)

    x_center = width // 2
    y_center = height // 2
    base_line_length = int(height * 0.5)

    # Base (vertical line on left)
    base_x = x_center - 8
    draw.line([(base_x, y_center - base_line_length // 2), (base_x, y_center + base_line_length // 2)], fill=0, width=2)

    # Base connection
    draw.line([(5, y_center), (base_x, y_center)], fill=0, width=2)

    # Collector (top right)
    collector_y = y_center - base_line_length // 3
    draw.line([(base_x, collector_y), (x_center + 8, 5)], fill=0, width=2)

    # Emitter (bottom right) with arrow
    emitter_y = y_center + base_line_length // 3
    draw.line([(base_x, emitter_y), (x_center + 8, height - 5)], fill=0, width=2)

    # Arrow on emitter
    arrow_tip = (x_center + 8, height - 5)
    draw.polygon([arrow_tip, (arrow_tip[0] - 4, arrow_tip[1] - 6), (arrow_tip[0] + 2, arrow_tip[1] - 4)], fill=0)

    return img


def rotate_template(img: Image.Image, angle: float) -> Image.Image:
    """
    Rotate a template image.

    Args:
        img: Source image
        angle: Rotation angle in degrees

    Returns:
        Rotated image
    """
    return img.rotate(angle, expand=True, fillcolor=255)


def main():
    """Generate all template images."""
    # Create output directory
    output_dir = Path(__file__).parent.parent.parent / "data" / "templates"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating templates in {output_dir}...")

    # Define templates to generate
    templates = {
        "resistor": create_resistor_template,
        "capacitor": create_capacitor_template,
        "inductor": create_inductor_template,
        "diode": create_diode_template,
        "transistor": create_transistor_template,
        "op_amp": create_op_amp_template,
    }

    # Generate base templates and rotations
    angles = [0, 45, 90, 135, 180, 225, 270, 315]

    for name, create_func in templates.items():
        # Create category directory
        category_dir = output_dir / name
        category_dir.mkdir(exist_ok=True)

        # Generate base template
        base_img = create_func()

        # Save rotated versions
        for angle in angles:
            if angle == 0:
                filename = f"{name}_0deg.png"
            else:
                filename = f"{name}_{angle}deg.png"

            rotated = rotate_template(base_img, angle)
            output_path = category_dir / filename
            rotated.save(output_path)
            print(f"  Created {filename}")

    print("\nTemplate generation complete!")
    print(f"Total templates: {len(templates) * len(angles)}")


if __name__ == "__main__":
    main()
