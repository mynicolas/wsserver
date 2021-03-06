# _*_ coding:utf-8 _*_
import socket
import threading
import sys
import os
import MySQLdb
import base64
import hashlib
import struct
import time

updateSql = "UPDATE websocket SET content='%s' WHERE id=1"
getSql = "SELECT content FROM websocket WHERE id=1"

# ====== config ======
HOST = '0.0.0.0'
PORT = 3368
MAGIC_STRING = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
HANDSHAKE_STRING = "HTTP/1.1 101 Switching Protocols\r\n" \
    "Upgrade:websocket\r\n" \
    "Connection: Upgrade\r\n" \
    "Sec-WebSocket-Accept: {1}\r\n" \
    "WebSocket-Location: ws://{2}/chat\r\n" \
    "WebSocket-Protocol:chat\r\n\r\n"


class Update(threading.Thread):
    def __init__(self, connection):
        threading.Thread.__init__(self)
        self.con = connection

    def run(self):
        while True:
            self.recvData(1024)

    def recvData(self, num):
        all_data = self.con.recv(num)
        if not len(all_data):
            return False

        code_len = ord(all_data[1]) & 127
        if code_len == 126:
            masks = all_data[4:8]
            data = all_data[8:]
        elif code_len == 127:
            masks = all_data[10:14]
            data = all_data[14:]
        else:
            masks = all_data[2:6]
            data = all_data[6:]
        raw_str = ""
        i = 0
        for d in data:
            raw_str += chr(ord(d) ^ ord(masks[i % 4]))
            i += 1

        db = MySQLdb.connect(host="localhost", user="root",
                             passwd="root", db="ws", charset="utf8")
        cursor = db.cursor()
        cursor.execute(updateSql % raw_str)
        db.commit()
        return raw_str


class Th(threading.Thread):
    def __init__(self, connection):
        threading.Thread.__init__(self)
        self.con = connection

    def run(self):
        while True:
            try:
                db = MySQLdb.connect(
                    host="localhost",
                    user="root",
                    passwd="root",
                    db="ws",
                    charset="utf8")
                cursor = db.cursor()
                cursor.execute(getSql)
                data = cursor.fetchone()[0]
                self.send_data(data)
                self.check()

            except:
                self.con.close()

    def check(self):
        newContent = None
        db = MySQLdb.connect(host="localhost", user="root",
                             passwd="root", db="ws", charset="utf8")
        cursor = db.cursor()
        cursor.execute(getSql)
        content = cursor.fetchone()[0]
        db.close()
        update = Update(self.con)
        update.start()
        while True:
            time.sleep(1)
            db = MySQLdb.connect(host="localhost", user="root",
                                 passwd="root", db="ws", charset="utf8")
            cursor = db.cursor()
            cursor.execute(getSql)
            thisContent = cursor.fetchone()[0]
            db.close()
            print 'looper: %s' % thisContent
            if content != thisContent:
                newContent = thisContent
                content = thisContent
                # break

                self.send_data(newContent)

    # send data
    def send_data(self, data):
        db = MySQLdb.connect(host="localhost", user="root",
                             passwd="root", db="ws", charset="utf8")
        cursor = db.cursor()
        cursor.execute(getSql)
        data = cursor.fetchone()[0]
        print "send data: \t%s" % data
        if data:
            data = str(data)
        else:
            return False
        token = "\x81"
        length = len(data)
        if length < 126:
            token += struct.pack("B", length)
        elif length <= 0xFFFF:
            token += struct.pack("!BH", 126, length)
        else:
            token += struct.pack("!BQ", 127, length)
            # struct为Python中处理二进制数的模块，二进制流为C，或网络流的形式。
        data = '%s%s' % (token, data)
        self.con.send(data)
        return True

# handshake


def handshake(con):
    headers = {}
    shake = con.recv(1024)

    if not len(shake):
        return False

    header, data = shake.split('\r\n\r\n', 1)
    for line in header.split('\r\n')[1:]:
        key, val = line.split(': ', 1)
        headers[key] = val

    if 'Sec-WebSocket-Key' not in headers:
        print ('This socket is not websocket, client close.')
        con.close()
        return False

    sec_key = headers['Sec-WebSocket-Key']
    res_key = base64.b64encode(hashlib.sha1(sec_key + MAGIC_STRING).digest())
    print res_key

    str_handshake = HANDSHAKE_STRING.replace(
        '{1}', res_key).replace('{2}', HOST + ':' + str(PORT))
    print str_handshake
    con.send(str_handshake)
    return True


def new_service():
    """start a service socket and listen
    when coms a connection, start a new thread to handle it"""

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((HOST, PORT))
    sock.listen(1000)
    print "bind %s,ready to use" % PORT

    while True:
        connection, address = sock.accept()
        # 返回元组（socket,add），accept调用时会进入wait状态
        print "Got connection from ", address
        isHandshake = handshake(connection)
        if isHandshake:
            print "handshake success"
            try:
                t = Th(connection)
                t.start()
                print 'new thread for client ...'
            except:
                print 'start new thread error'
                connection.close()

if __name__ == '__main__':
    new_service()
