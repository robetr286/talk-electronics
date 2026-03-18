import sys

def convert_line(line):
    parts = line.strip().split()
    if len(parts) == 9:
        c = parts[0]
        coords = [float(x) for x in parts[1:]]
        xs = coords[0::2]
        ys = coords[1::2]
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        xc = (xmin + xmax) / 2.0
        yc = (ymin + ymax) / 2.0
        w = xmax - xmin
        h = ymax - ymin
        return f"{c} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}\n"
    return line

with open(sys.argv[1], 'r') as f:
    lines = f.readlines()
    
with open(sys.argv[1], 'w') as f:
    for line in lines:
        f.write(convert_line(line))
