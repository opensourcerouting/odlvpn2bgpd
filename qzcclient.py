#!/usr/bin/env python

import os, sys, random, socket, struct, argparse
dirn = os.path.dirname(os.path.abspath(__file__))
sys.path.append(dirn)

import logging
import zmq, capnp

import qzc_capnp
import bgp_capnp

types = {}
def regtype(v):
    if hasattr(v, 'schema'):
        types[v.schema.node.id] = v

for k in dir(bgp_capnp):
    if k.startswith('_'): continue
    v = bgp_capnp.__dict__[k]
    regtype(v)
regtype(qzc_capnp.QZCNodeList)


class QZCClient(object):
    def __init__(self, url, ctx = None):
        if ctx is None:
            ctx = zmq.Context()
        self.ctx = ctx

        self.zsock = ctx.socket(zmq.REQ)
        self.zsock.connect(url)

    def do(self, req, timeout = 1000):
        logging.debug('send req %r', req)
        q = req.to_bytes()
        self.zsock.send(zmq.Message(q))
        ready = self.zsock.poll(timeout = timeout)
        if ready == 0:
            raise IOError('ZMQ request timed out')
        r = self.zsock.recv()
        rep = qzc_capnp.QZCReply.from_bytes(r)
        logging.debug('recv rep %r', rep)
        return rep

    def getwkn(self, wkn):
        req = qzc_capnp.QZCRequest.new_message()
        req.init('wknresolve')
        req.wknresolve.wid = wkn;
        rep = self.do(req)
        if rep.error:
            raise ValueError('error resolving WKN:%016x' % (wkn))
        logging.info('resolved WKN %016x to nid %016x', wkn, rep.wknresolve.nid)
        return rep.wknresolve.nid

    def getelem(self, nid, elem, ctx = None, wrap = True):
        req = qzc_capnp.QZCRequest.new_message()
        req.init('get')
        req.get.nid = nid;
        req.get.elem = elem;
        if ctx is not None:
            ptr = req.get.ctxdata.as_struct(ctx.schema)
            ptr.from_dict(ctx.to_dict())
            req.get.ctxtype = ctx.schema.node.id
        rep = self.do(req)
        if rep.error:
            raise ValueError('error getting element %d on nid:%016x' % (elem, nid))

        if rep.get.datatype in types:
            rtype = types[rep.get.datatype].schema.node.displayName
            ret = rep.get.data.as_struct(types[rep.get.datatype])
            if wrap:
                ret = StructWrapper(ret)
        else:
            rtype = '<unknown:%016x>' % (rep.get.datatype)
            ret = (rep.get.datatype, rep.get.data)

        logging.info('GET nid:%016x/%d => %s', nid, elem, rtype)
        return ret

    def setelem(self, nid, elem, msg, ctx = None):
        req = qzc_capnp.QZCRequest.new_message()
        req.init('set')
        req.set.nid = nid;
        req.set.elem = elem;
        if ctx is not None:
            ptr = req.set.ctxdata.as_struct(ctx.schema)
            ptr.from_dict(ctx.to_dict())
            req.set.ctxtype = ctx.schema.node.id

        ptr = req.set.data.as_struct(msg.schema)
        ptr.from_dict(msg.to_dict())
        req.set.datatype = msg.schema.node.id

        rep = self.do(req)
        if rep.error:
            raise ValueError('error setting element %d on nid:%016x' % (elem, nid))

        logging.info('SET nid:%016x/%d', nid, elem)

    def createchild(self, nid, elem, msg):
        req = qzc_capnp.QZCRequest.new_message()
        req.init('create')
        req.create.parentnid = nid
        req.create.parentelem = elem

        ptr = req.create.data.as_struct(msg.schema)
        ptr.from_dict(msg.to_dict())
        req.create.datatype = msg.schema.node.id

        rep = self.do(req)
        if rep.error:
            raise ValueError('error creating element %d on nid:%016x with msg %r' % (elem, nid, msg))

        logging.info('CREATE nid:%016x/%d => %016x', nid, elem, rep.create.newnid)
        return rep.create.newnid

    def delnode(self, nid):
        req = qzc_capnp.QZCRequest.new_message()
        req.init('del')
        getattr(req, 'del').nid = nid
        rep = self.do(req)
        if rep.error:
            raise ValueError('error deleting NID:%016x' % (nid))
        logging.info('deleted nid %016x', nid)


def decode_rd(val):
    rdtype = struct.unpack('>H6x', struct.pack('@Q', val))[0]
    if rdtype == 0:
        rdtype, asn, val = struct.unpack('>HHI', struct.pack('@Q', val))
        rd = '%d:%d' % (asn, val)
    elif rdtype == 1:
        rdtype, ip, val = struct.unpack('>HIH', struct.pack('@Q', val))
        rd = '%s:%d' % (socket.inet_ntoa(struct.pack('>I', ip)), val)
    elif rdtype == 2:
        rdtype, asn, val = struct.unpack('>HIH', struct.pack('@Q', val))
        rd = '%d:%d' % (asn, val)
    else:
        rd = '%d:%s' % (rdtype, '.'.join(['%02x' % i for i in
            struct.unpack('6B', struct.pack('@Q', val)[2:])]))
    return rd
def decode_ec(val):
    ectype = struct.unpack('>B7x', struct.pack('@Q', val))[0]
    subtypes = {2: 'rt', 3: 'ro', 5: 'ospf'}
    if ectype == 0:
        subtype, asn, val = struct.unpack('>xBHI', struct.pack('@Q', val))
        ec = '%s %d:%d' % (subtypes.get(subtype, str(subtype)), asn, val)
    elif ectype == 1:
        subtype, ip, val = struct.unpack('>xBIH', struct.pack('@Q', val))
        ec = '%s %s:%d' % (subtypes.get(subtype, str(subtype)), socket.inet_ntoa(struct.pack('>I', ip)), val)
    elif ectype == 2:
        subtype, asn, val = struct.unpack('>xBIH', struct.pack('@Q', val))
        ec = '%s %d:%d' % (subtypes.get(subtype, str(subtype)), asn, val)
    else:
        ec = '%d:%s' % (ectype, '.'.join(['%02x' % i for i in
            struct.unpack('7B', struct.pack('@Q', val)[1:])]))
    return ec
def encode_rd(val):
    adm, sub = val.strip().split(':')
    sub = int(sub)
    if '.' in adm:
        rv = struct.pack('>H', 1) + socket.inet_aton(adm) + struct.pack('>H', sub)
    else:
        adm = int(adm)
        if adm < 65536:
            rv = struct.pack('>HHI', 0, adm, sub)
        else:
            rv = struct.pack('>HIH', 2, adm, sub)
    return struct.unpack('@Q', rv)[0]
def encode_ec(val):
    val = val.strip()
    if val.startswith('rt'): val = val[2:].strip()
    subtype = 2

    adm, sub = val.split(':')
    sub = int(sub)
    if '.' in adm:
        rv = struct.pack('>BB', 1, subtype) + socket.inet_aton(adm) + struct.pack('>H', sub)
    else:
        adm = int(adm)
        if adm < 65536:
            rv = struct.pack('>BBHI', 0, subtype, adm, sub)
        else:
            rv = struct.pack('>BBIH', 2, subtype, adm, sub)
    return struct.unpack('@Q', rv)[0]


class StructWrapper(object):
    def __init__(self, capnp):
        self.capnp = capnp
    def __getattr__(self, name):
        value = getattr(self.capnp, name)
        field = self.capnp.schema.fields[name]

        if field.proto.slot.type.which() == 'struct':
            structtype = types[field.proto.slot.type.struct.typeId]
            if structtype == bgp_capnp.IPv4:
                return socket.inet_ntoa(struct.pack('>I', value.val))
            if structtype == bgp_capnp.PrefixV4:
                return '%s/%d' % (socket.inet_ntoa(struct.pack('>I', value.addr)), value.prefixlen)
        return value
    def __setattr__(self, name, value):
        if name == 'capnp':
            self.__dict__['capnp'] = value
        else:
            setattr(self.__dict__['capnp'], name, value)
    def as_builder(self):
        return self.capnp.as_builder()
    def getrepr(self, name):
        value = getattr(self, name)
        selftype = types.get(self.capnp.schema.node.id, None)
        if selftype == qzc_capnp.QZCNodeList:
            return '[ %s ]' % (', '.join(['0x%016x' % i for i in value]))
        field = self.capnp.schema.fields[name]
        if field.proto.slot.type.which() == 'struct':
            structtype = types[field.proto.slot.type.struct.typeId]
            if structtype == bgp_capnp.ExtCommunityList:
                return '[ %s ]' % (', '.join([decode_ec(i) for i in value.values]))
        if name.endswith('Rd'):
            return "'%s'" % decode_rd(value)
        if isinstance(value, long):
            return '%d' % value
        return repr(value)
    def __repr__(self):
        # import pdb; pdb.set_trace()
        fields = ','.join([
            '\n    %s: %s' % (name, self.getrepr(name)) for name in self.capnp.schema.fieldnames
            ])
        return 'struct %s {%s\n}' % (self.capnp.schema.node.displayName, fields)
        # return repr(self.capnp)

bgp_def_wkn = 0xee130f407472b15a
bgp_bm_wkn = 0x37b64fdb20888a50

default_url = 'ipc:///tmp/qzc'

def run():
    conn = QZCClient(url)

    bgp_def_id = conn.getwkn(bgp_def_wkn)

    if False:
        req = qzc_capnp.QZCRequest.new_message()
        req.init('nodeinforeq')
        req.nodeinforeq.nid = rep.wknresolve.nid;
        do(req)

    data = conn.getelem(bgp_def_id, 1, wrap = True)
    print repr(data)

    nl = conn.getelem(bgp_def_id, 2, wrap = True)
    print repr(nl)

    for i in nl.nodes:
        data = conn.getelem(i, 2)
        print repr(data)

        ctx = bgp_capnp.AfiSafiKey.new_message()
        ctx.afi = 1
        ctx.safi = 1
        data = conn.getelem(i, 3, ctx)
        print repr(data)

    data = bgp_capnp.BGPPeer.new_message()
    data.host = "127.0.0.2"
    setattr(data, 'as', 12312)
    # conn.createchild(bgp_def_id, 2, data)

    i = nl.nodes[-1]
    data = conn.getelem(i, 2)
    print repr(data)
    change = data.as_builder()
    change.keepalive = 30
    change.holdtime = 120
    change.weight = random.randrange(10, 1000, 10)
    change.desc = "hello world %d" % (random.randrange(1,100))
    print repr(change)
    conn.setelem(i, 2, change)

def run_pretty():
    conn = QZCClient(url)

    bgp_def_id = conn.getwkn(bgp_def_wkn)
    data = conn.getelem(bgp_def_id, 1)
    print 'BGP default instance'
    print '\tASN:         %d' % getattr(data, 'as')
    print '\tRouter ID:   %s' % data.routerIdStatic
    print ''
    
    vrfs = conn.getelem(bgp_def_id, 3)
    print '%d VPN instances configured:' % len(vrfs.nodes)
    for vrf in vrfs.nodes:
        data = conn.getelem(vrf, 1)
        print '    RD (out)        %s' % data.getrepr('outboundRd')
        print '\timports:   %s' % data.getrepr('rtImport')
        print '\texports:   %s' % data.getrepr('rtExport')
    print ''

    peers = conn.getelem(bgp_def_id, 2)
    print '%d peers configured:' % len(peers.nodes)
    for peer in peers.nodes:
        data = conn.getelem(peer, 2)
        print '    %s' % data.host
        print '\tRemote ASN:  %d' % getattr(data, 'as')
        print '\tShutdown:    %r' % data.cfShutdown
        active = []
        for afi, afiname in enumerate(['IPv4', 'IPv6'], 1):
            for safi, safiname in enumerate(['Unicast', 'Multicast', 'rsvd-3', 'VPN'], 1):
                ctx = bgp_capnp.AfiSafiKey.new_message()
                ctx.afi = afi
                ctx.safi = safi
                afidata = conn.getelem(peer, 3, ctx)
                if afidata.afc:
                    active.append('%s %s' % (afiname, safiname))
        print '\tActive AFs:  %s' % ', '.join(active)

    print ''

if __name__ == '__main__':
    argp = argparse.ArgumentParser(description = "QZC test client")
    argp.add_argument('--dump', action = 'store_const', const = True, default = False)
    argp.add_argument('--pretty', action = 'store_const', const = True, default = False)
    argp.add_argument('--url', type = str, default = default_url)
    args = argp.parse_args()

    url = args.url
    if args.dump:
        logging.basicConfig(level=logging.INFO,
            format='%(asctime)s %(levelname)s %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S')
        run()
    if args.pretty:
        logging.basicConfig(level=logging.WARN,
            format='%(asctime)s %(levelname)s %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S')
        run_pretty()

