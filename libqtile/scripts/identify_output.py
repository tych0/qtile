from sys import exit

import libqtile.backend


def identify_output(opts) -> None:
    """Print output names and serial numbers for all screens."""
    if missing_deps := libqtile.backend.has_deps(opts.backend):
        print(f"Backend '{opts.backend}' missing required Python dependencies:")
        for dep in missing_deps:
            print("\t", dep)
        exit(1)

    kore = libqtile.backend.get_core(opts.backend)
    output_info = kore.get_output_info()
    kore.finalize()

    print("Output Information:")

    for i, info in enumerate(output_info):
        name = info.name or "Unknown"
        serial = info.serial or "N/A"

        print(f"Screen {i}:")
        print(f"  Output Name: {name}")
        print(f"  Serial Number: {serial}")
        print(f"  Position: ({info.rect.x}, {info.rect.y})")
        print(f"  Resolution: {info.rect.width}x{info.rect.height}")
        print()


def add_subcommand(subparsers, parents):
    parser = subparsers.add_parser(
        "identify-output",
        parents=parents,
        help="Print output names and serial numbers.",
    )
    parser.add_argument(
        "-b",
        "--backend",
        default="x11",
        dest="backend",
        choices=libqtile.backend.CORES.keys(),
        help="Use specified backend.",
    )
    parser.set_defaults(func=identify_output)
