import logging
import shutil
import subprocess
from multiprocessing.context import Process
from zipfile import PyZipFile

from .external_device_management import ping
from .external_ip_getter import ExternalIpGetter


class Commands:
    def __init__(self, config):
        self._config = config

    def send_external_ip(self, null=None):
        self._outgoing_queue.put([self._config['EMAIL']['ImapLogin'],
                                  self._config['EMAIL']['DefaultAddressee'],
                                  'Current IP',
                                  'Current IP is {ip}'.format(ip=self._externalIp.getExternalIp())]
                                 )

    def reboot_server(self, null=None):
        cmd = "sudo /sbin/reboot"
        subprocess.call(cmd, stdout=subprocess.DEVNULL, shell=True)

    def update_software(self, data):
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


    def connect_openvpn(self, data):
        with open('client.ovpn', 'wb') as ovpn_file:
            ovpn_file.write(data)
        cmd = "sudo systemctl stop openvpn"
        subprocess.call(cmd, stdout=subprocess.DEVNULL, shell=True)
        shutil.copyfile('client.ovpn', '/etc/openvpn/client.conf')
        self._ovpn_server_subprocess = Process(target=self._run_openvpn_server, args=(), daemon=True)
        self._ovpn_server_subprocess.start()


    def _run_openvpn_server(self):
        self._ovpn_active = True
        cmd = "sudo systemctl restart ntp"
        logging.info('Restarting NTP')
        subprocess.call(cmd, stdout=subprocess.DEVNULL, shell=True)
        cmd = "sudo openvpn --config /etc/openvpn/client.conf"
        logging.info('Trying to start openvpn server as client')
        subprocess.call(cmd, stdout=subprocess.DEVNULL, shell=True)
        counter = 100
        while self._ovpn_active:
            if counter > 0:
                if not ping('8.8.8.8'):
                    counter -= 1
                else:
                    counter = 100
            else:
                logging.error("Connection to internet lost")
                subprocess.call("sudo service openvpn stop", stdout=subprocess.DEVNULL, shell=True)
                self._current_external_ip = None
                self._ovpn_active = False
                self._outgoing_queue.put([self._config['EMAIL']['ImapLogin'],
                                          self._config['EMAIL']['DefaultAddressee'],
                                          'Connection LOST',
                                          'Connection to internet lost'.format(ip=self._externalIp.getExternalIp())]
                                         )

    def clear_log(self, null):
        with open("log.txt", "w") as file:
            logging.info("Log cleared")

    def get_external_ip(self):
        self._externalIp = ExternalIpGetter(provider=self._config['NETWORK']['ExternalIpProvider'],
                                            expire_in_minutes=self._config['NETWORK']['ExternalIpExpire'])
        return self._externalIp.getExternalIp()
