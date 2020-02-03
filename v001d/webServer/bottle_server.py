import logging
import os
import subprocess
from time import sleep
from bottle import route, run, static_file


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
        """.format(pic='/orangepi.jpeg')

    def start(self, queue):
        self._queue = queue
        self.boundBottle()
        try:
            run(host='0.0.0.0', port=80)
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
        """.format(pic='orangepi.jpeg', externalIp=self._externalIpGetter.getExternalIp())
        ### <td><a href = setMode2> Получить доступ к дисплею </a></td>

    # @route('/orangepi.jpeg')
    def send_image(self):
        return static_file('orangepi.jpeg', root=os.getcwd(), mimetype='image/jpeg')

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
                result += "<tr><td>{host}</td><td>Доступен</td></tr>".format(host=self._hosts[i])
            else:
                result += "<tr><td>{host}</td><td>Недоступен</td></tr>".format(host=self._hosts[i])
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
        """.format(pic='orangepi.jpeg', result=result)

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
        """.format(pic='orangepi.jpeg')

    # @route('/reboot/true')
    def systemReboot(self):
        cmd = "sudo /sbin/reboot"
        subprocess.call(cmd, stdout=subprocess.DEVNULL, shell=True)
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
        """.format(pic='orangepi.jpeg', table=log)

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
        """.format(pic='orangepi.jpeg')

    def clear_log_accepted(self):
        self._queue.put(['ClearLog', None, 'Web'])
        return self._busyPage

    def _ping(self, host):
        cmd = 'ping -c 1 {host}'.format(host=host)
        return subprocess.call(cmd, stdout=subprocess.DEVNULL, shell=True) == 0

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
