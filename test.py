import argparse
import os
import sys
import unittest
from importlib import import_module
from unittest.mock import Mock, patch

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
    def test_gzip_file(self, mock_open):
        '''open_ uses built-in open when filename doesn't end with .gz'''
        mock_open.return_value = 'text file!'
        self.assertEqual(aptrollback.open_('myfile.log'),
                         mock_open.return_value)


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


if __name__ == '__main__':
    unittest.main()
