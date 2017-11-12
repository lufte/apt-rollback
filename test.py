import argparse
import os
import re
import sys
import unittest
from importlib import import_module
from unittest.mock import Mock, patch
from urllib.request import urljoin

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
aptrollback = import_module('apt-rollback')


class ParseTimestampTestCase(unittest.TestCase):

    def test_valid_timestamp(self):
        '''parse_timestamp returns the same string if timestamp is valid'''
        self.assertEqual('2017-01-01 00:00:00',
                         aptrollback.parse_timestamp('2017-01-01 00:00:00'))

    def test_invalid_timestamp(self):
        '''parse_timestamp raises an error if timestamp is invalid'''
        self.assertRaises(argparse.ArgumentTypeError,
                          aptrollback.parse_timestamp, 'timestamp')


class OpenTestCase(unittest.TestCase):

    @patch('apt-rollback.gzip')
    def test_gzip_file(self, mock_gzip):
        '''open_ uses gzip.open when filename ends with .gz'''
        mock_gzip.open = Mock(return_value='zip file!')
        self.assertEqual(aptrollback.open_('myfile.gz'),
                         mock_gzip.open.return_value)

    @patch('apt-rollback.open')
    def test_plain_text_file(self, mock_open):
        '''open_ uses built-in open when filename doesn't end with .gz'''
        mock_open.return_value = 'text file!'
        self.assertEqual(aptrollback.open_('myfile.log'),
                         mock_open.return_value)


        class BuildFilenameTestCase(unittest.TestCase):

            def test_build_filename(self):
                self.assertEqual(aptrollback.build_filename('first-string',
                                                            'second-string',
                                                            'third-string'),
                                 'first-string_second-string_third-string.deb')


class MockFile:

    def __init__(self, content):
        self.content = content
        self.curr_line = 0

    def readline(self):
        if self.curr_line < len(self.content):
            self.curr_line += 1
            return self.content[self.curr_line - 1]
        else:
            return ''

    def read(self):
        return self

    def splitlines(self):
        return self.content

    def __enter__(self, *args, **kwargs):
        return self

    def __exit__(self, *args, **kwargs):
        pass


def mock_open_(path, *args, **kwargs):
    if path == 'dpkg.log.1':
        return MockFile(['2017-01-01 00:00:00 upgrade pkg:arch 2 3'])
    elif path == 'dpkg.log.2':
        return MockFile(['2015-01-01 00:00:00 install pkg:arch <none> 1'])
    elif path == 'dpkg.log.3':
        return MockFile(['2016-01-01 00:00:00 upgrade pkg:arch 1 2'])
    elif path == 'dpkg.log.installs':
        return MockFile(['2016-01-01 00:00:00 install pkg:arch <none> 2'])
    elif path == 'dpkg.log.upgrades':
        return MockFile(['2016-01-01 00:00:00 upgrade pkg:arch 1 2'])
    elif path == 'dpkg.log.removes':
        return MockFile(['2016-01-01 00:00:00 remove pkg:arch 1 <none>'])
    elif path == 'dpkg.log.purges':
        return MockFile(['2016-01-01 00:00:00 purge pkg:arch 1 <none>'])
    elif path == 'dpkg.log.non-applicable':
        return MockFile([
            '2016-01-01 00:00:00 status pkg:arch',
            '2016-01-01 00:00:01 configure pkg some other args',
            '2016-01-01 00:00:02 startup pkg:arch:version:v',
            '2016-01-01 00:00:03 installed this package pkg:arch',
            '2016-01-01 00:00:04 upgrad arg',
            '2017-01-01 00:00:00 upgrade pkg:arch 2 3'
        ])
    elif path == 'dpkg.log.4':
        return MockFile([
            '2016-01-01 00:00:00 install firstpackage:arch <none> 1',
            '2016-01-01 00:00:01 install secondpackage:arch <none> 1',
            '2016-01-01 00:00:02 install thirdpackage:arch <none> 1',
        ])
    elif path == 'dpkg.txt':
        return MockFile(['2016-01-01 00:00:00 upgrade pkg:arch 1 2'])
    elif path == 'apt.log':
        return MockFile(['2015-01-01 00:00:00 upgrade pkg:arch 0 1'])


@patch('apt-rollback.open_', mock_open_)
@patch('os.scandir')
class GetActionsTestCase(unittest.TestCase):

    @staticmethod
    def build_entry(name, is_file=True, path=None):
        entry = Mock()
        entry.name = name
        entry.is_file.return_value = is_file
        if path:
            entry.path = path
        else:
            entry.path = name
        return entry

    def test_no_valid_files(self, mock_scandir):
        '''get_actions returns no actions from files that aren't dpkg logs'''
        file1 = self.build_entry('dpkg.txt')
        file2 = self.build_entry('apt.log')
        dir1 = self.build_entry('dir', False)

        mock_scandir.return_value = [file1, file2, dir1]
        actions = aptrollback.get_actions('2017-01-01 00:00:00')
        self.assertEqual(len(list(actions)), 0)

    def test_action_parsing(self, mock_scandir):
        '''Validate the format of actions returned by get_actions'''
        file1 = self.build_entry('dpkg.log.1')
        mock_scandir.return_value = [file1]

        actions = list(aptrollback.get_actions('2014-01-01 00:00:00'))
        self.assertEqual(actions[0], {
            'action': 'upgrade',
            'package': 'pkg',
            'arch': 'arch',
            'fromversion': '2',
            'toversion': '3'
        })

    def test_install_actions(self, mock_scandir):
        '''get_actions evaluates install actions'''
        file1 = self.build_entry('dpkg.log.installs')
        mock_scandir.return_value = [file1]

        actions = list(aptrollback.get_actions('2014-01-01 00:00:00'))
        self.assertEqual(len(actions), 1)

    def test_upgrade_actions(self, mock_scandir):
        '''get_actions evaluates upgrade actions'''
        file1 = self.build_entry('dpkg.log.upgrades')
        mock_scandir.return_value = [file1]

        actions = list(aptrollback.get_actions('2014-01-01 00:00:00'))
        self.assertEqual(len(actions), 1)

    def test_remove_actions(self, mock_scandir):
        '''get_actions evaluates remove actions'''
        file1 = self.build_entry('dpkg.log.removes')
        mock_scandir.return_value = [file1]

        actions = list(aptrollback.get_actions('2014-01-01 00:00:00'))
        self.assertEqual(len(actions), 1)

    def test_purge_actions(self, mock_scandir):
        '''get_actions evaluates purge actions'''
        file1 = self.build_entry('dpkg.log.purges')
        mock_scandir.return_value = [file1]

        actions = list(aptrollback.get_actions('2014-01-01 00:00:00'))
        self.assertEqual(len(actions), 1)

    def test_non_applicable_actions(self, mock_scandir):
        '''get_actions ignores other types of actions'''
        file1 = self.build_entry('dpkg.log.non-applicable')
        mock_scandir.return_value = [file1]

        actions = list(aptrollback.get_actions('2014-01-01 00:00:00'))
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0], {
            'action': 'upgrade',
            'package': 'pkg',
            'arch': 'arch',
            'fromversion': '2',
            'toversion': '3'
        })

    def test_file_ordering(self, mock_scandir):
        '''get_actions evaluates files in reversed chronological order'''
        file1 = self.build_entry('dpkg.log.1')
        file2 = self.build_entry('dpkg.log.2')
        file3 = self.build_entry('dpkg.log.3')
        mock_scandir.return_value = [file1, file2, file3]

        actions = list(aptrollback.get_actions('2014-01-01 00:00:00'))
        self.assertEqual(len(actions), 3)
        self.assertEqual(actions[0]['fromversion'], '2')
        self.assertEqual(actions[1]['fromversion'], '1')
        self.assertEqual(actions[2]['fromversion'], '<none>')

    def test_action_ordering(self, mock_scandir):
        '''get_actions evaluates actions in reversed chronological order'''
        file1 = self.build_entry('dpkg.log.4')
        mock_scandir.return_value = [file1]

        actions = list(aptrollback.get_actions('2014-01-01 00:00:00'))
        self.assertEqual(len(actions), 3)
        self.assertEqual(actions[0]['package'], 'thirdpackage')
        self.assertEqual(actions[1]['package'], 'secondpackage')
        self.assertEqual(actions[2]['package'], 'firstpackage')

    def test_reach_timestamp(self, mock_scandir):
        '''get_actions returns no action older than the target timestamp'''
        file1 = self.build_entry('dpkg.log.4')
        mock_scandir.return_value = [file1]

        actions = list(aptrollback.get_actions('2016-01-01 00:00:01'))
        self.assertEqual(len(actions), 2)
        self.assertEqual(actions[0]['package'], 'thirdpackage')
        self.assertEqual(actions[1]['package'], 'secondpackage')


class MockResponse:

    def __init__(self, content):
        self.content = content

    def read(self):
        return self.content.encode()


def mock_urllib_request_urlopen(url):

    if url == '{}/binary/package/'.format(aptrollback.REPOSITORY_URL):
        return MockResponse('''
            <html><body>
                <a href="/package/options/url">version</a>
                <a href="/package/options/wrongurl">wrong version</a>
            </body></html>
        ''')
    elif url == urljoin(aptrollback.REPOSITORY_URL, '/package/options/url'):
        return MockResponse('''
            <html><body>
                <a href="/file/url">package_randomsuffix_arch.deb</a>
                <a href="/file/wrongurl">package_randomsuffix_arch2.deb</a>
            </body></html>
        ''')


class DownloadPackageTestCase(unittest.TestCase):

    @patch('os.path.exists', Mock(return_value=False))
    @patch('urllib.request.urlopen', mock_urllib_request_urlopen)
    @patch('urllib.request.urlretrieve')
    def test_download_new_package(self, mock_urlretrieve):
        prints = []
        with patch('apt-rollback.print', lambda m: prints.append(m)):
            aptrollback.download_package('/dir', 'package', 'arch', 'version')
        mock_urlretrieve.assert_called_once_with(
            urljoin(aptrollback.REPOSITORY_URL, '/file/url'),
            '/dir/package_version_arch.deb'
        )
        self.assertEqual(prints[0], 'Downloading {}'.format(
            urljoin(aptrollback.REPOSITORY_URL, '/file/url')))
        self.assertEqual(prints[1], 'Finished downloading {}'.format(
            urljoin(aptrollback.REPOSITORY_URL, '/file/url')))

    @patch('os.path.exists', Mock(return_value=True))
    def test_download_existing_package(self):
        prints = []
        with patch('apt-rollback.print', lambda m: prints.append(m)):
            aptrollback.download_package('/dir', 'package', 'arch', 'version')
        self.assertEqual(prints[0], 'We already have {}, neat!'.format(
            'package_version_arch.deb'))


def build_mock_argparser(timestamp, force, print_):
    mock_argparser = Mock()
    mock_argparser.return_value.parse_args.return_value.timestamp = timestamp
    mock_argparser.return_value.parse_args.return_value.force = force
    mock_argparser.return_value.parse_args.return_value.print = print_
    return mock_argparser


class MockFuture:

    def __init__(self, failed):
        self.failed = failed

    def exception(self):
        return self.failed


class MockTPE:

    def __init__(self, *args, **kwargs):
        pass

    def submit(self, *args, **kwargs):
        version = args[4]
        return (
            MockFuture(failed=True) if version.startswith('failed')
            else MockFuture(failed=False)
        )

    def __enter__(self, *args, **kwargs):
        return self

    def __exit__(self, *args, **kwargs):
        pass


class MainTestCase(unittest.TestCase):

    @patch('argparse.ArgumentParser', build_mock_argparser('timestamp', False,
                                                           False))
    @patch('apt-rollback.get_actions', Mock(return_value=[]))
    def test_no_operations(self):
        prints = []
        with patch('apt-rollback.print', lambda m, *a, **k: prints.append(m)):
            with self.assertRaises(SystemExit) as cm:
                aptrollback.main()
                self.assertEqual(cm.exception.error_code, 0)
        self.assertEqual(prints[0], 'No package operations to revert')

    @patch('argparse.ArgumentParser', build_mock_argparser('timestamp', False,
                                                           False))
    @patch('os.mkdir', Mock())
    @patch('apt-rollback.ThreadPoolExecutor', MockTPE)
    @patch('apt-rollback.wait', lambda x: (x, None))
    def test_failed_and_not_force(self):
        actions = [
            {'action': 'upgrade', 'package': 'p1', 'arch': 'a1',
             'fromversion': 'failed', 'toversion': '2'},
            {'action': 'upgrade', 'package': 'p2', 'arch': 'a1',
             'fromversion': 'notfailed', 'toversion': '2'},
        ]
        prints = []
        with patch('apt-rollback.print', lambda m, *a, **k: prints.append(m)):
            with patch('apt-rollback.get_actions', Mock(return_value=actions)):
                with self.assertRaises(SystemExit) as cm:
                    aptrollback.main()
                    self.assertEqual(cm.exception.error_code, 1)
        self.assertEqual(prints[0],
                        "\nThe following packages couldn't be downloaded. "
                        "Please download them manually, place them in "
                        "/tmp/apt-rollback-timestamp/ and run this command "
                        "again. If you wish to ignore these packages run the "
                        "command again using the -f flag.\n")
        self.assertEqual(prints[1],
                         '{}:{} {}'.format(actions[0]['package'],
                                           actions[0]['arch'],
                                           actions[0]['fromversion']))

    @patch('argparse.ArgumentParser', build_mock_argparser('timestamp', True,
                                                           False))
    @patch('os.mkdir', Mock())
    @patch('apt-rollback.ThreadPoolExecutor', MockTPE)
    @patch('apt-rollback.wait', lambda x: (x, None))
    def test_failed_and_force(self):
        actions = [
            {'action': 'upgrade', 'package': 'p1', 'arch': 'a1',
             'fromversion': 'failed', 'toversion': '2'},
            {'action': 'upgrade', 'package': 'p2', 'arch': 'a1',
             'fromversion': '1.5', 'toversion': '2'},
        ]
        system_calls = []
        with patch('os.system', lambda m, *a, **k: system_calls.append(m)):
            with patch('apt-rollback.get_actions', Mock(return_value=actions)):
                aptrollback.main()

        command = re.search('dpkg -i (.*)', system_calls[0])
        installs = command.group(1).split(' ')
        self.assertIn('/tmp/apt-rollback-timestamp/p2_1.5_a1.deb', installs)

    @patch('argparse.ArgumentParser', build_mock_argparser('timestamp', False,
                                                           False))
    @patch('os.mkdir', Mock())
    @patch('apt-rollback.ThreadPoolExecutor', MockTPE)
    @patch('apt-rollback.wait', lambda x: (x, None))
    def test_general(self):
        actions = reversed([
            {'action': 'install', 'package': 'p1', 'arch': 'i386',
             'fromversion': '<none>', 'toversion': '1'},
            {'action': 'upgrade', 'package': 'p1', 'arch': 'i386',
             'fromversion': '1', 'toversion': '2'},
            {'action': 'install', 'package': 'p1', 'arch': 'amd64',
             'fromversion': '<none>', 'toversion': '1'},
            {'action': 'purge', 'package': 'p2', 'arch': 'amd64',
             'fromversion': '1', 'toversion': '<none>'},
            {'action': 'remove', 'package': 'p3', 'arch': 'amd64',
             'fromversion': '1', 'toversion': '<none>'},
            {'action': 'upgrade', 'package': 'p4', 'arch': 'amd64',
             'fromversion': '2', 'toversion': '1'},
            {'action': 'upgrade', 'package': 'p4', 'arch': 'amd64',
             'fromversion': '1', 'toversion': '3'},
        ])
        system_calls = []
        with patch('os.system',
                   lambda m, *a, **k: system_calls.append(m)):
            with patch('apt-rollback.get_actions', Mock(return_value=actions)):
                aptrollback.main()

        command = re.search('dpkg -i (.*) -P (.*)', system_calls[0])
        installs = command.group(1).split(' ')
        uninstalls = command.group(2).split(' ')
        self.assertIn('/tmp/apt-rollback-timestamp/p2_1_amd64.deb', installs)
        self.assertIn('/tmp/apt-rollback-timestamp/p3_1_amd64.deb', installs)
        self.assertIn('/tmp/apt-rollback-timestamp/p4_2_amd64.deb', installs)
        self.assertIn('p1:amd64', uninstalls)
        self.assertIn('p1:i386', uninstalls)

    @patch('argparse.ArgumentParser', build_mock_argparser('timestamp', False,
                                                           False))
    @patch('os.mkdir', Mock())
    @patch('apt-rollback.ThreadPoolExecutor', MockTPE)
    @patch('apt-rollback.wait', lambda x: (x, None))
    def test_no_installs(self):
        actions = reversed([
            {'action': 'install', 'package': 'p1', 'arch': 'i386',
             'fromversion': '<none>', 'toversion': '1'},
            {'action': 'upgrade', 'package': 'p1', 'arch': 'i386',
             'fromversion': '1', 'toversion': '2'},
            {'action': 'install', 'package': 'p1', 'arch': 'amd64',
             'fromversion': '<none>', 'toversion': '1'},
        ])
        system_calls = []
        with patch('os.system', lambda m, *a, **k: system_calls.append(m)):
            with patch('apt-rollback.get_actions', Mock(return_value=actions)):
                aptrollback.main()

        command = re.search('dpkg -P (.*)', system_calls[0])
        uninstalls = command.group(1).split(' ')
        self.assertIn('p1:amd64', uninstalls)
        self.assertIn('p1:i386', uninstalls)

    @patch('argparse.ArgumentParser', build_mock_argparser('timestamp', False,
                                                           False))
    @patch('os.mkdir', Mock())
    @patch('apt-rollback.ThreadPoolExecutor', MockTPE)
    @patch('apt-rollback.wait', lambda x: (x, None))
    def test_no_uninstalls(self):
        actions = reversed([
            {'action': 'purge', 'package': 'p2', 'arch': 'amd64',
             'fromversion': '1', 'toversion': '<none>'},
            {'action': 'remove', 'package': 'p3', 'arch': 'amd64',
             'fromversion': '1', 'toversion': '<none>'},
            {'action': 'upgrade', 'package': 'p4', 'arch': 'amd64',
             'fromversion': '2', 'toversion': '1'},
            {'action': 'upgrade', 'package': 'p4', 'arch': 'amd64',
             'fromversion': '1', 'toversion': '3'},
        ])
        system_calls = []
        with patch('os.system', lambda m, *a, **k: system_calls.append(m)):
            with patch('apt-rollback.get_actions', Mock(return_value=actions)):
                aptrollback.main()

        command = re.search('dpkg -i (.*)', system_calls[0])
        installs = command.group(1).split(' ')
        self.assertIn('/tmp/apt-rollback-timestamp/p2_1_amd64.deb', installs)
        self.assertIn('/tmp/apt-rollback-timestamp/p3_1_amd64.deb', installs)
        self.assertIn('/tmp/apt-rollback-timestamp/p4_2_amd64.deb', installs)


if __name__ == '__main__':
    unittest.main()
