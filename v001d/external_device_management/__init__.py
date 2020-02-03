import logging

from selenium.common.exceptions import WebDriverException

from .external_device_setup import ChangeDlinkModes_DGS_1100_05
from .ping import ping

class ExternalDeviceManagement:
    def __init__(self, config):
        self._state = False
        self._config = config
        if self.start():
            logging.debug("Dlink Control activated")

    def start(self):
        return self._init_dlink()

    def _init_dlink(self):
        try:
            logging.debug("Opening connection to switch")
            self._state = self._init_dlink_process(self._config)
            logging.info("Switch on-line")
            return self._state
        except WebDriverException:
            logging.warning('switch unavialable')
            self._state = False
            return False

    def _init_dlink_process(self, config):
        if ping(config['SWITCH']['SwitchIp']):
            self._dLink = ChangeDlinkModes_DGS_1100_05()
            self._dLink.setSwitchAdminLogin(config['SWITCH']['SwitchLogin'])
            self._dLink.setSwitchAdminPassword(config['SWITCH']['SwitchPassword'])
            self._dLink.setSwitchIp(config['SWITCH']['SwitchIp'])
            self._dLink.setHwLag(int(config['HARDWARE']['HardwareLag']))
            return self._dLink.setState(config['SWITCH']['DefaultState'])
        else:
            return False

    def get_state(self):
        return self._state

    def set_default(self):
        self._set_default_mode()

    def set_working_mode_1(self):
        self._enable_port3_to_wan()

    def set_working_mode_2(self):
        self._enable_port4_to_wan()

    def _set_default_mode(self, null=None):
        if self._state:
            self._dLink.setState(self._config['SWITCH']['DefaultState'])
        else:
            logging.error("Can't connect to switch")

    def _enable_port3_to_wan(self, null=None):
        if self._state:
            self._dLink.setState('11112')
        else:
            logging.error("Can't connect to switch")

    def _enable_port4_to_wan(self, null=None):
        if self._state:
            self._dLink.setState('11112')
        else:
            logging.error("Can't connect to switch")