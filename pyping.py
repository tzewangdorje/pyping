"""Pying - Python Ping.

Usage:
  pying.py [-c cycles] [-i interval] <destination>
  pying.py -h
  pying.py -V

Options:
  -h     	Show this screen.
  -V     	Show version.
  -c=cycles	Number of cycles to count [default: 0]
  -i=interval	Interval between pings [default: 1]

"""
from docopt import docopt
import socket
import struct
import os
import select
import time
import datetime
import numpy
import traceback


class SocketTimeout(Exception):
    pass


class Icmp(object):
    TYPE_ECHO_REPLY = 0
    TYPE_ECHO_REQUEST = 8

    # http://stackoverflow.com/questions/1767910/checksum-udp-calculation-python
    @staticmethod
    def _carry_around_add(a, b):
        c = a + b
        return (c & 0xffff) + (c >> 16)

    @staticmethod
    def _checksum(msg):
        if len(msg) % 2 != 0:
            msg += "\x00"
        s = 0
        for i in range(0, len(msg), 2):
            w = ord(msg[i]) + (ord(msg[i + 1]) << 8)
            s = Icmp._carry_around_add(s, w)
        return ~s & 0xffff

    @staticmethod
    def pack(identity, icmp_type, data, sequence):
        header = struct.pack('bbHHh', icmp_type, 0, 0, identity, sequence)
        csum = Icmp._checksum(header + data)
        header = struct.pack('bbHHh', icmp_type, 0, csum, identity, sequence)
        packet = header + data
        size_header = len(header)
        size_data = len(data)
        return packet, size_header, size_data

    @staticmethod
    def unpack(packed):
        without_ip_header = packed[20:]
        header = without_ip_header[:8]
        data = without_ip_header[8:]
        icmp_type, icmp_code, csum, identity, sequence = struct.unpack('bbHHh', header)
        return icmp_type, icmp_code, csum, identity, sequence, data


class Pying(object):
    def __init__(self):
        self.__name__ = "Pying"
        self.__version__ = 0.1
        self._socket = None
        self.cycles = None
        self.interval = 1
        self._completed = 0
        self._sequence = 0
        self.destination = None
        self.identity = None
        self._stats = []
        self._request_time = None

    def _get_time(self):
        return datetime.datetime.now()

    def run(self):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
        self._socket.setblocking(0)
        if isinstance(self.cycles, basestring):
            self.cycles = int(self.cycles)
        first = True
        self.identity = os.getpid()
        while self.cycles is None or self._sequence < self.cycles:
            self._request_time = self._get_time()
            self._sequence += 1
            packet, size_header, size_data = Icmp.pack(self.identity,
                                                       Icmp.TYPE_ECHO_REQUEST,
                                                       "Ping Pong",
                                                       self._sequence)
            if first:
                print "PING {0} ({1}) {2}({3}) bytes of data.".format(self.destination,
                                                                      self.destination,
                                                                      size_data,
                                                                      size_header + size_data)
            self.send(packet)
            received = False
            try:
                while not received:
                    if self.receive():
                        received = True
                        self._completed += 1
                        time.sleep(float(self.interval))
            except SocketTimeout as e:
                pass  # socket time out - break out of while loop and increment sequence
            except:
                raise
            first = False
        if self._completed == 0:
            packetloss = 100
        else:
            packetloss = 100 - (100 * (self._completed / self._sequence))
        totaltime = sum(self._stats)
        print "\n--- {0} ping statistics ---".format(self.destination)
        print "{0} packets transmitted, {1} received, {2}% packet loss, time {3}ms".format(
            self._sequence,
            self._completed,
            packetloss,
            totaltime)
        rtt = self._get_rtt_stats(self._stats)
        print "rtt min/avg/max/mdev = {0}/{1}/{2}/{3} ms".format(rtt["min"],
                                                                 rtt["avg"],
                                                                 rtt["max"],
                                                                 rtt["mdev"])

    def _get_rtt_stats(self, stats):
        rtt_min = round(min(stats), 3)
        rtt_max = round(max(stats), 3)
        rtt_avg = round(numpy.mean(stats), 3)
        rtt_mdev = round(numpy.std(stats), 3)
        return {
            "min": rtt_min,
            "avg": rtt_avg,
            "max": rtt_max,
            "mdev": rtt_mdev
        }

    def version_info(self):
        return self.__name__ + " " + str(self.__version__)

    def send(self, packet):
        destination = (socket.gethostbyname(self.destination), 0)
        self._socket.sendto(packet, destination)

    def receive(self):
        timeout_in_seconds = 1
        ready = select.select([self._socket], [], [], timeout_in_seconds)
        if ready[0]:
            data, addr = self._socket.recvfrom(1508)
            bytes_received = len(data)
            ip = addr[0]
            icmp_type, icmp_code, csum, identity, sequence, data = Icmp.unpack(data)
            # print icmp_type, icmp_code, csum, identity, sequence, data
            if icmp_type == Icmp.TYPE_ECHO_REPLY and identity == self.identity:
                time_delta = self._get_time() - self._request_time
                response_time = time_delta.total_seconds() * 1000
                self._stats.append(response_time)
                print "{0} bytes from {1} ({2}): icmp_seq={3} ttl=64 time={4} ms".format(bytes_received,
                                                                                         ip,
                                                                                         ip,
                                                                                         sequence,
                                                                                         response_time)
                return True
            else:
                return False
        else:
            raise SocketTimeout()


if __name__ == '__main__':
    args = docopt(__doc__)
    pying = Pying()
    if args["-V"]:
        print pying.version_info()
    else:
        pying.destination = args["<destination>"]
        try:
            pying.cycles = args["-c"]
        except:
            pass  # cycles not set, leave as default
        try:
            pying.interval = args["-i"]
        except:
            pass  # interval not set, leave as default
        pying.run()
