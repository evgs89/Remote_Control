import subprocess
import logging
from time import sleep

from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


class ChangeDlinkModes_DGS_1100_05:

    def __init__(self):

        self._host_ip = '10.90.90.90'
        self._admin_password = 'admin'
        # webdriver.wait is better, of course, but I couldn't wait for frames without names or IDs
        self._hw_lag = 7  # experimentally setting depending of computer's speed of render web page
        self._currentState = '00000'

    def _create_driver(self):
        subprocess.call("pkill phantomjs*", shell=True)  # if browser failed because lack of RAM, kill it's process
        try:
            driver = webdriver.PhantomJS()
            driver.set_window_size(1000, 900)
            driver.implicitly_wait(30)
            wait = WebDriverWait(driver, 30)
            return (driver, wait)
        except Exception as e:
            logging.error('Error creating driver: {err}'.format(err=repr(e)))

    def _login(self, url, password):
        driver, wait = self._create_driver()
        try:
            logging.debug('load start page')
            driver.get('http://' + url)
        except Exception as e:
            logging.debug('got exception: ', e)
            driver.quit()
            return None
        if driver.title == "Login {host}".format(host=url):
            logging.debug('Authorisation page, logging in')
            try:
                frame = wait.until(EC.presence_of_element_located((By.TAG_NAME, 'frame')))
                driver.switch_to.frame(frame)
            except Exception as e:
                logging.debug(str(e))
            try:
                elem = wait.until(
                    EC.presence_of_element_located((By.XPATH, "//table[@id='tabLogCont']/tbody/tr[3]/td[2]/input")))
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
                elem = wait.until(
                    EC.presence_of_element_located((By.XPATH, ".//table[@id='tabPBVlan']/tbody/tr[2]/td[3]")))
                interfaces_included_cell = elem.text
                vlan1 = [int(i[-1:]) for i in interfaces_included_cell.split(',')]
                interfaces_included_cell = driver.find_element_by_xpath(
                    ".//table[@id='tabPBVlan']/tbody/tr[3]/td[3]").text
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
                    logging.info("Current SWITCH state is {state}".format(state=state))
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
        else:
            return None

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
                                                    ".//table[@id='tabContent']/tbody/tr[2]/td/table/tbody/tr[2]/td[{numOfCell}]/input".format(
                                                        numOfCell=port + 2))))
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
        return True  # for other switches this may be needed

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
                ports_to_change = {1: [], 2: []}
                for port in range(5):
                    if state[port] != currentState[port]:
                        if int(currentState[port]):
                            ports_to_change[int(currentState[port])].append(port)
                        if int(state[port]):
                            ports_to_change[int(state[port])].append(port)
                ok = True
                for vlan_num in [1, 2]:
                    ok = ok and self._set_settings_for_vlan(stateDict['driver'], stateDict['wait'], vlan_num,
                                                            ports_to_change[vlan_num])
                if ok:
                    stateDict['driver'].quit()
                    if self.getCurrentState(): return True
                else:
                    return False
            else:
                return True
        else:
            logging.error('Unknown state recieved - ' + state)
            return False