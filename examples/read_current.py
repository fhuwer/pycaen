#!/usr/bin/env python
import argparse
from pycaen import Caen1471
import time


def main(args):
    c = Caen1471(port=args.port, baudrate=args.baudrate)
    try:
        while True:
            print("\r", end="")
            print(
                "0: {:.2f} nA, 1: {:.2f} nA".format(
                    c.get_current(0) * 1e3, c.get_current(1) * 1e3
                ),
                end="",
            )
            time.sleep(1)
    except:
        c.connection.close()


if __name__ == "__main__":
    argparser = argparse.ArgumentParser(prog="read_current")
    argparser.add_argument(
        "-p", "--port", default="/dev/ttyUSB0", help="Serial port of the 1471"
    )
    argparser.add_argument(
        "-b", "--baudrate", default=115200, type=int, help="Baudrate for serial port"
    )
    args = argparser.parse_args()
    main(args)
