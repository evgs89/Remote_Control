import email
from abc import ABC
from email.mime.text import MIMEText
import imaplib
import smtplib
import logging

from html.parser import HTMLParser


class HTMLParse(HTMLParser, ABC):
    def feed(self, data):
        self._output_data = []
        super(HTMLParse, self).feed(data)

    def handle_data(self, data):
        if data not in ['\r', '\n', '\r\n', '']:
            self._output_data.append(data)

    def get_data(self):
        return self._output_data


class MailBox:
    def __init__(self, host, login, password, smtp_host, smtp_sender,
                 smtp_ssl_port=None, type_of_mailbox='imap', port=None):
        # create mailbox object referring to type of server
        self._state = False
        self._connect_info = (host, login, password, type_of_mailbox, port)
        self._state = self._connect(*self._connect_info)
        self._login = login
        self._password = password
        self._smtp_host = smtp_host
        self._smtp_sender = smtp_sender
        if smtp_ssl_port:
            self._smtp_ssl_port = smtp_ssl_port
        else:
            self._smtp_ssl_port = 465
        self._type = type_of_mailbox
        self._cursor = 0
        self._search_criteria = "ALL"
        self._quantity_of_messages = 0
        self._unhtml = HTMLParse()

    def _connect(self, host, login, password, protocol, port):
        if protocol == 'imap':
            self._connect_imap(host, login, password, port)
        if self._state:
            logging.debug('Sucsessfully logged in mailbox')
            self._mailbox.list()
            self._mailbox.select('inbox')
            logging.info('In mailbox {num} letters'.format(num=self._check_messages_quantity()))
            self._quantity_of_messages = 0  # just for correct work of self.check_updates method
            return self._state

    def _connect_imap(self, host, login, password, port):
        try:
            port = self._connect_no_ssl(host, login, password, port)
        except imaplib.IMAP4.error as e:
            if "PRIVACYREQUIRED" in str(e.args[0]):
                print("Requred SSL")
                try:
                    self._connect_ssl(host, login, password, port)
                except imaplib.IMAP4.error as er:
                    e = er
            if "AUTHENTICATIONFAILED" in str(e.args[0]):
                logging.error("Auth Error")
        except Exception as e:
            pass  # logging.error("Other error:" + repr(e))

    def _connect_ssl(self, host, login, password, port):
        if not port or port == 143:
            port = 993
        self._mailbox = imaplib.IMAP4_SSL(host, port)
        self._mailbox.login(login, password)
        self._state = True
        return port

    def _connect_no_ssl(self, host, login, password, port):
        if not port:
            port = 143
        self._mailbox = imaplib.IMAP4(host, port)
        self._mailbox.login(login, password)
        self._state = True
        return port

    def fetch_one_mail(self):
        if self._state:
            self._cursor -= 1
            state, letters = self._mailbox.uid('search', None, self._search_criteria)
            try:
                uid = letters[0].split()[self._cursor]
            except IndexError:
                print("No more mail")
                return None
            return self._parse_message(uid)
        else:
            print('not connected')
            return None

    def set_search_criteria(self, sender=None, topic=None, new=False):
        if not sender and not topic and not new:
            search_criteria = 'ALL'
        else:
            criteria1 = 'FROM "{0}"'.format(sender) if sender else ''
            criteria2 = 'SUBJECT "{0}"'.format(topic) if topic else ''
            criteria3 = 'NEW' if new else ''
            search_criteria = '({0} {1} {2})'.format(criteria1, criteria2, criteria3)
            self._search_criteria = search_criteria
        return search_criteria

    def _parse_message(self, uid):
        result, raw_message = self._mailbox.uid('fetch', uid, '(RFC822)')
        text = ''
        if result:
            mail = email.message_from_bytes(raw_message[0][1])
            applications = {}
            maintype = mail.get_content_maintype()
            if maintype == 'multipart':
                text = self._get_multipart(applications, mail, text)
            elif maintype == 'text':
                text = mail.get_payload()
            mail_from = email.utils.parseaddr(mail['From'])[1]
            self._unhtml.feed(text)
            text = self._unhtml.get_data()
            return {"From": mail_from, "Subject": mail["Subject"], "Text": text, "Application": applications}
        else:
            logging.warning("Parsing Failed for uid: " + str(uid))
            return None

    def _get_multipart(self, applications, mail, text):
        for part in mail.get_payload():
            if part.get_content_maintype() == 'text':
                text = part.get_payload()
            elif part.get_content_maintype() == 'application':
                application, data = self._get_application(part)
                applications[application] = data
        return text

    def _get_application(self, part):
        application_name = str(
            email.header.make_header(email.header.decode_header(part.get_filename())))
        if not application_name:
            application_name = "application.raw"
        application_data = part.get_payload(decode=1)
        return application_name, application_data

    def fetch_all_mail(self):
        all_mail = {}  # {uid:email}
        state, letters = self._mailbox.uid('search', None, self._search_criteria)
        for uid in letters[0].split():
            message = self._parse_message(uid)
            print("Message: ", message)
            all_mail[uid] = self._parse_message(uid)
        return all_mail

    def _check_messages_quantity(self):
        if not self._state:
            self._connect(*self._connect_info)
        if self._state:
            try:
                state = self._mailbox.status('INBOX', '(MESSAGES)')[1][0].decode('utf-8')
                offset = state.index('MESSAGES') + 9
                self._quantity_of_messages = int(state[offset:-1])
                return self._quantity_of_messages
            except Exception as e:
                self._state = False
                logging.info('connection to mailbox lost')
                print(e)
                return 0
        else:
            # logging.warning('No connection')
            return 0

    def check_updates(self):
        quantity_of_messages = self._quantity_of_messages
        q = self._check_messages_quantity()
        if q > quantity_of_messages:
            self._cursor = 0
            return True
        else:
            return False

    def delete_message(self, uid):
        typ, response = self._mailbox.uid('store', uid, '+FLAGS', '\\Deleted')
        self._mailbox.expunge()
        if typ == 'OK':
            self._quantity_of_messages -= 1
            return True
        else:
            return False

    def send_mail(self, sender, send_to, subject, text):
        msg = MIMEText(text)
        msg['Subject'] = subject
        msg['From'] = sender
        msg['To'] = send_to
        try:
            server = smtplib.SMTP_SSL(self._smtp_host, self._smtp_ssl_port)
            server.login(self._login, self._password)
            server.sendmail(sender, send_to, msg.as_string())
            server.quit()
            return True
        except Exception as e:
            logging.warning(repr(e))
            return False

    def __exit__(self, exc_type, exc_value, traceback):
        self._mailbox.close()
        return True
