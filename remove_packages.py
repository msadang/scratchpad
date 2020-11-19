from datetime import date, datetime, timedelta
from binstar_client.commands.remove import main as remove_main
from binstar_client.utils.spec import parse_specs
from conda.cli.python_api import run_command as conda_cli
from conda.exceptions import PackagesNotFoundError
import json
import re
from argparse import Namespace
import os
from typing import Set, List, Tuple, Iterable
from itertools import islice

def split_every(n, iterable):
    iterable = iter(iterable)
    yield from iter(lambda: list(islice(iterable, n)), [])


TOKEN = os.environ['CONDA_TOKEN']


def version_to_date(version: str) -> date:
    """
    Extracts the date from a version string like 0.13.0a200104
    :param version:
    :return:
    """
    pattern = re.compile(r'[a-z]\d?(\d\d)(\d\d)(\d\d)')
    m = pattern.search(version)
    if not m:
        return None
    year = 2000 + int(m.group(1))
    month = int(m.group(2))
    day = int(m.group(3))
    return date(year=year, month=month, day=day)


def get_date(version: str, timestamp: int) -> date:
    """
    Converts the version to a date and falls back on the timestamp if the
    version doesn't contain a date
    :param version:
    :param timestamp:
    :return:
    """
    d = version_to_date(version)
    if not d:
        d = datetime.utcfromtimestamp(timestamp / 1000.0).date()
    return d


def get_file_list(channel, package) -> \
        List[Tuple[date, str, str]]:
    """
    Get all of the versions for a specific package
    :param channel:
    :param package:
    :return:
    """
    for arch in ('noarch', 'linux-64'):
        args = ['-c', channel, '--override-channels', '--info', '--json', f'{package}[subdir={arch}]']

        try:
            result = conda_cli('search', *args)
        except PackagesNotFoundError:
            continue
        result = json.loads(result[0])[package]

        files = []
        for pkg in result:
            version = pkg['version']
            timestamp = pkg['timestamp']
            pkg_date = get_date(version, timestamp)
            fn = pkg['subdir'] + '/' + pkg['fn']
            file = (pkg_date, version, fn)
            files.append(file)
        return files
    raise Exception('Could not find package: '+package)


def versions_older_than(older_than: date, files: Iterable[Tuple[date, str, str]]) \
        -> List[Tuple[date, str, str]]:
    """
    Get versions older than a certain date
    :param older_than:
    :param files:
    :return:
    """
    return [x for x in files if older_than > x[0]]


def remove(min_packages_to_keep: int, older_than: date, channel, package_name):
    """
    Remove packages from the channel older than a certain date
    :param min_packages_to_keep:
    :param older_than:
    :param channel:
    :param package_name:
    :return:
    """
    files = sorted(get_file_list(channel, package_name), reverse=True)
    print(f'Found {len(files)} packages for {package_name}')
    # Keep the most recent N
    print(f'Retaining most recent {min_packages_to_keep} packages for {package_name}')
    files = files[min_packages_to_keep:]
    # Remove packages older than the date
    files = versions_older_than(older_than, files)
    print(f'Removing {package_name} ({len(files)}): {[x[2] for x in files]}')
    if files:
        count = 0
        for files_chunk in split_every(50, files):
            specs = (parse_specs(f'{channel}/{package_name}/{f[1]}/{f[2]}')
                     for f in files_chunk)
            args = Namespace(specs=specs, token=TOKEN, site='', force=True)
            remove_main(args)
            count += len(files_chunk)
            print(f'Removed {count}/{len(files)} {package_name} packages...')


def main():
    older_than = date.today() - timedelta(days=int(os.environ.get('DAYS_OLD', 10)))
    channel = os.environ.get('CHANNEL', 'rapidsai-nightly')
    packages = os.environ['PACKAGES'].split(',')
    min_packages_to_keep = int(os.environ.get('KEEP_NUM_PACKAGES', 21))
    for package in packages:
        remove(min_packages_to_keep, older_than, channel, package)


if __name__ == '__main__':
    main()
