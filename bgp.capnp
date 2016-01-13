@0xc4c948a17d3b2250;

struct IPv4 @0xba7e0c8264b0f022 {
	val @0 :UInt32;
}
struct AfiSafiKey {
	afi			 @0 :UInt8;
	safi			 @1 :UInt8;
}
struct ExtCommunityList {
	values			 @0 :List(UInt64);
}
struct PrefixV4 {
	addr			 @0 :UInt32;
	prefixlen		 @1 :UInt8;
}

struct BGP {
	as			 @0 :UInt32;
	name			 @1 :Text;

	routerIdStatic		 @2 :IPv4;

	cfAlwaysCompareMed	 @3 :Bool;
	cfDeterministicMed	 @4 :Bool;
	cfMedMissingAsWorst	 @5 :Bool;
	cfMedConfed		 @6 :Bool;
	cfNoDefaultIPv4		 @7 :Bool;
	cfNoClientToClient	 @8 :Bool;
	cfEnforceFirstAS	 @9 :Bool;
	cfCompareRouterID	@10 :Bool;
	cfAspathIgnore		@11 :Bool;
	cfImportCheck		@12 :Bool;
	cfNoFastExtFailover	@13 :Bool;
	cfLogNeighborChanges	@14 :Bool;
	cfGracefulRestart	@15 :Bool;
	cfAspathConfed		@16 :Bool;
	cfAspathMpathRelax	@17 :Bool;

	distanceEBGP		@18 :UInt8;
	distanceIBGP		@19 :UInt8;
	distanceLocal		@20 :UInt8;

	defaultLocalPref	@21 :UInt32;
	defaultHoldtime		@22 :UInt32;
	defaultKeepalive	@23 :UInt32;

	restartTime		@24 :UInt32;  # XXX: can't be set in CLI?
	stalepathTime		@25 :UInt32;

	notifyZMQUrl		@26 :Text;
}

struct BGPAfiSafi {
	cfDampening		 @0 :Bool;
}

struct BGPPeer {
	as			 @0 :UInt32;
	host			 @1 :Text;

#	localAs			 @2 :UInt32;	# TBD

	desc			 @2 :Text;
	port			 @3 :UInt16;
	weight			 @4 :UInt32;
	holdtime		 @5 :UInt32;
	keepalive		 @6 :UInt32;

	cfPassive		 @7 :Bool;
	cfShutdown		 @8 :Bool;
	cfDontCapability	 @9 :Bool;
	cfOverrideCapability	@10 :Bool;
	cfStrictCapMatch	@11 :Bool;
	cfDynamicCapability	@12 :Bool;
	cfDisableConnectedCheck	@13 :Bool;
#	cfLocalAsNoPrepend	@14 :Bool;
#	cfLocalAsReplaceAs	@15 :Bool;

	ttl			@14 :Int32;
	updateSource		@15 :Text;
}

struct BGPPeerAfiSafi {
	afc			 @0 :Bool;

	cfSendCommunity		 @1 :Bool;
	cfSendExtCommunity	 @2 :Bool;
	cfNexthopSelf		 @3 :Bool;
	cfReflectorClient	 @4 :Bool;
	cfRServerClient		 @5 :Bool;
	cfSoftReconfig		 @6 :Bool;
	cfAsPathUnchanged	 @7 :Bool;
	cfNexthopUnchanged	 @8 :Bool;
	cfMedUnchanged		 @9 :Bool;
	cfDefaultOriginate	@10 :Bool;
	cfRemovePrivateAs	@11 :Bool;
	cfAllowAsIn		@12 :Bool;
	cfOrfPrefixSM		@13 :Bool;
	cfOrfPrefixRM		@14 :Bool;
	cfMaxPrefix		@15 :Bool;
	cfMaxPrefixWarn		@16 :Bool;
	cfNexthopLocalUnchanged	@17 :Bool;
	cfNexthopSelfAll	@18 :Bool;

	allowAsIn		@19 :Int8;
}

struct BGPVRF {
	outboundRd		 @0 :UInt64;
	rtImport		 @1 :ExtCommunityList;
	rtExport		 @2 :ExtCommunityList;
}

struct BGPEventVRFRoute {
	announce		 @0 :Bool;
	outboundRd		 @1 :UInt64;
	prefix			 @2 :PrefixV4;
	nexthop			 @3 :IPv4;
	label			 @4 :UInt32;
}

struct BGPEventShut {
	peer			 @0 :IPv4;
	type			 @1 :UInt8;
	subtype			 @2 :UInt8;
}

# vim: set noet ts=8 nowrap tw=0:
