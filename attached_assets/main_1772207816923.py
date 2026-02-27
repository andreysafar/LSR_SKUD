import json
import pathlib
import sys
import zeep
import typing

from event_filter import EventFilter
from http_server import HttpServer


class ConnectionConfig:

    def __init__(self, config_path: str):
        if pathlib.Path(config_path).is_file():
            with open(config_path, "rb") as fin:
                try:
                    data = json.loads(fin.read().decode("utf-8"))
                    self.host_addr = data["host_addr"]
                    self.organization = data["organization"]
                    self.username = data["username"]
                    self.password = data["password"]
                    self.integrational_service_url_path_template = data["integrational_service_url_path_template"]
                except KeyError as e:
                    raise SyntaxError(f"Incorrect connection config\n"
                                      "missing obligatory params:[host_addr, organization, username, password, integrational_service_url_path_template]\n"
                                      "{str(e)}")
        else:
            raise FileNotFoundError


class IntegrationalServiceSession:

    def __init__(self, config: ConnectionConfig):
        self.url = config.integrational_service_url_path_template.format(config.host_addr)
        self.client = zeep.Client(self.url)
        for func_name, func in self.client.service.__dict__["_operations"].items():
            self.__setattr__(func_name, func)
        if hasattr(self, "OpenSession"):
            self.session = self.OpenSession(config.organization, config.username, config.password)
            if self.session.Result == -1:
                raise ConnectionError(self.session.ErrorMessage)
            else:
                self.session = self.session.Value
                self.sessionId = self.session.SessionID
        else:
            raise KeyError(f"Method OpenSession wasn't found at {self.url}")

    def __del__(self):
        if hasattr(self, "CloseSession"):
            self.CloseSession(self.sessionId)
        else:
            raise KeyError(f"Method CloseSession wasn't found at {self.url}")

    def __resolve_namespace(self):
        for key, value in self.client.namespaces.items():
            if "Parsec3IntergationService" in value:
                self.parsec_namespace = key

    def type(self, type_name: str, namespace: str = None):
        if not hasattr(self, "parsec_namespace"):
            self.__resolve_namespace()
        try:
            if namespace:
                return self.client.get_type(f"{namespace}:{type_name}")
            else:
                return self.client.get_type(f"{self.parsec_namespace}:{type_name}")
        except Exception as e:
            return None


if __name__ == "__main__":
    connection_config = ConnectionConfig("connection_config.json")
    session = IntegrationalServiceSession(connection_config)
    EventFilter.initialize_type(session)
    server = HttpServer("127.0.0.1", 12345)
    server.start()
    filter = EventFilter()
    filter.fromJson("event_filter.json")
    subscription_ids = []
    subscriptionResult = session.EventsSubscribe(session.sessionId, filter.toWSDL(), 0, 1,
                                                 server.addr + "/test_post_events_matches_filter")
    subscription_ids.append(subscriptionResult.Value)
    subscriptionResult = session.EventsSubscribe(session.sessionId, filter.toWSDL(), 1, 1,
                                                 server.addr + "/test_resolved_post_events_matches_filter")
    subscription_ids.append(subscriptionResult.Value)
    req = server.addr + '/test_get_events_matches_filter?' \
                        'eventTypeDec=57CA38E4-ED6F-4D12-ADCB-2FAA16F950D7&' \
                        'subjectIdentifier=7C6D82A0-C8C8-495B-9728-357807193D23'
    subscriptionResult = session.EventsSubscribe(session.sessionId, filter.toWSDL(), 1, 0, req)
    subscription_ids.append(subscriptionResult.Value)
    while True:
        try:
            command = input().lower()
            if command == "q" or command == "quit" or command == "exit":
                break
        except KeyboardInterrupt:
            break
    if hasattr(session, "EventsUnsubscribeUrl"):
        session.EventsUnsubscribeUrl(session.sessionId, server.addr)
    else:
        for subscription_id in subscription_ids:
            session.EventsUnsubscribe(session.sessionId, subscription_id)
    server.stop()
