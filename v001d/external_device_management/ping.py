import subprocess

def ping(host):
    cmd = 'ping -c 1 {host}'.format(host=host)  # for testing on PC
    # cmd = 'sudo /bin/ping -c 1 {host}'.format(host = host) # for orangepi
    return subprocess.call(cmd, stdout=subprocess.DEVNULL, shell=True) == 0