import argparse
import gzip
import itertools
import os
import re
import urllib.parse
import urllib.request
from bisect import bisect_left
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime

TIMESTAMP_FORMAT = '"YYYY-MM-DD hh:mm:ss"'
WORKING_DIR = '/tmp'
LINK_REGEX = '<a.*?href="(.*?)".*?>{}'
REPOSITORY_URL = 'http://snapshot.debian.org'


def parse_timestamp(timestamp):
    try:
        datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
        return timestamp
    except ValueError:
        raise argparse.ArgumentTypeError(
            'timestamp does not match format {}'.format(TIMESTAMP_FORMAT))


def open_(path, *args, **kwargs):
    return (
        gzip.open(path, *args, **kwargs)
        if path.endswith('.gz')
        else open(path, *args, **kwargs)
    )


def get_actions(until):
    '''Returns applicable log actions in reversed chronological order'''

    log_files = (
        entry for entry in os.scandir('/var/log')
        if entry.is_file() and entry.name.startswith('dpkg.log')
    )

    # Evaluate the first line of each file to figure out their order
    sorted_timestamps = []
    timestamp_to_file = {}
    for entry in log_files:
        with open_(entry.path, 'rt') as f:
            line = f.readline()
            if line:
                date, time, rest = line.strip().split(' ', 2)
                timestamp = '{} {}'.format(date, time)
                sorted_timestamps.insert(bisect_left(sorted_timestamps,
                                                     timestamp),
                                         timestamp)
                assert timestamp not in timestamp_to_file, \
                       'Two log files start with the same timestamp'
                timestamp_to_file[timestamp] = entry

    # Now extract actions from them in the correct order
    for timestamp in reversed(sorted_timestamps):
        entry = timestamp_to_file[timestamp]
        with open_(entry.path, 'rt') as f:
            for line in reversed(f.read().splitlines()):
                date, time, action, rest = line.strip().split(' ', 3)

                if '{} {}'.format(date, time) < until:
                    return

                if action in ('install', 'upgrade', 'remove', 'purge'):
                    package_arch, fromversion, toversion = rest.split(' ')
                    package, arch = package_arch.split(':')
                    yield {
                        'action': action,
                        'package': package,
                        'arch': arch,
                        'fromversion': fromversion,
                        'toversion': toversion,
                    }
                line = f.readline()


def build_filename(package, version, arch):
    return '{}_{}_{}.deb'.format(package, version, arch)


def download_package(download_dir, package, arch, version):
    filename = build_filename(package, version, arch)
    if not os.path.exists(os.path.join(download_dir, filename)):
        search_results_url = '{}/binary/{}/'.format(REPOSITORY_URL, package)
        search_results = bytes.decode(
            urllib.request.urlopen(search_results_url).read()
        )
        search_result_link_regex = LINK_REGEX.format(re.escape(version))
        package_options_url = urllib.parse.urljoin(
            search_results_url,
            re.search(search_result_link_regex, search_results).group(1)
        )
        package_options = bytes.decode(
            urllib.request.urlopen(package_options_url).read()
        )
        package_link_regex = LINK_REGEX.format('{}_[^_]*_{}.deb'.format(
            re.escape(package),
            re.escape(arch)
        ))
        package_url = urllib.parse.urljoin(
            package_options_url,
            re.search(package_link_regex, package_options).group(1)
        )
        print('Downloading {}'.format(package_url))
        urllib.request.urlretrieve(package_url,
                                   os.path.join(download_dir, filename))
        print('Finished downloading {}'.format(package_url))
    else:
        print('We already have {}, neat!'.format(filename))


def main():
    argparser = argparse.ArgumentParser(
        description='''Reverts all package operations up
                       to some specific timestamp.'''
    )
    argparser.add_argument(
        'timestamp',
        help='timestamp in format {}'.format(TIMESTAMP_FORMAT),
        type=parse_timestamp
    )
    argparser.add_argument('-f', '--force', action='store_true',
                           help="force execution even if some packages can't "
                           "be downloaded")
    args = argparser.parse_args()

    snapshot = {
        (action['package'], action['arch']): action
        for action in
        get_actions(args.timestamp)
    }

    if not len(snapshot):
        print('No package operations to revert')
        exit(0)

    download_dir = os.path.join(
        WORKING_DIR,
        'apt-rollback-{}/'.format(args.timestamp).replace(' ', '_')
    )
    try:
        os.mkdir(download_dir)
    except FileExistsError:
        pass

    with ThreadPoolExecutor(max_workers=len(snapshot)) as executor:
        futures = {
            executor.submit(download_package, download_dir, package, arch,
                            action['fromversion']): action
            for (package, arch), action in snapshot.items()
            if action['action'] != 'install'
        }
        done, _ = wait(futures.keys())

    failed = [futures[future] for future in done if future.exception()]
    if failed and not args.force:
        print("\nThe following packages couldn't be downloaded. Please "
              "download them manually, place them in {} and run "
              "this command again. If you wish to ignore these packages run "
              "the command again using the -f flag.\n".format(download_dir))
        for action in failed:
            print('{}:{} {}'.format(action['package'], action['arch'],
                                    action['fromversion']))
        exit(1)

    # remove packages we couldn't download from the snapshot
    for action in failed:
        del snapshot[(action['package'], action['arch'])]

    if not len(snapshot):
        print('No package operations to revert')
        exit(0)

    installs = [
        os.path.join(download_dir, build_filename(action['package'],
                                                  action['fromversion'],
                                                  action['arch']))
        for action in snapshot.values()
        if action['action'] != 'install'
    ]
    uninstalls = [
        '{}:{}'.format(action['package'], action['arch'])
        for action in snapshot.values()
        if action['action'] == 'install'
    ]
    dpkg_command = 'dpkg{}{}{}{}'.format(' -i ' if installs else '',
                                         ' '.join(installs),
                                         ' -P ' if uninstalls else '',
                                         ' '.join(uninstalls))
    os.system(dpkg_command)


if __name__ == '__main__':
    main()
