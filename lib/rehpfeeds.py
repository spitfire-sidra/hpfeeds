#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Copyright (C) 2010-2013 Mark Schloesser <ms@mwcollect.org>
This file is part of hpfeeds - https://github.com/rep/hpfeeds
See the file 'LICENSE' for copying permission.
"""

import sys
import struct
import socket
import hashlib
import logging
import time
import threading
import ssl


logger = logging.getLogger('pyhpfeeds')


OPCODE_ERROR = 0
OPCODE_INFO = 1
OPCODE_AUTH = 2
OPCODE_PUBLISH = 3
OPCODE_SUBSCRIBE = 4
BUFFER_SIZE = 16384


def make_message(opcode, data):
    """
    Making a message. Each message carries a message header and data.
    """
    message = '{0}{1}'
    length = 5 + len(data)
    header = struct.pack('!iB', length, opcode)
    return message.format(header, data)


def make_pair(data):
    """
    Returning a (length, data) pair.
    """
    pair = '{0}{1}'
    length = struct.pack('!B', len(data))
    return pair.format(length, data)


def concate_pairs(pairs):
    """
    Concatenating pairs list.
    >>> concate_pairs([u'a', b'0x11', unicode('c')])
    u'a0x11c'
    """
    return ''.join(pairs)


def make_publish_message(ident, chann, data):
    """
    Making a message for publication
    """
    pairs = list()
    pairs.append(make_pair(ident))
    pairs.append(make_pair(chann))
    pairs.append(data)
    return make_message(OPCODE_PUBLISH, concate_pairs(pairs))


def make_subscribe_message(ident, chann):
    """
    Making a message for subscription
    """
    pairs = list()
    pairs.append(make_pair(ident))
    pairs.append(chann)
    return make_message(OPCODE_SUBSCRIBE, concate_pairs(pairs))


def make_auth_message(rand, ident, secret):
    """
    Making a message for authentication
    """
    sha1_hash = hashlib.sha1(''.join([rand, secret])).digest()
    pairs = list()
    pairs.append(make_pair(ident))
    pairs.append(sha1_hash)
    return make_message(OPCODE_AUTH, concate_pairs(pairs))


class FeedException(Exception): pass


class Disconnect(Exception): pass


# need for a better name
class Feed(object):

    def __init__(self):
        self.buf = bytearray()

    def __iter__(self):
        return self

    def next(self):
        return self.unpack()

    def feed(self, data):
        self.buf.extend(data)

    def unpack(self):
        if len(self.buf) < 5:
            raise StopIteration('No message.')

        ml, opcode = struct.unpack('!iB', buffer(self.buf, 0, 5))
        if len(self.buf) < ml:
            raise StopIteration('No message.')

        data = bytearray(buffer(self.buf, 5, ml - 5))
        del self.buf[:ml]
        return opcode, data


class HPC(object):

    def __init__(self, host, port, ident, secret, timeout=3, reconnect=True, sleepwait=20):
        self.host, self.port = host, port
        self.ident, self.secret = ident, secret
        self.timeout = timeout
        self.reconnect = reconnect
        self.sleepwait = sleepwait
        self._init_private_vars()
        self.try_connect()

    def _init_private_vars(self):
        """
        Initializing variables for private usage.
        """
        self._broker_name = 'UNKNOWN'
        self._connected = False
        self._stop = False
        self._socket = None
        self._subscriptions = set()
        self._unpacker = Feed() # need for a better name

    def get_socket(self, family):
        """
        Get a socket for connection
        """
        return socket.socket(family, socket.SOCK_STREAM)

    def recv(self):
        """
        Receiving data from broker
        """
        try:
            data = self._socket.recv(BUFFER_SIZE)
        except socket.timeout:
            logger.warn('Socket timeout')
            raise
        except socket.error as e:
            logger.warn("Socket error: %s", e)
            raise Disconnect()
        return data

    def send(self, data):
        """
        Sendinf data to broker
        """
        try:
            self._socket.sendall(data)
        except socket.timeout:
            logger.warn("Timeout while sending - disconnect.")
            raise
        except socket.error as e:
            logger.warn("Socket error: %s", e)
            raise Disconnect()
        else:
            return True
        return False

    def try_connect(self):
        """
        Trying to connect to the broker
        """
        while self._stop == False and not self._connected:
            try:
                self.connect()
            except socket.error as e:
                logger.warn(
                    'Socket error while connecting: {0}'.format(e))
                time.sleep(self.sleepwait)
            except FeedException as e:
                logger.warn(
                    'FeedException while connecting: {0}'.format(e))
                time.sleep(self.sleepwait)
            except Disconnect as e:
                logger.warn('Disconnect while connecting.')
                time.sleep(self.sleepwait)
            except Exception:
                logger.warn('An unexcepted error occured.')
                time.sleep(self.sleepwait)
            else:
                # if connected to the broker, then break this while loop
                break


    def connect(self):
        self.close_old()

        logger.info('connecting to {0}:{1}'.format(self.host, self.port))

        # Try other resolved addresses (IPv4 or IPv6) if failed.
        ainfos = socket.getaddrinfo(
            self.host, 1, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for ainfo in ainfos:
            addr_family = ainfo[0]
            addr = ainfo[4][0]
            try:
                self._socket = self.get_socket(addr_family)
                self._socket.settimeout(self.timeout)
                self._socket.connect((addr, self.port))
            except:
                import traceback
                traceback.print_exc()
                # print 'Could not connect to broker. %s[%s]' % (self.host,
                # addr)
                continue
            else:
                self._connected = True
                break

        if self._connected == False:
            raise FeedException(
                'Could not connect to broker [%s].' % (self.host))

        try:
            d = self._socket.recv(BUFFER_SIZE)
        except socket.timeout:
            raise FeedException('Connection receive timeout.')

        self._unpacker.feed(d)
        for opcode, data in self._unpacker:
            if opcode == OPCODE_INFO:
                rest = buffer(data, 0)
                name, rest = rest[
                    1:1 + ord(rest[0])], buffer(rest, 1 + ord(rest[0]))
                rand = str(rest)

                logger.debug(
                    'info message name: {0}, rand: {1}'.format(name, repr(rand)))
                self._broker_name = name

                self.send(make_auth_message(rand, self.ident, self.secret))
                break
            else:
                raise FeedException('Expected info message at this point.')

        self._socket.settimeout(None)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

        if sys.platform in ('linux2', ):
            self._socket.setsockopt(socket.SOL_TCP, socket.TCP_KEEPIDLE, 10)

    def run(self, message_callback, error_callback):
        while not self._stop:
            self._subscribe()
            while self._connected:
                try:
                    d = self.recv()
                    self._unpacker.feed(d)

                    for opcode, data in self._unpacker:
                        if opcode == OPCODE_PUBLISH:
                            rest = buffer(data, 0)
                            ident, rest = rest[
                                1:1 + ord(rest[0])], buffer(rest, 1 + ord(rest[0]))
                            chan, content = rest[
                                1:1 + ord(rest[0])], buffer(rest, 1 + ord(rest[0]))

                            message_callback(str(ident), str(chan), content)
                        elif opcode == OPCODE_ERROR:
                            error_callback(data)

                except Disconnect:
                    self._connected = False
                    logger.info('Disconnected from broker.')
                    break

                # end run loops if stopped
                if self._stop:
                    break

            if not self._stop and self.reconnect:
                # connect again if disconnected
                self.tryconnect()

        logger.info('Stopped, exiting run loop.')

    def wait(self, timeout=1):
        self._socket.settimeout(timeout)

        try:
            d = self.recv()
            if not d:
                return None

            self._unpacker.feed(d)
            for opcode, data in self._unpacker:
                if opcode == OPCODE_ERROR:
                    return data
        except Disconnect:
            pass

        return None

    def close_old(self):
        if self.s:
            try:
                self._socket.close()
            except:
                pass

    def subscribe(self, chaninfo):
        if type(chaninfo) == str:
            chaninfo = [chaninfo, ]
        for c in chaninfo:
            self.subscriptions.add(c)

    def _subscribe(self):
        for c in self.subscriptions:
            try:
                logger.debug('Sending subscription for {0}.'.format(c))
                self.send(make_subscribe_message(self.ident, c))
            except Disconnect:
                self._connected = False
                logger.info('Disconnected from broker (in subscribe).')
                if not self.reconnect:
                    raise
                break

    def publish(self, chaninfo, data):
        if type(chaninfo) == str:
            chaninfo = [chaninfo, ]
        for c in chaninfo:
            try:
                self.send(make_publish_message(self.ident, c, data))
            except Disconnect:
                self._connected = False
                logger.info('Disconnected from broker (in publish).')
                if self.reconnect:
                    self.tryconnect()
                else:
                    raise

    def stop(self):
        self._stop = True

    def close(self):
        try:
            self._socket.close()
        except:
            logger.debug('Socket exception when closing (ignored though).')


class HPC_SSL(HPC):

    def __init__(self, *args, **kwargs):
        self.certfile = kwargs.pop("certfile", None)
        HPC.__init__(self, *args, **kwargs)

    def get_socket(self, addr_family):
        s = socket.socket(addr_family, socket.SOCK_STREAM)
        return ssl.wrap_socket(s, ca_certs=self.certfile, ssl_version=3, cert_reqs=2)


def new(host=None, port=10000, ident=None, secret=None, timeout=3, reconnect=True, sleepwait=20, certfile=None):
    if certfile:
        return HPC_SSL(host, port, ident, secret, timeout, reconnect, certfile=certfile)
    return HPC(host, port, ident, secret, timeout, reconnect)
