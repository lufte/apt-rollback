import os
import sys
import argparse
import unittest
from unittest.mock import Mock, patch
from importlib import import_module
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
aptrollback = import_module('apt-rollback')


class ParseTimestampTestCase(unittest.TestCase):

    @patch('apt-rollback.datetime', Mock(strptime=Mock(return_value=True)))
    def test_valid_timestamp(self):
        self.assertEqual('timestamp',
                         aptrollback.parse_timestamp('timestamp'))

    def test_invalid_timestamp(self):
        self.assertRaises(argparse.ArgumentTypeError,
                          aptrollback.parse_timestamp, 'timestamp')


class OpenTestCase(unittest.TestCase):

    @patch('apt-rollback.gzip')
    def test_gzip_file(self, mock_gzip):
        mock_gzip.open = Mock(return_value='zip file!')
        self.assertEqual(aptrollback.open_('myfile.gz'),
                         mock_gzip.open.return_value)

    @patch('apt-rollback.open')
    def test_gzip_file(self, mock_open):
        mock_open.return_value = 'text file!'
        self.assertEqual(aptrollback.open_('myfile.log'),
                         mock_open.return_value)



if __name__ == '__main__':
    unittest.main()
