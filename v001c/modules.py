import email
from email.mime.text import MIMEText
import imaplib
import smtplib
import logging

import selenium
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from time import sleep
import datetime
import hashlib
import os, subprocess
from bottle import route, run, static_file
from queue import Empty
from html.parser import HTMLParser


class HTMLParse(HTMLParser):
    def feed(self, data):
        self._output_data = []
        super(HTMLParse, self).feed(data)

    def handle_data(self, data):
        if data not in ['\r', '\n', '\r\n', '']:
            self._output_data.append(data)

    def getData(self):
        return self._output_data

class MailBox:

    def __init__(self, host, login, password, smtp_host, smtp_sender, smtp_ssl_port = None, type_of_mailbox = 'imap', port = None):
        # create mailbox object referring to type of server
        self._state = False
        self._connect_info = (host, login, password, type_of_mailbox, port)
        self._state = self._connect(*self._connect_info)
        self._login = login
        self._password = password
        self._smtp_host = smtp_host
        self._smtp_sender = smtp_sender
        if smtp_ssl_port: self._smtp_ssl_port = smtp_ssl_port
        else: self._smtp_ssl_port = 465
        self._type = type_of_mailbox
        self._cursor = 0
        self._search_criteria = "ALL"
        self._quantity_of_messages = 0
        self._unhtml = HTMLParse()

    def _connect(self, host, login, password, type, port):
        if type == 'imap':
            try:
                if not port: port = 143
                self._mailbox = imaplib.IMAP4(host, port)
                self._mailbox.login(login, password)
                self._state = True
            except imaplib.IMAP4.error as e:
                if "PRIVACYREQUIRED" in str(e.args[0]):
                    print("Requred SSL")
                    try:
                        if not port or port == 143: port = 993
                        self._mailbox = imaplib.IMAP4_SSL(host, port)
                        self._mailbox.login(login, password)
                        self._state = True
                    except imaplib.IMAP4.error as er:
                        e = er
                if "AUTHENTICATIONFAILED" in str(e.args[0]):
                    logging.error("Auth Error")
            except Exception as e:
                pass # logging.error("Other error:" + repr(e))
        if self._state:
            logging.debug('Sucsessfully logged in mailbox')
            mailboxes = self._mailbox.list()
            self._mailbox.select('inbox')
            logging.info('In mailbox {num} letters'.format(num = self._check_messages_quantity()))
            self._quantity_of_messages = 0 # just for correct work of self.check_updates method
            return self._state

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

    def set_search_criteria(self, sender = None, topic = None, new = False):
        if not sender and not topic and not new:
            search_criteria = 'ALL'
        else:
            criteria1, criteria2 = '', ''
            criteria3 = ''
            if sender: criteria1 = 'FROM "{0}"'.format(sender)
            if topic: criteria2 = 'SUBJECT "{0}"'.format(topic)
            if new: criteria3 = 'NEW'
            search_criteria = '({0} {1} {2})'.format(criteria1,  criteria2, criteria3)
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
                for part in mail.get_payload():
                    if part.get_content_maintype() == 'text':
                        text = part.get_payload()
                    elif part.get_content_maintype() == 'application':
                        application_name = str(email.header.make_header(email.header.decode_header(part.get_filename())))
                        if not application_name: application_name = "application.raw"
                        application_data = part.get_payload(decode = 1)
                        applications[application_name] = application_data
            elif maintype == 'text':
                text = mail.get_payload()
            mailFrom = email.utils.parseaddr(mail['From'])[1]
            self._unhtml.feed(text)
            text = self._unhtml.getData()
            return {"From": mailFrom, "Subject": mail["Subject"], "Text": text, "Application": applications}
        else:
            logging.warning("Parsing Failed for uid: " + str(uid))
            return None

    def fetch_all_mail(self):
        all_mail = {} # {uid:email}
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


class Mailerdaemon:
    def __init__(self):
        self._mailbox = None
        self.mail = {}
        self._active = True
        self._queue = None
        self._outgoing_queue = None

    def main_loop(self, mailbox, queue, outgoing_queue, period):
        self._mailbox = mailbox
        self.mail = {}
        self._active = True
        self._queue = queue
        self._outgoing_queue = outgoing_queue
        sleeping = False
        sleep_timer = period
        while self._active:
            if not sleeping:
                # first process all incoming messages
                if self._mailbox.check_updates():
                    self.mail = self._mailbox.fetch_all_mail()
                    for uid in self.mail:
                        if self.mail[uid]['Subject'] == 'command':
                            logging.info('recieved command via email')
                            lines = self.mail[uid]['Text']
                            if len(lines) == 1:
                                lines = lines[0].split('\r\n')
                            hashed = hashlib.md5(lines[0].encode('utf-8'))
                            if hashed.hexdigest() == lines[1]:
                                self._queue.put([lines[0], None, self.mail[uid]['From']])
                                self._mailbox.delete_message(uid)
                        elif self.mail[uid]['Subject'] == 'update':
                            if 'update.zip' in self.mail[uid]['Application'].keys():
                                logging.info('recieved connection info')
                                lines = self.mail[uid]['Text']
                                hashed = hashlib.md5(self.mail[uid]['Application']['update.zip'])
                                if hashed.hexdigest() == lines[0]:
                                    self._queue.put(['update', self.mail[uid]['Application']['update.zip'], self.mail[uid]['From']])
                                    self._mailbox.delete_message(uid)
                        elif self.mail[uid]['Subject'] == 'connect':
                            if 'client.ovpn' in self.mail[uid]['Application'].keys():
                                logging.info('recieved connection info')
                                lines = self.mail[uid]['Text']
                                hashed = hashlib.md5(self.mail[uid]['Application']['client.ovpn'])
                                if hashed.hexdigest() == lines[0]:
                                    self._queue.put(['connect', self.mail[uid]['Application']['client.ovpn'], self.mail[uid]['From']])
                                    self._mailbox.delete_message(uid)
                        else:
                            self._mailbox.delete_message(uid)
                # then proceed all outgoing messages
                try:
                    outgoing_email = self._outgoing_queue.get_nowait()
                    logging.info('Outgoing mail: ' + repr(outgoing_email))
                    text = datetime.datetime.now().strftime('%c') + " " + outgoing_email[3]
                    hashed = hashlib.md5(text.encode('utf-8')).hexdigest()
                    outgoing_email[3] = text + '\n' + hashed
                    self._mailbox.send_mail(*outgoing_email)
                except Empty:
                    sleeping = True
                    sleep_timer = period
            else:
                sleep_timer -= 1
                if sleep_timer == 0: sleeping = False
                sleep(1)


class ChangeDlinkModes_DGS_1100_05:

    def __init__(self):

        self._host_ip = '10.90.90.90'
        self._admin_password = 'admin'
        # webdriver.wait is better, of course, but I couldn't wait for frames without names or IDs
        self._hw_lag = 7  # experimentally setting depending of computer's speed of render web page
        self._currentState = '00000'

    def _create_driver(self):
        subprocess.call("pkill phantomjs*", shell = True) # if browser failed because lack of RAM, kill it's process
        try:
            driver = webdriver.PhantomJS()
            driver.set_window_size(1000, 900)
            driver.implicitly_wait(30)
            wait = WebDriverWait(driver, 30)
            return (driver, wait)
        except Exception as e:
            logging.error('Error creating driver: {err}'.format(err = repr(e)))

    def _login(self, url, password):
        driver, wait = self._create_driver()
        try:
            logging.debug('load start page')
            driver.get('http://' + url)
        except Exception as e:
            logging.debug('got exception: ', e)
            driver.quit()
            return None
        if driver.title == "Login {host}".format(host = url):
            logging.debug('Authorisation page, logging in')
            try:
                frame = wait.until(EC.presence_of_element_located((By.TAG_NAME, 'frame')))
                driver.switch_to.frame(frame)
            except Exception as e:
                logging.debug(str(e))
            try:
                elem = wait.until(EC.presence_of_element_located((By.XPATH, "//table[@id='tabLogCont']/tbody/tr[3]/td[2]/input")))
                elem.send_keys(password)
                elem = driver.find_element_by_xpath('//*[@id="tabLogCont"]/tbody/tr[5]/td/input[1]')
                elem.click()
            except TimeoutException:
                logging.error('auth page not loading properly, exit')
                driver.quit()
                return None
            assert "No results found." not in driver.page_source
            logging.debug('Successfully logged in')
            return (driver, wait)
        elif driver.title == "DGS-1100-05":
            logging.debug('Already logged in, continue...')
            return (driver, wait)
        else:
            return None

    def _get_current_state(self):
        driver_wait = self._login(self._host_ip, self._admin_password)
        if driver_wait:
            driver, wait = driver_wait
            logging.debug("Login to switch successful")
            try:
                sleep(self._hw_lag)
                driver.switch_to.default_content()
                driver.switch_to.frame(1)
                driver.switch_to.frame(0)
                elem = wait.until((EC.presence_of_element_located((By.XPATH, ".//table[4]/tbody/tr/td[2]/span/img"))))
                elem.click()
                driver.find_element_by_xpath(".//div[3]/table[2]/tbody/tr/td[2]/span/img").click()
                driver.find_element_by_link_text("Port-Based VLAN").click()
                sleep(self._hw_lag)
                driver.switch_to.default_content()
                driver.switch_to.frame(2)
                elem = wait.until(EC.presence_of_element_located((By.XPATH, ".//table[@id='tabPBVlan']/tbody/tr[2]/td[3]")))
                interfaces_included_cell = elem.text
                vlan1 = [int(i[-1:]) for i in interfaces_included_cell.split(',')]
                interfaces_included_cell = driver.find_element_by_xpath(".//table[@id='tabPBVlan']/tbody/tr[3]/td[3]").text
                vlan2 = [int(i[-1:]) for i in interfaces_included_cell.split(',')]
                state = ''
                for i in range(0, 5):
                    if i + 1 in vlan1:
                        state += '1'
                    elif i + 1 in vlan2:
                        state += '2'
                    else:
                        state += '0'
                if len(state) == 5:
                    self._currentState = state
                    logging.info("Current SWITCH state is {state}".format(state = state))
                    return {'state': state, 'driver': driver, 'wait': wait}
                else:
                    logging.error('GetStateError')  # O__o down't know, why, but i want it in such way
                    return None
            except TimeoutException:
                logging.warning('Timeout expired')
                driver.quit()
                return None
            except Exception as e:
                logging.error(e)
                try:
                    driver.quit()
                except Exception:
                    pass
                finally:
                    return None
        else: return None

    def getCurrentState(self):
        stateDict = self._get_current_state()
        if stateDict:
            stateDict['driver'].quit()
            return True
        else:
            logging.error('GetStateError')  # O__o down't know, why, but i want it in such way
        return False

    def _set_settings_for_vlan(self, driver, wait, num_of_vlan, ports_to_change):
        driver.switch_to.default_content()
        driver.switch_to.frame(2)
        elem = wait.until(EC.presence_of_element_located((By.XPATH, './/*[@id="tabBigTitle"]/table/tbody/tr/td/font')))
        if elem.text == "Port-Based VLAN":
            elem = wait.until(EC.presence_of_element_located((By.LINK_TEXT, str(num_of_vlan))))
            elem.click()
            sleep(self._hw_lag)
            for port in ports_to_change:
                elem = wait.until(
                    EC.presence_of_element_located((By.XPATH,
                                                    ".//table[@id='tabContent']/tbody/tr[2]/td/table/tbody/tr[2]/td[{numOfCell}]/input".format(numOfCell = port + 2))))
                elem.send_keys(Keys.SPACE)
            driver.find_element_by_xpath(".//input[@value='Apply']").click()
            driver.switch_to.default_content()
            driver.switch_to.frame(2)
            if driver.find_element_by_xpath('.//*[@id="tabBigTitle"]/table/tbody/tr/td/font').text == "Port-Based VLAN":
                return True
        return False

    def setSwitchIp(self, ip):
        self._host_ip = ip
        return True

    def setSwitchAdminPassword(self, password):
        self._admin_password = password
        return True

    def setSwitchAdminLogin(self, login):
        return True # for other switches this may be needed

    def setHwLag(self, lag):
        self._hw_lag = lag
        return True

    def getState(self):
        print("Current State = ", self._currentState)
        return self._currentState

    def setState(self, state):
        if len(state) == 5:
            stateDict = self._get_current_state()
            currentState = stateDict['state']
            logging.debug("Current state = " + currentState)
            if state != currentState:
                logging.info("Set State = " + state)
                ports_to_change = {1:[], 2:[]}
                for port in range(5):
                    if state[port] != currentState[port]:
                        if int(currentState[port]):
                            ports_to_change[int(currentState[port])].append(port)
                        if int(state[port]):
                            ports_to_change[int(state[port])].append(port)
                ok = True
                for vlan_num in [1,2]:
                    ok = ok and self._set_settings_for_vlan(stateDict['driver'], stateDict['wait'], vlan_num, ports_to_change[vlan_num])
                if ok:
                    stateDict['driver'].quit()
                    if self.getCurrentState(): return True
                else: return False
            else: return True
        else:
            logging.error('Unknown state recieved - ' + state)
            return False


class ExternalIpGetter:
    def __init__(self, provider = "ifconfig.me", expire_in_minutes = 60):
        self._provider = provider
        self._update_time = datetime.datetime.now()
        self.expire_time_minutes = expire_in_minutes
        self._external_ip = ''
        self._getExternalIp()

    def _getExternalIp(self):
        # we can get IP using special providers, which support CLI and curl:
        # ifconfig.co (wrong?), ifconfig.me, icanhazip.com
        p = subprocess.Popen("timeout 30 curl {prov}".format(prov = self._provider),
                             shell = True,
                             stdout = subprocess.PIPE)
        lines = []
        for line in p.stdout:
            if line[-2:] == '\n': lines.append(str(line, 'utf-8')[:-2])
            else: lines.append(str(line, 'utf-8'))
        if len(lines) == 0:
            p = subprocess.Popen("timeout 30 curl {prov}".format(prov = self._provider),
                                 shell = True,
                                 stdout = subprocess.PIPE)
            lines = []
            for line in p.stdout:
                lines.append(str(line, 'utf-8')[:-2])
        if len(lines) > 0:
            self._update_time = datetime.datetime.now()
            self._external_ip = lines[0]
            return lines[0]
        else: return None

    def getExternalIp(self):
        expire = datetime.datetime.now() - self._update_time
        if expire.seconds > int(self.expire_time_minutes) * 60 or not self._external_ip:
            self._external_ip = self._getExternalIp()
        return self._external_ip


class WebInterface:
    def __init__(self, externalIpGetter, queue, hosts):
        self._hosts = hosts
        self._externalIpGetter = externalIpGetter
        self._queue = queue
        self._busyPage = """
        <!DOCTYPE html>
        <html>
        <head>
        <title>OrangePi Controller</title>
        </head>
        <body>
            <img src={pic}>
            <hr>
            <header>Команда отправлена</header>
            <a href=/>Назад</a>
        </body>
        </html>
        """.format(pic = '/orangepi.jpeg')

    def start(self, queue):
        self._queue = queue
        self.boundBottle()
        try:
            run(host = '0.0.0.0', port = 80)
        except OSError:
            logging.debug("OSError")
            sleep(30)

    # @route('/')
    def index(self):
        return """
        <!DOCTYPE html>
        <html>
        <head>
        <title>OrangePi Controller</title>
        </head>
        <body>
        <img src={pic}>
        <hr>
        <header>Сервер активен. Внешний IP - {externalIp}</header>
        <table cellspacing=20>
            <tr>
                <td><a href = defaultMode> Установить рабочий режим </a></td>
                <td><a href = setMode1> Установить режим настройки </a></td>
            </tr>
        </table>
        <table cellspacing=20>
        <tr>
            <td><a href = ping>Проверить доступность устройств (Ping)</a></td>
        </tr>
        <tr>
            <td><a href = reboot>Перезагрузка сервера</a></td>
        </tr>
        <tr>
            <td><a href = viewlog>Просмотр лога</a></td>
        </tr>
        </table>
        </body>
        </html>
        """.format(pic = 'orangepi.jpeg', externalIp = self._externalIpGetter.getExternalIp())
        ### <td><a href = setMode2> Получить доступ к дисплею </a></td>

    # @route('/orangepi.jpeg')
    def send_image(self):
        return static_file('orangepi.jpeg', root = os.getcwd(), mimetype = 'image/jpeg')

    # @route('/defaultMode')
    def defaultMode(self):
        self._queue.put(['SetDefaultState', None, 'Web'])
        return self._busyPage

    # @route('/setMode1')
    def setMode1(self):
        self._queue.put(['SetState1', None, 'Web'])
        return self._busyPage

    # @route('/ping')
    def ping(self):
        result = ""
        for i in self._hosts:
            if self._ping(self._hosts[i]):
                result += "<tr><td>{host}</td><td>Доступен</td></tr>".format(host = self._hosts[i])
            else:
                result += "<tr><td>{host}</td><td>Недоступен</td></tr>".format(host = self._hosts[i])
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>OrangePi Controller</title>
        </head>
        <body>
            <img src={pic}>
            <hr>
            <table>
            {result}
            </table>
            <a href=/>Назад</a>
        </body>
        </html>
        """.format(pic = 'orangepi.jpeg', result = result)

    # @route('/reboot')
    def reboot(self):
        return """
        <!DOCTYPE html>
        <html>
        <head>
        <title>OrangePi Controller</title>
        </head>
        <body>
            <img src={pic}>
            <hr>
            <header>Перезагрузить???</header>
            <table cellspacing=20>
            <tr>
                <td><a href=/reboot/true>Да!</a></td>
                <td><a href=/>Нет, назад</a></td>
            </tr>
        </table>
        </body>
        </html>
        """.format(pic = 'orangepi.jpeg')

    # @route('/reboot/true')
    def systemReboot(self):
        cmd = "sudo /sbin/reboot"
        subprocess.call(cmd, stdout = subprocess.DEVNULL, shell = True)
        return "Перезагрузка"

    # @route('/viewlog')
    def viewLog(self):
        log = ''
        with open('log.txt', 'r') as logfile:
            for line in logfile:
                log += '<tr><td>' + line + '</td></tr>'
        return """
        <!DOCTYPE html>
        <html>
        <head>
        <title>OrangePi Controller</title>
        </head>
        <body>
            <img src={pic}>
            <hr>
            <header>Лог</header>
            <table cellspacing=20>
            <tr>
                <td><a href = /clearlog>Очистить лог</a></td>
                <td><a href = />Назад</a></td>
            </tr>
            </table>
            <table>
            {table}
            </table>
        </body>
        </html>
        """.format(pic = 'orangepi.jpeg', table = log)

    def clear_log(self):
        return """
        <!DOCTYPE html>
        <html>
        <head>
        <title>OrangePi Controller</title>
        </head>
        <body>
            <img src={pic}>
            <hr>
            <header>Очистить лог???</header>
            <table cellspacing=20>
            <tr>
                <td><a href=/clearlog/true>Да!</a></td>
                <td><a href=/>Нет, назад</a></td>
            </tr>
        </table>
        </body>
        </html>
        """.format(pic = 'orangepi.jpeg')

    def clear_log_accepted(self):
        self._queue.put(['ClearLog', None, 'Web'])
        return self._busyPage


    def _ping(self, host):
        cmd = 'ping -c 1 {host}'.format(host = host)
        return subprocess.call(cmd, stdout = subprocess.DEVNULL, shell = True) == 0

    def boundBottle(self):
        route('/')(self.index)
        route('/orangepi.jpeg')(self.send_image)
        route('/defaultMode')(self.defaultMode)
        route('/setMode1')(self.setMode1)
        route('/ping')(self.ping)
        route('/reboot')(self.reboot)
        route('/reboot/true')(self.systemReboot)
        route('/viewlog')(self.viewLog)
        route('/clearlog')(self.clear_log)
        route('/clearlog/true')(self.clear_log_accepted)
