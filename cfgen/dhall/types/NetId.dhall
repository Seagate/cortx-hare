{-
  Copyright (c) 2020 Seagate Technology LLC and/or its Affiliates

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.

  For any questions about this software or licensing,
  please email opensource@seagate.com or cortx-questions@seagate.com.

-}

{-
    Network identifier format (ABNF):

    nid      = "0@lo" / (ipv4addr  "@" ("tcp" / "o2ib") [DIGIT])
    ipv4addr = 1*3DIGIT "." 1*3DIGIT "." 1*3DIGIT "." 1*3DIGIT ; 0..255
-}

let Addr = ./Addr.dhall

{-
    Wrapping `Addr` with a record context lets `yaml-to-dhall`
    distinguish between TCP and Infiniband addresses, which would look
    similar in YAML if record was not used.

    No record:
    ```
    $ echo '< a : Text | b : Text >' >X.dhall
    $ echo 'let X = ./X.dhall in [ X.a "a", X.b "b" ]' >xs.dhall

    $ dhall-to-yaml <xs.dhall
    - a
    - b

    $ dhall-to-yaml <xs.dhall | yaml-to-dhall 'List ./X.dhall' | tee xs1.dhall
    [ < a : Text | b : Text >.a "a", < a : Text | b : Text >.a "b" ]

    $ dhall hash <xs.dhall
    sha256:14bc27126ceb5a0745725328f0a3e5276bf4f59c574973e0951ac0e4330c5d14
    $ dhall hash <xs1.dhall
    sha256:f3757941b7a58bfd504587b86ba4d2d559d969bd5896bb2dd4f271f55d20d17e
    ```

    With record:
    ```
    $ echo '< a : { a : Text } | b : { b : Text } >' >Y.dhall
    $ echo 'let Y = ./Y.dhall in [ Y.a { a = "a" }, Y.b { b = "b" } ]' >ys.dhall
    $ dhall-to-yaml <ys.dhall
    - a: a
    - b: b
    $ dhall-to-yaml <ys.dhall | yaml-to-dhall 'List ./Y.dhall' | tee ys1.dhall
    [ < a : { a : Text } | b : { b : Text } >.a { a = "a" }
    , < a : { a : Text } | b : { b : Text } >.b { b = "b" }
    ]
    $ dhall hash <ys.dhall
    sha256:0b61a771ae5a6b0a3f04f34c8df91cf9b508ed8f80fa8f773d3d22a9c7d1f4bd
    $ dhall hash <ys1.dhall
    sha256:0b61a771ae5a6b0a3f04f34c8df91cf9b508ed8f80fa8f773d3d22a9c7d1f4bd
    ```
-}

in
< lo
| tcp : { tcp : Addr }
| o2ib : { o2ib : Addr }
>
