import argparse
import gzip
import itertools
import os
import re
import urllib.request
import urllib.parse
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


def get_actions(until):
    log_files = (
        entry for entry in os.scandir('/var/log')
        if entry.is_file() and entry.name.startswith('dpkg.log')
    )
    for entry in log_files:
        openf = gzip.open if entry.path.endswith('.gz') else open
        with openf(entry.path, 'rt') as f:
            line = f.readline()
            reached_timestamp = False
            while line and not reached_timestamp:
                date, time, action, rest = line.strip().split(' ', 3)
                reached_timestamp = '{} {}'.format(date, time) < until
                if (
                        not reached_timestamp
                        and action in ('install', 'upgrade', 'remove', 'purge')
                ):
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


def download_package(download_dir, package, arch, version):
    filename = '{}_{}_{}.deb'.format(package, version, arch)
    if not os.path.exists(os.path.join(download_dir, filename)):
        search_results_url = '{}/binary/{}/'.format(REPOSITORY_URL, package)
        search_results = bytes.decode(urllib.request.urlopen(search_results_url).read())
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
        urllib.request.urlretrieve(package_url, os.path.join(download_dir, filename))
        print('Finished downloading {}'.format(package_url))
    else:
        print('We already have {}, neat!'.format(filename))


if __name__ == '__main__':
    argparser = argparse.ArgumentParser(
        description='Reverts all package operations up to some specific timestamp.'
    )
    argparser.add_argument('timestamp',
                           help='Timestamp in format {}'.format(TIMESTAMP_FORMAT),
                           type=parse_timestamp)
    args = argparser.parse_args()

    snapshot = {}
    for action in get_actions(args.timestamp):
        snapshot[action['package']] = action

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
            executor.submit(download_package, download_dir, package,
                            action['arch'], action['fromversion']): action
            for package, action in snapshot.items()
            if action['action'] != 'install'
        }
        done, _ = wait(futures.keys())
        failed = (futures[future] for future in done if future.exception())
        can_continue = True
        for action in failed:
            if can_continue:
                can_continue = False
                print("The following packages couldn't be downloaded. Please "
                      "download them manually, place them in {} and run "
                      "this command again.".format(download_dir))
            print('{} {}'.format(action['package'], action['fromversion']))

        if can_continue:
            print('Finished downloading all packages')
