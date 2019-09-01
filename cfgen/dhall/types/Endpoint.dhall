{-
   LNet endpoint address.

   Endpoint address format (ABNF):

   endpoint = nid ":12345:" DIGIT+ ":" DIGIT+
   ; <network id>:<process id>:<portal number>:<transfer machine id>
   ;
   nid      = "0@lo" / (ipv4addr  "@" ("tcp" / "o2ib") [DIGIT])
   ipv4addr = 1*3DIGIT "." 1*3DIGIT "." 1*3DIGIT "." 1*3DIGIT ; 0..255
-}
{ nid : ./NetId.dhall
, portal : Natural
, tmid : Natural
}
