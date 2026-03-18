import sys
from pathlib import Path as _P

import cv2
import numpy as np

Path = _P


def build_image(size=200):
    img = np.zeros((size, size), dtype=np.uint8)
    center = size // 2
    cv2.line(img, (10, 10), (center - 6, center - 6), 255, 3)
    cv2.line(img, (center + 6, center + 6), (size - 10, size - 10), 255, 3)
    for i in range(-3, 4):
        cx = center + i * 3
        cy = center + i * 3
        cv2.circle(img, (cx, cy), 2, 255, -1)
    cv2.line(img, (size - 10, 10), (center + 6, center - 6), 255, 3)
    cv2.line(img, (center - 6, center + 6), (10, size - 10), 255, 3)
    for i in range(-3, 4):
        cx = center + i * 3
        cy = center - i * 3
        cv2.circle(img, (cx, cy), 2, 255, -1)
    mid_y = center + 30
    cv2.line(img, (10, mid_y), (size - 10, mid_y), 255, 3)
    return img


def run():
    out = Path("debug/debug_graph_repair_local")
    out.mkdir(parents=True, exist_ok=True)
    img = build_image()
    cv2.imwrite(str(out / "input.png"), img)

    # ensure project root is importable when running as a script
    ROOT = str(_P(__file__).resolve().parents[1])
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    from talk_electronic.services.line_detection import LineDetectionConfig, detect_lines

    cfg_no = LineDetectionConfig(
        dotted_line_graph_repair_enable=False, morph_iterations=0, debug_dir=out, debug_prefix="no"
    )
    res_no = detect_lines(img, binary=False, config=cfg_no)

    cfg_yes = LineDetectionConfig(
        dotted_line_graph_repair_enable=True,
        morph_iterations=0,
        dotted_line_graph_repair_angle_threshold=80.0,
        dotted_line_graph_repair_overlap_fraction=0.0,
        dotted_line_graph_repair_max_joins_per_image=100,
        dotted_line_bridge_endpoint_max_distance=250,
    )
    cfg_yes.debug_dir = out
    cfg_yes.debug_prefix = "yes"
    res_yes = detect_lines(img, binary=False, config=cfg_yes)

    # print results and where to find debug images
    print("no.lines=", len(res_no.lines), "yes.lines=", len(res_yes.lines))
    print("Debug artifacts saved into", out)
    print("no.lines=", len(res_no.lines), "yes.lines=", len(res_yes.lines))


if __name__ == "__main__":
    run()
