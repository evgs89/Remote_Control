import configparser, shutil, os, sys
from multiprocessing import Process
from time import sleep
import subprocess
import argparse
try:
    from pyvirtualdisplay import Display
except ModuleNotFoundError:
    print('PYVIRTUALENV not found, headless run not allowed')

if sys.argv[0] != '__init__.py':
    os.chdir(os.path.dirname(sys.argv[0]))
parser = argparse.ArgumentParser(description = 'Additional parameters for script')
parser.add_argument('-w', '--watchdog_enabled', default = 1, help = 'Disable or enable watchdog')
parser.add_argument('--log_level', default = 'INFO', help = 'Set logging level')
args = parser.parse_args()

def _init_virtual_display():
    try:
        Display(visible = 0, size = (1024, 1024), color_depth = 8).start()
    except NameError:
        print('Running on main X-server')
    except OSError:
        print('It seems Xvfb not installed in your system')

try:
    config = configparser.ConfigParser()
    config.read('settings.ini')
    version = config['VERSIONS']['DeviceProgramVersion']
except Exception as e:
    print(e)
    shutil.copyfile('settings.ini.backup', 'settings.ini', follow_symlinks = True)
    config = configparser.ConfigParser()
    config.read('settings.ini')
    version = config['VERSIONS']['DeviceProgramVersion']

_init_virtual_display()
mainScript = __import__('{v}.__init__'.format(v = version))
mainProcess = Process(target = mainScript.RunServer, args = (), daemon = False)

def watchdog():
    while True:
        subprocess.call("echo 1 > /dev/watchdog", shell = True)
        sleep(4)

watchdog_process = Process(target = watchdog, args = (), daemon = False)
if args.watchdog_enabled==1: watchdog_process.start()

while True:
   if not mainProcess.is_alive():
       subprocess.call("pkill phantomjs*", shell = True)
       mainProcess = Process(target = mainScript.RunServer, args = (args.log_level, ), daemon = False)
       mainProcess.start()
   sleep(60)




