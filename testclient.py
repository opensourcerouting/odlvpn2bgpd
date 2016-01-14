#!/usr/bin/env python

import os, sys, argparse, traceback, signal, time
import logging

import thriftpy, thriftpy.rpc
from thriftpy.transport import TBufferedTransportFactory, TTransportException

vpnsvc_thrift = thriftpy.load("vpnservice.thrift", module_name="vpnsvc_thrift")

class NonzeroReturn(Exception):
    pass

class NonzeroWrap(object):
    def __init__(self, obj, errs = {}):
        self._obj = obj
        self._errs = errs
    def __getattr__(self, name):
        attr = getattr(self._obj, name)
        if not callable(attr):
            return attr
        def zero_exc(*args, **kwargs):
            ret = attr(*args, **kwargs)
            if not (isinstance(ret, int) or isinstance(ret, long)):
                return ret
            if ret != 0:
                raise NonzeroReturn('function %s() returned %d (%s)' % (
                    name, ret, self._errs.get(ret, 'unknown')))
            return ret
        return zero_exc

class BGPUpdImpl(object):
    def __getattr__(self, name):
        def not_impl(*args):
            sys.stderr.write('received call %s(%s)\n' % (
                name,
                ', '.join([repr(i) for i in args]),
                ))
        return not_impl

class NoTimeoutTransport(TBufferedTransportFactory):
    def get_transport(self, client):
        client.socket_timeout = None
        client.sock.settimeout(None)
        return super(NoTimeoutTransport, self).get_transport(client)

def run(addr, port):
    errs = dict([(v, k) for (k, v) in vpnsvc_thrift.__dict__.items() if k.startswith('BGP_ERR_')])
    client = NonzeroWrap(thriftpy.rpc.make_client(vpnsvc_thrift.BgpConfigurator, addr, port), errs)

    try:
        print client.startBgp(64603, '192.168.0.1', 179, 30, 60, 60, False)
    except:
        traceback.print_exc()

    client.addVrf('64603:3333', ['64603:3000'], ['64603:3000'])
    client.addVrf('64603:2222', ['64603:2000'], ['64603:2000'])
    client.addVrf('64603:1111', ['64603:1000'], ['64603:1000'])
    client.enableGracefulRestart(120)
    time.sleep(1)
    client.disableGracefulRestart()
    time.sleep(1)
    client.delVrf('64603:3333')
    client.enableGracefulRestart(120)
    time.sleep(1)
    client.createPeer('192.168.1.150', 64602)
    client.enableAddressFamily('192.168.1.150',
            vpnsvc_thrift.af_afi.AFI_IP, vpnsvc_thrift.af_safi.SAFI_MPLS_VPN)
    client.setEbgpMultihop('192.168.1.150', 255)
    time.sleep(5)
    client.unsetEbgpMultihop('192.168.1.150', 255)
    time.sleep(1)
    for i in range(0, 3):
        client.createPeer('192.168.1.100', 64603)
        client.enableAddressFamily('192.168.1.100',
                vpnsvc_thrift.af_afi.AFI_IP, vpnsvc_thrift.af_safi.SAFI_MPLS_VPN)
        time.sleep(10)
        client.pushRoute('10.3.0.0/16', '192.168.1.150', '64603:1111', 200)
        time.sleep(1)
        client.pushRoute('10.4.1.0/24', '192.168.1.151', '64603:1111', 200)
        time.sleep(1)
        client.withdrawRoute('10.3.0.0/16', '64603:1111')
        time.sleep(1)
        client.disableAddressFamily('192.168.1.100',
                vpnsvc_thrift.af_afi.AFI_IP, vpnsvc_thrift.af_safi.SAFI_MPLS_VPN)
        client.deletePeer('192.168.1.100')
        time.sleep(1)

    client.stopBgp(64603)

def run_reverse():
    server = thriftpy.rpc.make_server(
            vpnsvc_thrift.BgpUpdater,
            BGPUpdImpl(),
            '0.0.0.0', 6644,
            trans_factory = NoTimeoutTransport())
    server.serve()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
            format='%(asctime)s %(levelname)s %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S')

    argp = argparse.ArgumentParser(description = "VPNService Thrift<>Cap'n'Proto test client")
    argp.add_argument('--thrift-connaddr', type = str, default = '127.0.0.1')
    argp.add_argument('--thrift-connport', type = int, default = 7644)
    args = argp.parse_args()

    pid = os.fork()
    if pid == 0:
        run_reverse()
    else:
        try:
            run(args.thrift_connaddr, args.thrift_connport)
        finally:
            os.kill(pid, signal.SIGTERM)

