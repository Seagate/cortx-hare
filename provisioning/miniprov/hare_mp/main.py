import argparse
import sys

from hare_mp.cdf import CdfGenerator
from hare_mp.store import ConfStoreProvider


class Configure(argparse.Action):
    def __call__(self, parser, args, values, option_string=None):
        url = values[0]
        self.generate_cdf(url)


def generate_cdf(url: str) -> str:
    generator = CdfGenerator(ConfStoreProvider(url))
    return generator.generate()


def save(filename: str, contents: str) -> None:
    with open(filename, 'w') as f:
        f.write(contents)


def main():
    p = argparse.ArgumentParser(description='Configure hare settings')
    p.add_argument('--filename',
                   help='Full path to the CDF file to generate at this stage.',
                   nargs=1,
                   default='/var/lib/hare/cluster.yaml',
                   type=str,
                   action='store')
    p.add_argument('--config',
                   help='Configure Hare',
                   nargs=1,
                   type=str,
                   default='',
                   dest='config_url',
                   action='store')
    parsed = p.parse_args(sys.argv[1:])
    if parsed.config_url:
        url = parsed.config_url[0]
        filename = parsed.filename[0]
        save(filename, generate_cdf(url))


if __name__ == '__main__':
    main()
