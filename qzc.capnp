@0xc7bbe66a583460d4;

# types of IDs:
#  - wkn: wellknown.  can be resolved to a nid, but may not always exist.
#                     also, the nid can change if an object is destroyed and
#                     recreated.
#
#  - nid: node id.    does not change over the lifetime of an object, but
#                     will change over restarts.  will also changed when some
#                     object is destroyed & recreated.
#
#  - elem: element.   a data item on a node.  for example, config & status
#                     might be 2 data elements.  children node lists are also
#                     separate elements (to make walking easier).
#
#                     note: elements can have 
#
#  - tid: type id.    constant type id of a node's type.
#
#  - datatype,        references to Cap'n'Proto struct IDs; specifies what
#    ctxtype:         kind of data is carried
#

# NodeInfo is mostly useless, but a very simple operation
#
struct QZCNodeInfoReq {
	nid		@0 :UInt64;
}

struct QZCNodeInfoRep {
	nid		@0 :UInt64;
	tid		@1 :UInt64;
}

# resolve a well-known ID to a node id.  first operation on client really.
#
struct QZCWKNResolveReq {
	wid		@0 :UInt64;
}

struct QZCWKNResolveRep {
	wid		@0 :UInt64;
	nid		@1 :UInt64;
}

# get data for a specific node element
#
struct QZCGetReq {
	nid		@0 :UInt64;
	elem		@1 :UInt64;
	ctxtype		@2 :UInt64;
	ctxdata		@3 :AnyPointer;
	itertype	@4 :UInt64;
	iterdata	@5 :AnyPointer;
}

struct QZCGetRep {
	nid		@0 :UInt64;
	elem		@1 :UInt64;
	datatype	@2 :UInt64;
	data		@3 :AnyPointer;
	itertype	@4 :UInt64;
	nextiter	@5 :AnyPointer;
}

# create child in context of a parent node/element
#
struct QZCCreateReq {
	parentnid	@0 :UInt64;
	parentelem	@1 :UInt64;
	datatype	@2 :UInt64;
	data		@3 :AnyPointer;
}

struct QZCCreateRep {
	newnid		@0 :UInt64;
}

struct QZCSetReq {
	nid		@0 :UInt64;
	elem		@1 :UInt64;
	ctxtype		@2 :UInt64;
	ctxdata		@3 :AnyPointer;
	datatype	@4 :UInt64;
	data		@5 :AnyPointer;
}

struct QZCDelReq {
	nid		@0 :UInt64;
}

struct QZCRequest {
	union {
		ping		@0 :Void;
		nodeinforeq	@1 :QZCNodeInfoReq;
		wknresolve	@2 :QZCWKNResolveReq;
		get		@3 :QZCGetReq;
		create		@4 :QZCCreateReq;
		set		@5 :QZCSetReq;
		del		@6 :QZCDelReq;
		unset		@7 :QZCSetReq;
	}
}

# TBD: better error handling *cough*
struct QZCReply {
	error @0 :Bool;
	union {
		pong		@1 :Void;
		nodeinforep	@2 :QZCNodeInfoRep;
		wknresolve	@3 :QZCWKNResolveRep;
		get		@4 :QZCGetRep;
		create		@5 :QZCCreateRep;
		set		@6 :Void;
		del		@7 :Void;
		unset		@8 :Void;
	}
}

# datatype / data of "nodelist" elements.
# TBD: windowed iterator?  hopefully not needed...
#
struct QZCNodeList @0x9bb91c45a95a581d {
	nodes			@0 :List(UInt64);
}

