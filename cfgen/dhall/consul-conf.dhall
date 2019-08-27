let local_ip = "127.0.0.1"
let ip = "{{GetPrivateIP}}"

let watch =
  < key :
      { type: Text, key: Text, args: List Text }
  | service_http :
      { type: Text, service: Text, handler_type: Text,
        http_handler_config : { path: Text, method: Text, timeout: Text } }
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

in
{ server = True
, addresses =
  { grpc = ip
  , dns = "${local_ip} ${ip}"
  , http = "${local_ip} ${ip}"
  }
, watches = [
    watch.key {
      type = "key",
      key = "leader",
      args = ["/opt/seagate/consul/elect-rc-leader"]
    },
    watch.service_http {
      type = "service",
      service = "confd",
      handler_type = "http",
      http_handler_config = {
        path = "http://localhost:8080",
        method = "POST",
        timeout = "10s"
      }
    },
    watch.service_args {
      type = "service",
      service = "confd",
      args = ["/opt/seagate/consul/watch-service"]
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
          args = ["/opt/seagate/consul/check-confd"],
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

