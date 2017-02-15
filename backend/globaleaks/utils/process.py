import ctypes
import json
import os
import signal

from twisted.internet import reactor

from globaleaks.utils.utility import WorkerLogger

def SigQUIT(SIG, FRM):
    log('Received signal %s . . . quitting' % (SIG))
    try:
        reactor.stop()
    except Exception:
        pass


def log(msg):
    pass


def set_proctitle(title):
    libc = ctypes.cdll.LoadLibrary('libc.so.6')
    buff = ctypes.create_string_buffer(len(title) + 1)
    buff.value = title
    libc.prctl(15, ctypes.byref(buff), 0, 0, 0)


def set_pdeathsig(sig):
    PR_SET_PDEATHSIG = 1
    libc = ctypes.cdll.LoadLibrary('libc.so.6')
    libc.prctl.argtypes = (ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
                           ctypes.c_ulong, ctypes.c_ulong)
    libc.prctl(PR_SET_PDEATHSIG, sig, 0, 0, 0)


class Process(object):
    def __init__(self, fd=42):
        signal.signal(signal.SIGTERM, SigQUIT)
        signal.signal(signal.SIGINT, SigQUIT)
        set_pdeathsig(signal.SIGINT)

        f = os.fdopen(fd, 'r')

        try:
            s = f.read()
        except:
            raise
        finally:
            f.close()

        self.cfg = json.loads(s)

        if self.cfg['debug']:
            self.log = WorkerLogger()

    def log(self, msg):
        pass

    def start(self):
        reactor.run()

    def stop(self):
        reactor.stop()
