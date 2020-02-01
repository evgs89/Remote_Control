import configparser
import shutil
import subprocess
import os
import logging
from zipfile import PyZipFile

from multiprocessing import Process, Queue

from selenium.common.exceptions import WebDriverException

from queue import Empty


from time import sleep

from .modules import MailBox, ExternalIpGetter, WebInterface, Mailerdaemon
from .modules import ChangeDlinkModes_DGS_1100_05 as ChangeDlinkModes  # propbably further we will use other swithes


class RunServer:
    def __init__(self, loglevel = 'INFO'):
        self._init_logger(loglevel)
        self._get_config()
        if self._init_dlink(): logging.debug("Dlink Control activated")
        self._current_external_ip = self._get_external_ip()
        logging.info('Current external IP is: ' + str(self._current_external_ip))
        self._queue = Queue()
        self._outgoing_queue = Queue()
        self._start_web_interface()
        self._start_mail_daemon()
        self._active = True
        self._commands = {'SetDefaultState': self._set_default_mode,
                          'SetState1': self._enable_port3_to_wan,
                          'SetState2': self._enable_port4_to_wan,
                          'send_external_ip': self._send_external_ip,
                          'reboot_server': self._reboot_server,
                          'ClearLog': self._clear_log,
                          'connect': self._connect_openvpn,
                          'update': self._update_software
        }
        logging.info("Program Started")
        self._main_loop()

    def _init_logger(self, loglevel):
        loglevels = {'NOTSET': logging.NOTSET,
                     'DEBUG': logging.DEBUG,
                     'INFO': logging.INFO,
                     'WARNING': logging.WARNING,
                     'ERROR': logging.ERROR,
                     'CRITICAL': logging.CRITICAL}
        _maxlogsize = 10485760
        if os.path.getsize('log.txt') > _maxlogsize:
            try:
                os.remove("log.txt.0")
            except Exception:
                pass
            finally:
                os.rename('log.txt', 'log.txt.0')
        logging.basicConfig(filename = 'log.txt',
                            level = loglevels[loglevel],
                            format = "%(levelname)s [%(asctime)s]  %(message)s")
        logging.getLogger().addHandler(logging.StreamHandler())

    def _get_config(self):
        self._config = configparser.ConfigParser()
        self._config.read('settings.ini')

    def _init_dlink(self):
        try:
            logging.debug("Opening connection to switch")
            self._dlink_inited = self._init_dlink_process(self._config)
            logging.info("Switch on-line")
            return self._dlink_inited
        except WebDriverException:
            logging.warning('switch unavialable')
            self._dlink_inited = False
            return False

    def _init_dlink_process(self, config):
        if self._ping(config['SWITCH']['SwitchIp']):
            self._dLink = ChangeDlinkModes()
            self._dLink.setSwitchAdminLogin(config['SWITCH']['SwitchLogin'])
            self._dLink.setSwitchAdminPassword(config['SWITCH']['SwitchPassword'])
            self._dLink.setSwitchIp(config['SWITCH']['SwitchIp'])
            self._dLink.setHwLag(int(config['HARDWARE']['HardwareLag']))
            return self._dLink.setState(config['SWITCH']['DefaultState'])
        else: return False

    def _ping(self, host):
        cmd = 'ping -c 1 {host}'.format(host = host) # for testing on PC
        # cmd = 'sudo /bin/ping -c 1 {host}'.format(host = host) # for orangepi
        return subprocess.call(cmd, stdout = subprocess.DEVNULL, shell = True) == 0

    def _get_external_ip(self):
        self._externalIp = ExternalIpGetter(provider = self._config['NETWORK']['ExternalIpProvider'],
                                            expire_in_minutes = self._config['NETWORK']['ExternalIpExpire'])
        return self._externalIp.getExternalIp()

    def _save_config(self):
        shutil.copyfile('settings.ini', 'settings.ini.backup', follow_symlinks = True)
        with open('settings.ini', 'w') as configfile:
            self._config.write(configfile)

    def _setup_default_mode(self, state):
        self._config['SWITCH']['DefaultMode'] = state
        self._save_config()

    def _clear_log(self, null):
        with open("log.txt", "w") as file:
            logging.info("Log cleared")

    def _start_web_interface(self):
        logging.debug('starting web interface')
        devices_dict = self._config['DEVICES']
        self._webInterface = WebInterface(self._externalIp, self._queue, devices_dict)
        self._webInterfaceProcess = Process(target = self._webInterface.start, args = (self._queue, ), daemon = True)
        self._webInterfaceProcess.start()

    def _send_external_ip(self, null = None):
        self._outgoing_queue.put([self._config['EMAIL']['ImapLogin'],
                                  self._config['EMAIL']['DefaultAddressee'],
                                  'Current IP',
                                  'Current IP is {ip}'.format(ip = self._externalIp.getExternalIp())]
                                 )

    def _set_default_mode(self, null = None):
        if self._dlink_inited: self._dLink.setState(self._config['SWITCH']['DefaultState'])
        else: logging.error("Can't connect to switch")

    def _enable_port3_to_wan(self, null = None):
        if self._dlink_inited: self._dLink.setState('11112')
        else: logging.error("Can't connect to switch")

    def _enable_port4_to_wan(self, null = None):
        if self._dlink_inited: self._dLink.setState('11112')
        else: logging.error("Can't connect to switch")

    def _reboot_server(self, null = None):
        cmd = "sudo /sbin/reboot"
        subprocess.call(cmd, stdout = subprocess.DEVNULL, shell = True)

    def _update_software(self, data):
        logging.info("Starting software upgrade")
        with open('update.zip', 'wb') as update_file:
            update_file.write(data)
        zip = PyZipFile('update.zip')
        zip.extractall()
        logging.info("Update extracted")
        try:
            with open('version.txt', 'r') as version_file:
                version = version_file.readline()
                logging.info("Upgrade software to version {0}".format(version))
                self._config["VERSIONS"]["DeviceProgramVersion"] = version
            with open('settings.ini', 'w') as configfile:
                self._config.write(configfile)
        except Exception as e:
            logging.error("Upgrade failed: ERROR MESSAGE: {0}".format(repr(e)))

    def _connect_openvpn(self, data):
        with open('client.ovpn', 'wb') as ovpn_file:
            ovpn_file.write(data)
        cmd = "sudo systemctl stop openvpn"
        subprocess.call(cmd, stdout = subprocess.DEVNULL, shell = True)
        shutil.copyfile('client.ovpn', '/etc/openvpn/client.conf')
        self._ovpn_server_subprocess = Process(target = self._run_openvpn_server, args = (), daemon = True)
        self._ovpn_server_subprocess.start()

    def _run_openvpn_server(self):
        self._ovpn_active = True
        cmd = "sudo systemctl restart ntp"
        logging.info('Restarting NTP')
        subprocess.call(cmd, stdout = subprocess.DEVNULL, shell = True)
        cmd = "sudo openvpn --config /etc/openvpn/client.conf"
        logging.info('Trying to start openvpn server as client')
        subprocess.call(cmd, stdout = subprocess.DEVNULL, shell = True)
        counter = 100
        while self._ovpn_active:
            if counter > 0:
                if not self._ping('8.8.8.8'): counter -= 1
                else: counter = 100
            else:
                logging.error("Connection to internet lost")
                subprocess.call("sudo service openvpn stop", stdout = subprocess.DEVNULL, shell = True)
                self._current_external_ip = None
                self._ovpn_active = False
                self._outgoing_queue.put([self._config['EMAIL']['ImapLogin'],
                                          self._config['EMAIL']['DefaultAddressee'],
                                          'Connection LOST',
                                          'Connection to internet lost'.format(ip = self._externalIp.getExternalIp())]
                                         )

    def _start_mail_daemon(self):
        self._mailbox = MailBox(
                                host = self._config['EMAIL']['ImapHost'],
                                login = self._config['EMAIL']['ImapLogin'],
                                password = self._config['EMAIL']['ImapPassword'],
                                smtp_host = self._config['EMAIL']['SmtpHost'],
                                smtp_sender = self._config['EMAIL']['SmtpLogin'],
        )
        self._mailer_daemon = Mailerdaemon()
        self._mailer_daemon_subproccess = Process(target = self._mailer_daemon.main_loop,
                                                  args = (self._mailbox, self._queue,
                                                          self._outgoing_queue,
                                                          int(self._config['HARDWARE']['EmailUpdatePeriodSec']), ),
                                                  daemon = True)
        self._mailer_daemon_subproccess.start()

    def _main_loop(self):
        sleeping = False
        sleeping_timer = int(self._config['HARDWARE']['CheckCommandsTimeout'])
        self._send_external_ip()
        while self._active:
            if not sleeping:
                if not self._mailer_daemon_subproccess.is_alive():
                    print("Restarting mail daemon")
                    # logging.error("Restarting mail daemon")
                    self._start_mail_daemon()
                if not self._webInterfaceProcess.is_alive():
                    logging.warning('Restarting web interface')
                    self._start_web_interface()
                if not self._dlink_inited:
                    cmd = "pkill phantomjs*"
                    subprocess.call(cmd, stdout = subprocess.DEVNULL, shell = True)
                    sleep(5)
                    self._init_dlink()
                if not self._current_external_ip:
                    if self._externalIp.getExternalIp():
                        self._current_external_ip = self._externalIp.getExternalIp()
                        self._send_external_ip()
                try:
                    command = self._queue.get_nowait()
                    logging.info('Got command:' + repr(command))
                    if command[0] in self._commands.keys():
                        method = self._commands[command[0]]
                        method(command[1])
                        logging.info("Executed {command} from {sender}".format(command = command[0], sender = command[2]))
                        if command[2] != "Web":
                            self._outgoing_queue.put([self._config['EMAIL']['SmtpLogin'],
                                                     command[2],
                                                     'response to command',
                                                     "Command {cmd} executed".format(cmd = command[0])])
                    else:
                        logging.error("Command {cmd} not found".format(cmd = command[0]))
                        if command[2] != "Web":
                            self._outgoing_queue.put([self._config['EMAIL']['SmtpLogin'],
                                                      command[2],
                                                      'response to command',
                                                      "Command {cmd} not found".format(cmd = command[0])])
                except Empty:
                    sleeping = True
                    sleeping_timer = int(self._config['HARDWARE']['CheckCommandsTimeout'])
            else:
                sleeping_timer -= 1
                sleep(1)
                if sleeping_timer == 0: sleeping = False
