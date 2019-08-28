let localIP = "127.0.0.1"
let ip = "{{GetPrivateIP}}"

let Watch =
  < key :
      { type: Text, key: Text, args: List Text }
  | service_http :
      { type: Text, service: Text, handler_type: Text,
        http_handler_config :
          { path: Text, method: Text, timeout: Text } }
  | service_args :
      { type: Text, service: Text, args: List Text }
  >

let service =
  < checked :
      { id: Text, name: Text, address: Text, port: Natural,
        checks: List { args: List Text, interval: Text } }
  | unchecked :
      { id: Text, name: Text, address: Text, port: Natural }
  >

let dir = "/opt/seagate/consul"

in
{ server = True
, addresses =
  { grpc = ip
  , dns = "${localIP} ${ip}"
  , http = "${localIP} ${ip}"
  }
, watches = [
    Watch.key {
      type = "key",
      key = "leader",
      args = ["${dir}/elect-rc-leader"]
    },
    Watch.service_http {
      type = "service",
      service = "confd",
      handler_type = "http",
      http_handler_config = {
        path = "http://localhost:8080",
        method = "POST",
        timeout = "10s"
      }
    },
    Watch.service_args {
      type = "service",
      service = "confd",
      args = ["${dir}/Watch-service"]
    }
  ]
, services = [
    service.checked {
      id = "0x7200000000000001:0x1",
      name = "confd",
      address = "@tcp:12345:44",
      port = 1,
      checks = [
        {
          args = ["${dir}/check-confd"],
          interval = "10s"
        }
      ]
    },
    service.unchecked {
      id = "0x7200000000000001:0x3",
      name = "ios",
      address = "@tcp:12345:42",
      port = 401
    }
  ]
}

