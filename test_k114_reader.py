import unittest
from unittest.mock import patch, Mock
from k114_reader import K114Reader

class TestK114Reader(unittest.TestCase):
    @patch('serial.Serial')
    def test_connect(self, mock_serial):
        reader = K114Reader("COM1")
        mock_serial.return_value.is_open = True
        self.assertTrue(reader.connect())

    @patch('serial.Serial')
    def test_send_receive(self, mock_serial):
        reader = K114Reader("COM1")
        mock_serial.return_value.read.side_effect = [b'\x01', b'\x02', b'\x03\x04']
        mock_serial.return_value.write.return_value = None
        response = reader.send_receive(b'\x00')
        self.assertEqual(response, b'\x01\x02\x03\x04')

    def test_validate_response(self):
        reader = K114Reader("COM1")
        response = b'\x01\x02\x03\x04\x05\x06'
        self.assertTrue(reader._validate_response(response))

if __name__ == '__main__':
    unittest.main()
