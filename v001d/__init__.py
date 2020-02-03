import configparser
import subprocess
import os
import logging
from queue import Empty
from multiprocessing import Process, Queue
from time import sleep

from .email import Mailerdaemon, MailBox, LongSleepLoop
from .webServer import WebInterface
from .external_device_management import ExternalDeviceManagement
from .commands import Commands
from .external_ip_getter import ExternalIpGetter


class RunServer:
    def __init__(self, loglevel='INFO'):
        self._init_logger(loglevel)
        self._get_config()
        self._device_manager = ExternalDeviceManagement(self._config)
        self._commands = Commands(config=self._config)
        self._current_external_ip = self._commands.get_external_ip()
        logging.info('Current external IP is: ' + str(self._current_external_ip))
        self._queue = Queue()
        self._outgoing_queue = Queue()
        self._start_web_interface()
        self._start_mail_daemon()
        self._active = True
        self._commands = {'SetDefaultState': self._device_manager.set_default,
                          'SetState1': self._device_manager.set_working_mode_1,
                          'SetState2': self._device_manager.set_working_mode_2,
                          'send_external_ip': self._commands.send_external_ip,
                          'reboot_server': self._commands.reboot_server,
                          'ClearLog': self._commands.clear_log,
                          'connect': self._commands.connect_openvpn,
                          'update': self._commands.update_software
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
        logging.basicConfig(filename='log.txt',
                            level=loglevels[loglevel],
                            format="%(levelname)s [%(asctime)s]  %(message)s")
        logging.getLogger().addHandler(logging.StreamHandler())

    def _get_config(self):
        self._config = configparser.ConfigParser()
        self._config.read('settings.ini')

    def _start_web_interface(self):
        logging.debug('starting web interface')
        devices_dict = self._config['DEVICES']
        self._webInterface = WebInterface(self._externalIp, self._queue, devices_dict)
        self._webInterfaceProcess = Process(target=self._webInterface.start, args=(self._queue,), daemon=True)
        self._webInterfaceProcess.start()

    def _start_mail_daemon(self):
        self._mailbox = MailBox(
            host=self._config['EMAIL']['ImapHost'],
            login=self._config['EMAIL']['ImapLogin'],
            password=self._config['EMAIL']['ImapPassword'],
            smtp_host=self._config['EMAIL']['SmtpHost'],
            smtp_sender=self._config['EMAIL']['SmtpLogin'],
        )
        self._mailer_daemon = Mailerdaemon()
        self._mailer_daemon_subprocess = Process(target=self._mailer_daemon.main_loop,
                                                 args=(self._mailbox, self._queue,
                                                        self._outgoing_queue,
                                                        int(self._config['HARDWARE']['EmailUpdatePeriodSec']),),
                                                 daemon=True)
        self._mailer_daemon_subprocess.start()

    def _main_loop(self):
        sleeping_timer = int(self._config['HARDWARE']['CheckCommandsTimeout'])
        self._send_external_ip()
        LongSleepLoop(timeout=sleeping_timer, func=self._check_services_and_incoming_commands, args=())

    def _check_services_and_incoming_commands(self):
        self._check_services_are_alive()
        try:
            command = self._queue.get_nowait()
            logging.info('Got command:' + repr(command))
            self._execute_command(command)
        except Empty:
            pass

    def _execute_command(self, command):
        if command[0] in self._commands.keys():
            method = self._commands[command[0]]
            method(command[1])
            logging.info("Executed {command} from {sender}".format(command=command[0], sender=command[2]))
            if command[2] != "Web":
                self._outgoing_queue.put([self._config['EMAIL']['SmtpLogin'],
                                          command[2],
                                          'response to command',
                                          "Command {cmd} executed".format(cmd=command[0])])
        else:
            logging.error("Command {cmd} not found".format(cmd=command[0]))
            if command[2] != "Web":
                self._outgoing_queue.put([self._config['EMAIL']['SmtpLogin'],
                                          command[2],
                                          'response to command',
                                          "Command {cmd} not found".format(cmd=command[0])])

    def _check_services_are_alive(self):
        if not self._mailer_daemon_subprocess.is_alive():
            print("Restarting mail daemon")
            # logging.error("Restarting mail daemon")
            self._start_mail_daemon()
        if not self._webInterfaceProcess.is_alive():
            logging.warning('Restarting web interface')
            self._start_web_interface()
        if not self._device_manager.get_state():
            cmd = "pkill phantomjs*"
            subprocess.call(cmd, stdout=subprocess.DEVNULL, shell=True)
            sleep(5)
            self._device_manager.start()
        if not self._current_external_ip:
            if self._externalIp.getExternalIp():
                self._current_external_ip = self._externalIp.getExternalIp()
                self._send_external_ip()


