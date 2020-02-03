import datetime
import subprocess


class ExternalIpGetter:
    _update_time = datetime.datetime.now()
    _expire_time_minutes = 60
    _provider = "ifconfig.me"

    def __init__(self, provider="ifconfig.me", expire_in_minutes=60):
        self._provider = provider
        self.expire_time_minutes = expire_in_minutes
        self._external_ip = ''
        self._getExternalIp()

    @classmethod
    def _getExternalIp(cls):
        # we can get IP using special providers, which support CLI and curl:
        # ifconfig.co (wrong?), ifconfig.me, icanhazip.com
        p = subprocess.Popen("timeout 30 curl {prov}".format(prov=cls._provider),
                             shell=True,
                             stdout=subprocess.PIPE)
        lines = []
        for line in p.stdout:
            if line[-2:] == '\n':
                lines.append(str(line, 'utf-8')[:-2])
            else:
                lines.append(str(line, 'utf-8'))
        if len(lines) == 0:
            p = subprocess.Popen("timeout 30 curl {prov}".format(prov=cls._provider),
                                 shell=True,
                                 stdout=subprocess.PIPE)
            lines = []
            for line in p.stdout:
                lines.append(str(line, 'utf-8')[:-2])
        if len(lines) > 0:
            cls._update_time = datetime.datetime.now()
            cls._external_ip = lines[0]
            return lines[0]
        else:
            return None

    @classmethod
    def getExternalIp(cls):
        expire = datetime.datetime.now() - cls._update_time
        if expire.seconds > int(cls._expire_time_minutes) * 60 or not cls._external_ip:
            cls._external_ip = cls._getExternalIp()
        return cls._external_ip
