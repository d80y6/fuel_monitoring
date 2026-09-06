import unittest
from unittest.mock import patch, Mock
from k114_tcp_reader import K114TCPReader

class TestK114TCPReader(unittest.TestCase):
    @patch('socket.socket')
    def test_connect(self, mock_socket):
        reader = K114TCPReader("23.94.76.44", port=2000)
        mock_socket.return_value.connect.return_value = None
        self.assertTrue(reader.connect())

    @patch('socket.socket')
    def test_send_receive(self, mock_socket):
        reader = K114TCPReader("23.94.76.44", port=2000)
        mock_socket.return_value.recv.side_effect = [b'\x01', b'\x02', b'\x03\x04']
        mock_socket.return_value.sendall.return_value = None
        response = reader.send_receive(b'\x00')
        self.assertEqual(response, b'\x01\x02\x03\x04')

if __name__ == '__main__':
    unittest.main()
