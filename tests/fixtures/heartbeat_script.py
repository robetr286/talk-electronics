import sys
import time


def main(period=0.2, n=5, initial=0.0):
    time.sleep(initial)
    for i in range(n):
        print(f"tick-{i}")
        sys.stdout.flush()
        time.sleep(period)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--period", type=float, default=0.2)
    p.add_argument("--n", type=int, default=5)
    p.add_argument("--initial", type=float, default=0.0)
    args = p.parse_args()
    main(args.period, args.n, args.initial)
