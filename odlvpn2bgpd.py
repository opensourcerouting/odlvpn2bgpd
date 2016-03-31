#!/usr/bin/env python

import os, sys, argparse, select, subprocess, traceback, struct, socket, signal
dirn = os.path.dirname(os.path.abspath(__file__))
sys.path.append(dirn)

import logging, traceback, inspect, time
import zmq, capnp
import thriftpy, thriftpy.rpc
from thriftpy.transport import TBufferedTransportFactory, TTransportException

import qzcclient
import qzc_capnp
import bgp_capnp

# default settings to be modified for package install
# dirn = full path to this script
#
default_bgp_cfg = os.path.join(dirn, 'bgpd.conf')
default_bgpd = '../quagga/bgpd/bgpd'
default_thrift = os.path.join(dirn, 'vpnservice.thrift')
#
# end default settings

ctx = zmq.Context()

vpnsvc_thrift = thriftpy.load(default_thrift, module_name="vpnsvc_thrift")
notify_url = 'ipc:///tmp/qzc-notify'

def ipv4_s2v(s):
    return struct.unpack('>I', socket.inet_aton(s))[0]
def ipv4_v2s(val):
    return socket.inet_ntoa(struct.pack('>I', val))

class BGPInstance(object):
    def __init__(self):
        pass

class BGPConfImpl(object):
    def __init__(self, quaggacfg, bgpdpath):
        self.asn = None
        self.proc = None
        self.quaggacfg = quaggacfg
        self.bgpdpath = bgpdpath
        self.rd_cache = {}
        self.iter_reset()

    def startBgp(self, asn, rid, port, t_holdtime, t_keepalive, t_stalepath, fbit):
        if self.asn is not None:
            return vpnsvc_thrift.BGP_ERR_ACTIVE

        self.iter_reset()
        self.asn = asn
        self.url = 'ipc:///tmp/qzc-%d' % (asn)
        self.proc = subprocess.Popen(
            [self.bgpdpath,
            '-f', self.quaggacfg, '-p', str(port), '-Z', self.url])

        try:
            self.zsock = qzcclient.QZCClient(self.url, ctx)

            # ping
            rep = self.zsock.do(qzc_capnp.QZCRequest.new_message(), timeout = 5000)
            if rep.which != 'pong' or rep.error:
                raise ValueError('bgpd init failed')

            bm = self.zsock.getwkn(qzcclient.bgp_bm_wkn)
            inst = bgp_capnp.BGP.new_message()
            setattr(inst, 'as', asn)
            inst.routerIdStatic.val = ipv4_s2v(rid)
            bgp = self.zsock.createchild(bm, 1, inst)

            conf = self.zsock.getelem(bgp, 1).as_builder()
            conf.routerIdStatic.val = ipv4_s2v(rid)
            conf.notifyZMQUrl = notify_url
            conf.defaultHoldtime = t_holdtime
            conf.defaultKeepalive = t_keepalive
            conf.stalepathTime = t_stalepath
            self.zsock.setelem(bgp, 1, conf)

            self.bgp_instance_nid = bgp
        except:
            traceback.print_exc()
            self.proc.terminate()
            self.proc = None
            self.asn = None
            return vpnsvc_thrift.BGP_ERR_FAILED

        return 0

    def stopBgp(self, asn):
        if self.asn is None or self.proc is None:
            return vpnsvc_thrift.BGP_ERR_INACTIVE
        if self.asn != asn:
            return vpnsvc_thrift.BGP_ERR_PARAM
        self.asn = None
        self.proc.terminate()
        self.proc.wait()
        self.proc = None
        self.iter_reset()
        return 0

    def enableGracefulRestart(self, stalepathTime):
        conf = self.zsock.getelem(self.bgp_instance_nid, 1).as_builder()
        conf.stalepathTime = stalepathTime
        conf.cfGracefulRestart = True
        self.zsock.setelem(self.bgp_instance_nid, 1, conf)
        return 0

    def disableGracefulRestart(self):
        conf = self.zsock.getelem(self.bgp_instance_nid, 1).as_builder()
        conf.stalepathTime = 0
        conf.cfGracefulRestart = False
        self.zsock.setelem(self.bgp_instance_nid, 1, conf)
        return 0

    def find_peer(self, ip):
        peers = self.zsock.getelem(self.bgp_instance_nid, 2)
        for peer in peers.nodes:
            data = self.zsock.getelem(peer, 2)
            if data.host == ip:
                return peer
        return None

    def createPeer(self, ip, asn):
        newconf = bgp_capnp.BGPPeer.new_message()
        setattr(newconf, 'as', asn)
        newconf.host = ip
        newnid = self.zsock.createchild(self.bgp_instance_nid, 2, newconf)
        if newnid == 0:
            return vpnsvc_thrift.BGP_ERR_FAILED

        self.aficfg(ip,
                vpnsvc_thrift.af_afi.AFI_IP,
                vpnsvc_thrift.af_safi.SAFI_MPLS_VPN,
                True)
        return 0

    def deletePeer(self, ip):
        peer = self.find_peer(ip)
        if peer is None:
            return vpnsvc_thrift.BGP_ERR_PARAM
        self.zsock.delnode(peer)
        return 0

    def enableAddressFamily(self, ip, afi, safi):
        return self.aficfg(ip, afi, safi, True)
    def disableAddressFamily(self, ip, afi, safi):
        return self.aficfg(ip, afi, safi, False)
    def aficfg(self, ip, afi, safi, value):
        peer = self.find_peer(ip)
        if peer is None:
            return vpnsvc_thrift.BGP_ERR_PARAM
        if afi not in [vpnsvc_thrift.af_afi.AFI_IP]:
            return vpnsvc_thrift.BGP_ERR_PARAM
        if safi not in [vpnsvc_thrift.af_safi.SAFI_MPLS_VPN]:
            return vpnsvc_thrift.BGP_ERR_PARAM

        ctx = bgp_capnp.AfiSafiKey.new_message()
        ctx.afi = 1
        ctx.safi = 4
        data = self.zsock.getelem(peer, 3, ctx)
        change = data.as_builder()
        change.afc = value
        self.zsock.setelem(peer, 3, change, ctx)
        return 0

    def setEbgpMultihop(self, ip, hops):
        return self.multihopcfg(ip, hops)
    def unsetEbgpMultihop(self, ip):
        return self.multihopcfg(ip, 0)
    def multihopcfg(self, ip, hops):
        peer = self.find_peer(ip)
        if peer is None:
            return vpnsvc_thrift.BGP_ERR_PARAM

        data = self.zsock.getelem(peer, 2)
        change = data.as_builder()
        change.ttl = hops
        self.zsock.setelem(peer, 2, change)
        return 0

    def find_vrf(self, rd):
        if rd in self.rd_cache:
            return self.rd_cache[rd]
        vrfs = self.zsock.getelem(self.bgp_instance_nid, 3)
        for vrf in vrfs.nodes:
            data = self.zsock.getelem(vrf, 1)
            if data.outboundRd == rd:
                self.rd_cache[rd] = vrf
                return vrf
        return None

    def addVrf(self, rd, irts, erts):
        rd = qzcclient.encode_rd(rd)
        newconf = bgp_capnp.BGPVRF.new_message()
        newconf.outboundRd = rd
        newconf.rtImport.values = [ qzcclient.encode_ec(ec) for ec in irts ]
        newconf.rtExport.values = [ qzcclient.encode_ec(ec) for ec in erts ]
        newnid = self.zsock.createchild(self.bgp_instance_nid, 3, newconf)
        if newnid == 0:
            return vpnsvc_thrift.BGP_ERR_FAILED
        self.zsock.setelem(newnid, 1, newconf)
        return 0

    def delVrf(self, rd):
        rd = qzcclient.encode_rd(rd)
        vrf = self.find_vrf(rd)
        if vrf is None:
            return vpnsvc_thrift.BGP_ERR_PARAM
        self.zsock.delnode(vrf)
        self.rd_cache = {}
        return 0

    def pushRoute(self, prefix, nexthop, rd, label):
        rd = qzcclient.encode_rd(rd)
        vrf = self.find_vrf(rd)
        if vrf is None:
            return vpnsvc_thrift.BGP_ERR_PARAM

        ctx = bgp_capnp.AfiKey.new_message()
        ctx.afi = 1

        rt = bgp_capnp.BGPVRFRoute.new_message()
        rt.nexthop.val = ipv4_s2v(nexthop)
        rt.prefix.prefixlen = int(prefix.split('/')[1])
        rt.prefix.addr = ipv4_s2v(prefix.split('/')[0])
        rt.label = label
        self.zsock.setelem(vrf, 3, rt, ctx)
        return 0

    def withdrawRoute(self, prefix, rd):
        rd = qzcclient.encode_rd(rd)
        vrf = self.find_vrf(rd)
        if vrf is None:
            return vpnsvc_thrift.BGP_ERR_PARAM

        ctx = bgp_capnp.AfiKey.new_message()
        ctx.afi = 1

        rt = bgp_capnp.BGPVRFRoute.new_message()
        rt.prefix.prefixlen = int(prefix.split('/')[1])
        rt.prefix.addr = ipv4_s2v(prefix.split('/')[0])
        self.zsock.unsetelem(vrf, 3, rt, ctx)
        return 0

    def iter_reset(self):
        self.iter_vrfs = None
        self.iter_pfx = None
    def iter_get(self):
        ctx = bgp_capnp.AfiKey.new_message()
        ctx.afi = 1
        data = None
        prev_vrf = None
        prev_rd = None
        while len(self.iter_vrfs) > 0 and data == None:
            vrf = self.iter_vrfs[0]
            if vrf != prev_vrf:
                vrfcfg = self.zsock.getelem(vrf, 1)
                prev_vrf = vrf
                prev_rd = vrfcfg.outboundRd
            data, self.iter_pfx = self.zsock._getelem(vrf, 2, ctx,
                    self.iter_pfx, wrap = False)
            if self.iter_pfx is None:
                self.iter_vrfs.pop(0)
        return (prev_rd, data)
    def getRoutes(self, optype, winsize):
        routes = vpnsvc_thrift.Routes()
        if optype == vpnsvc_thrift.GET_RTS_INIT:
            self.iter_reset()
            self.iter_vrfs = [long(i) for i in
                    self.zsock.getelem(self.bgp_instance_nid, 3).nodes]
        else:
            if self.iter_vrfs is None:
                routes.errcode = vpnsvc_thrift.ERR_NOT_ITER
                return routes
        routes.errcode = 0
        routes.more = 1
        routes.updates = []
        for i in range(0, max(winsize / 96, 1)):
            rd, route = self.iter_get()
            if route is None:
                routes.more = 0
                break
            upd = vpnsvc_thrift.Update()
            upd.type = vpnsvc_thrift.BGP_RT_ADD
            upd.prefixlen = route.prefix.prefixlen
            upd.prefix = ipv4_v2s(route.prefix.addr)
            upd.nexthop = ipv4_v2s(route.nexthop.val)
            upd.label = route.label
            upd.rd = qzcclient.decode_rd(rd)
            routes.updates.append(upd)
        return routes

    def __getattr__(self, name):
        def not_impl(*args, **kwargs):
            sys.stderr.write('calling %s(args = [%s], kwargs = {%s})\n' % (
                name,
                ', '.join([repr(i) for i in args]),
                ', '.join(['%s: %s' % (k, repr(v)) for k, v in kwargs.items()])
                ))
            return 0
        return not_impl

        # raise AttributeError('no such attribute: %s' % (name))

class NoTimeoutTransport(TBufferedTransportFactory):
    def get_transport(self, client):
        client.socket_timeout = None
        client.sock.settimeout(None)
        return super(NoTimeoutTransport, self).get_transport(client)

def run(addr, port, cfgfile, bgpd):
    server = thriftpy.rpc.make_server(
            vpnsvc_thrift.BgpConfigurator,
            BGPConfImpl(cfgfile, bgpd),
            addr, port,
            trans_factory = NoTimeoutTransport())
    server.serve()

class IntrospectionTransport(TBufferedTransportFactory):
    def __init__(self, *args, **kwargs):
        self.client = None
        super(IntrospectionTransport, self).__init__(*args, **kwargs)

    def get_transport(self, client):
        if self.client is not None:
            raise RuntimeError("IntrospectionTransport can only be used once")
        self.client = client
        return super(IntrospectionTransport, self).get_transport(client)

def run_reverse_int(addr, port):
    transport = IntrospectionTransport()
    try:
        client = thriftpy.rpc.make_client(vpnsvc_thrift.BgpUpdater, addr, port,
                                          trans_factory = transport)
    except TTransportException, e:
        if e.message.startswith('Could not connect'):
            return
        raise

    thsock = transport.client.sock

    client.onStartConfigResyncNotification()

    zssub = ctx.socket(zmq.SUB)
    zssub.connect(notify_url)
    zssub.setsockopt(zmq.SUBSCRIBE, '')

    poller = zmq.Poller()
    poller.register(zssub, zmq.POLLIN)
    poller.register(thsock, zmq.POLLIN)

    while True:
        events = dict(poller.poll())
        if events == {}:
            continue
        if thsock.fileno() in events and events[thsock.fileno()] == zmq.POLLIN:
            buf = thsock.recv(1024)
            if not buf:
                sys.stderr.write('client closed connection\n')
                zssub.close()
                return
        if zssub not in events or events[zssub] != zmq.POLLIN:
            continue

        raw = zssub.recv()
        upd = bgp_capnp.BGPEventVRFRoute.from_bytes(raw)

        rd = qzcclient.decode_rd(upd.outboundRd)
        prefix = socket.inet_ntoa(struct.pack('>I', upd.prefix.addr))
        prefixlen = upd.prefix.prefixlen
        nexthop = socket.inet_ntoa(struct.pack('>I', upd.nexthop.val))
        label = upd.label

        if upd.announce:
            client.onUpdatePushRoute(rd, prefix, prefixlen, nexthop, label)
        else:
            client.onUpdateWithdrawRoute(rd, prefix, prefixlen)

def run_reverse(addr, port):
    while True:
        try:
            run_reverse_int(addr, port)
        except:
            traceback.print_exc()
        time.sleep(1)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
            format='%(asctime)s %(levelname)s %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S')

    argp = argparse.ArgumentParser(description = "VPNService Thrift<>Cap'n'Proto proxy")
    argp.add_argument('--server-addr', type = str, default = '127.0.0.1')
    argp.add_argument('--server-port', type = int, default = 7644)
    argp.add_argument('--client-addr', type = str, default = '127.0.0.1')
    argp.add_argument('--client-port', type = int, default = 6644)
    argp.add_argument('--config', type = str, default = default_bgp_cfg)
    argp.add_argument('--bgpd', type = str, default = default_bgpd)
    args = argp.parse_args()

    if os.getuid() != 0:
        sys.stderr.write('WARNING: this script should run as root since it starts bgpd\n')

    pid = os.fork()
    if pid == 0:
        run_reverse(args.client_addr, args.client_port)
    else:
        try:
            run(args.server_addr, args.server_port, args.config, args.bgpd)
        finally:
            os.kill(pid, signal.SIGTERM)

