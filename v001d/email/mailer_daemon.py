import datetime
import hashlib
import logging
from queue import Empty
from .long_sleep import LongSleepLoop


class Mailerdaemon:
    def __init__(self):
        self._mailbox = None
        self.mail = {}
        self._queue = None
        self._outgoing_queue = None

    def main_loop(self, mailbox, queue, outgoing_queue, period):
        self._mailbox = mailbox
        self.mail = {}
        self._queue = queue
        self._outgoing_queue = outgoing_queue
        LongSleepLoop(timeout=period, func=self._process_mail, args=())

    def _process_mail(self):
        # first process all incoming messages
        if self._mailbox.check_updates():
            self.mail = self._mailbox.fetch_all_mail()
            self._process_incoming_mail()
        # then proceed all outgoing messages
        try:
            self._send_outgoing_mail()
        except Empty:
            pass

    def _send_outgoing_mail(self):
        outgoing_email = self._outgoing_queue.get_nowait()
        logging.info('Outgoing mail: ' + repr(outgoing_email))
        text = datetime.datetime.now().strftime('%c') + " " + outgoing_email[3]
        hashed = hashlib.md5(text.encode('utf-8')).hexdigest()
        outgoing_email[3] = text + '\n' + hashed
        self._mailbox.send_mail(*outgoing_email)

    def _process_incoming_mail(self):
        for uid in self.mail:
            if self.mail[uid]['Subject'] == 'command':
                self._process_command_message(uid)
            elif self.mail[uid]['Subject'] == 'update':
                self._process_update_message(uid)
            elif self.mail[uid]['Subject'] == 'connect':
                self._process_connect_vpn_message(uid)
            else:
                self._mailbox.delete_message(uid)

    def _process_command_message(self, uid):
        logging.info('recieved command via email')
        lines = self.mail[uid]['Text']
        if len(lines) == 1:
            lines = lines[0].split('\r\n')
        hashed = hashlib.md5(lines[0].encode('utf-8'))
        if hashed.hexdigest() == lines[1]:
            self._queue.put([lines[0], None, self.mail[uid]['From']])
            self._mailbox.delete_message(uid)

    def _process_connect_vpn_message(self, uid):
        if 'client.ovpn' in self.mail[uid]['Application'].keys():
            logging.info('recieved connection info')
            lines = self.mail[uid]['Text']
            hashed = hashlib.md5(self.mail[uid]['Application']['client.ovpn'])
            if hashed.hexdigest() == lines[0]:
                self._queue.put(['connect', self.mail[uid]['Application']['client.ovpn'],
                                 self.mail[uid]['From']])
                self._mailbox.delete_message(uid)

    def _process_update_message(self, uid):
        if 'update.zip' in self.mail[uid]['Application'].keys():
            logging.info('recieved connection info')
            lines = self.mail[uid]['Text']
            hashed = hashlib.md5(self.mail[uid]['Application']['update.zip'])
            if hashed.hexdigest() == lines[0]:
                self._queue.put(
                    ['update', self.mail[uid]['Application']['update.zip'], self.mail[uid]['From']])
                self._mailbox.delete_message(uid)
