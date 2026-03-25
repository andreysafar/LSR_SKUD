import socket
import logging
import secrets
import threading
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class ParsecAPI:
    def __init__(self, host: str, port: int = 10101,
                 organization: str = "SYSTEM",
                 bot_username: str = "", bot_password: str = "",
                 admin_username: str = "", admin_password: str = ""):
        self.host = host
        self.port = port
        self.organization = organization
        self.bot_username = bot_username
        self.bot_password = bot_password
        self.admin_username = admin_username
        self.admin_password = admin_password
        self.wsdl_url = f"http://{host}:{port}/IntegrationService/IntegrationService.asmx?WSDL"
        self._client = None
        self._client_lock = threading.Lock()
        self._parsec_namespace = None
        self._bot_session = None
        self._admin_session = None
        logger.info(f"ParsecAPI initialized with WSDL: {self.wsdl_url}")

    @property
    def domain(self):
        return self.host

    def _ensure_client(self):
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    self._create_client()
        return self._client

    def _create_client(self):
        try:
            import zeep
            from zeep.transports import Transport
            import requests

            http_session = requests.Session()
            http_session.trust_env = False
            transport = Transport(session=http_session, timeout=10)
            self._client = zeep.Client(wsdl=self.wsdl_url, transport=transport)
            self._resolve_namespace()
            logger.info("SOAP client created successfully")
        except Exception as e:
            logger.error(f"Failed to create SOAP client: {e}")
            self._client = None

    def _resolve_namespace(self):
        if self._client is None:
            return
        for key, value in self._client.namespaces.items():
            if "Parsec3IntergationService" in value:
                self._parsec_namespace = key
                break

    def _get_type(self, type_name: str):
        client = self._ensure_client()
        if not client or not self._parsec_namespace:
            return None
        try:
            return client.get_type(f"{self._parsec_namespace}:{type_name}")
        except Exception as e:
            logger.error(f"Failed to get type {type_name}: {e}")
            return None

    def open_session(self, organization: str, username: str, password: str) -> Optional[Dict]:
        try:
            client = self._ensure_client()
            if not client:
                return None
            result = client.service.OpenSession(organization, username, password)
            if result.Result == -1:
                logger.error(f"OpenSession failed: {result.ErrorMessage}")
                return None
            session_data = {
                "session_id": str(result.Value.SessionID),
                "root_org_unit_id": str(result.Value.RootOrgUnitID),
                "root_territory_id": str(result.Value.RootTerritoryID),
            }
            logger.info(f"Session opened for {username}")
            return session_data
        except Exception as e:
            logger.error(f"Failed to open session for {username}: {e}")
            return None

    def close_session(self, session_id: str):
        try:
            client = self._ensure_client()
            if client and session_id:
                client.service.CloseSession(session_id)
                logger.debug(f"Session {session_id} closed")
        except Exception as e:
            logger.error(f"Failed to close session: {e}")

    def continue_session(self, session_id: str) -> bool:
        try:
            client = self._ensure_client()
            if not client:
                return False
            result = client.service.ContinueSession(session_id)
            return result == 0
        except Exception as e:
            logger.error(f"Failed to continue session: {e}")
            return False

    def open_bot_session(self) -> Optional[Dict]:
        self._bot_session = self.open_session(
            self.organization, self.bot_username, self.bot_password
        )
        return self._bot_session

    def open_admin_session(self) -> Optional[Dict]:
        self._admin_session = self.open_session(
            self.organization, self.admin_username, self.admin_password
        )
        return self._admin_session

    def get_bot_session_id(self) -> Optional[str]:
        if self._bot_session:
            sid = self._bot_session["session_id"]
            if self.continue_session(sid):
                return sid
            # Session expired, re-open
            self._bot_session = None
        sess = self.open_bot_session()
        return sess["session_id"] if sess else None

    def get_admin_session_id(self) -> Optional[str]:
        if self._admin_session:
            sid = self._admin_session["session_id"]
            if self.continue_session(sid):
                return sid
            # Session expired, re-open
            self._admin_session = None
        sess = self.open_admin_session()
        return sess["session_id"] if sess else None

    def find_people(self, session_id: str, lastname: str = "",
                    firstname: str = "", middlename: str = "") -> List[Dict]:
        try:
            client = self._ensure_client()
            if not client:
                return []
            persons = client.service.FindPeople(
                session_id, lastname or "", firstname or "", middlename or ""
            )
            if not persons:
                return []
            result = []
            for p in persons:
                result.append({
                    "id": str(p.ID),
                    "last_name": getattr(p, "LAST_NAME", ""),
                    "first_name": getattr(p, "FIRST_NAME", ""),
                    "middle_name": getattr(p, "MIDDLE_NAME", ""),
                    "tab_num": getattr(p, "TAB_NUM", ""),
                    "org_id": str(getattr(p, "ORG_ID", "")),
                })
            return result
        except Exception as e:
            logger.error(f"FindPeople error: {e}")
            return []

    def find_vehicle(self, session_id: str, number: str = "",
                     model: str = "", color: str = "") -> List[Dict]:
        try:
            client = self._ensure_client()
            if not client:
                return []
            vehicles = client.service.FindVehicle(
                session_id, number or "", model or "", color or ""
            )
            if not vehicles:
                return []
            result = []
            for v in vehicles:
                result.append({
                    "id": str(v.ID),
                    "last_name": getattr(v, "LAST_NAME", ""),
                    "first_name": getattr(v, "FIRST_NAME", ""),
                    "middle_name": getattr(v, "MIDDLE_NAME", ""),
                    "tab_num": getattr(v, "TAB_NUM", ""),
                })
            return result
        except Exception as e:
            logger.error(f"FindVehicle error: {e}")
            return []

    def person_search(self, session_id: str, field_id: str, relation: int,
                      value: Any, value1: Any = None) -> List[Dict]:
        try:
            client = self._ensure_client()
            if not client:
                return []
            persons = client.service.PersonSearch(
                session_id, field_id, relation, value, value1
            )
            if not persons:
                return []
            result = []
            for p in persons:
                result.append({
                    "id": str(p.ID),
                    "last_name": getattr(p, "LAST_NAME", ""),
                    "first_name": getattr(p, "FIRST_NAME", ""),
                    "middle_name": getattr(p, "MIDDLE_NAME", ""),
                    "tab_num": getattr(p, "TAB_NUM", ""),
                    "org_id": str(getattr(p, "ORG_ID", "")),
                })
            return result
        except Exception as e:
            logger.error(f"PersonSearch error: {e}")
            return []

    def get_person(self, session_id: str, person_id: str) -> Optional[Dict]:
        try:
            client = self._ensure_client()
            if not client:
                return None
            p = client.service.GetPerson(session_id, person_id)
            if not p:
                return None
            return {
                "id": str(p.ID),
                "last_name": getattr(p, "LAST_NAME", ""),
                "first_name": getattr(p, "FIRST_NAME", ""),
                "middle_name": getattr(p, "MIDDLE_NAME", ""),
                "tab_num": getattr(p, "TAB_NUM", ""),
                "org_id": str(getattr(p, "ORG_ID", "")),
            }
        except Exception as e:
            logger.error(f"GetPerson error: {e}")
            return None

    def get_person_extra_field_value(self, session_id: str, person_id: str,
                                     template_id: str) -> Optional[Any]:
        try:
            client = self._ensure_client()
            if not client:
                return None
            result = client.service.GetPersonExtraFieldValue(
                session_id, person_id, template_id
            )
            if result and result.Result == 0:
                return result.Value
            return None
        except Exception as e:
            logger.error(f"GetPersonExtraFieldValue error: {e}")
            return None

    def get_person_extra_field_templates(self, session_id: str) -> List[Dict]:
        try:
            client = self._ensure_client()
            if not client:
                return []
            templates = client.service.GetPersonExtraFieldTemplates(session_id)
            if not templates:
                return []
            return [{"id": str(t.ID), "name": t.NAME, "type": str(t.TYPE)} for t in templates]
        except Exception as e:
            logger.error(f"GetPersonExtraFieldTemplates error: {e}")
            return []

    def get_access_groups(self, session_id: str) -> List[Dict]:
        try:
            client = self._ensure_client()
            if not client:
                return []
            groups = client.service.GetAccessGroups(session_id)
            if not groups:
                return []
            result = []
            for g in groups:
                result.append({
                    "id": str(g.ID),
                    "name": getattr(g, "NAME", "Unknown"),
                    "identif_type": getattr(g, "IDENTIFTYPE", 0),
                })
            return result
        except Exception as e:
            logger.error(f"GetAccessGroups error: {e}")
            return []

    def get_person_identifiers(self, session_id: str, person_id: str) -> List[Dict]:
        try:
            client = self._ensure_client()
            if not client:
                return []
            identifiers = client.service.GetPersonIdentifiers(session_id, person_id)
            if not identifiers:
                return []
            result = []
            for ident in identifiers:
                result.append({
                    "code": getattr(ident, "CODE", ""),
                    "person_id": str(getattr(ident, "PERSON_ID", "")),
                    "is_primary": getattr(ident, "IS_PRIMARY", False),
                    "accgroup_id": str(getattr(ident, "ACCGROUP_ID", "")),
                    "identif_type": getattr(ident, "IDENTIFTYPE", 0),
                    "name": getattr(ident, "NAME", ""),
                })
            return result
        except Exception as e:
            logger.error(f"GetPersonIdentifiers error: {e}")
            return []

    def open_person_editing_session(self, session_id: str, person_id: str) -> Optional[str]:
        try:
            client = self._ensure_client()
            if not client:
                return None
            result = client.service.OpenPersonEditingSession(session_id, person_id)
            if result and result.Result == 0:
                return str(result.Value)
            if result:
                logger.error(f"OpenPersonEditingSession failed: {getattr(result, 'ErrorMessage', 'unknown')}")
            return None
        except Exception as e:
            logger.error(f"OpenPersonEditingSession error: {e}")
            return None

    def close_person_editing_session(self, edit_session_id: str):
        try:
            client = self._ensure_client()
            if client:
                client.service.ClosePersonEditingSession(edit_session_id)
        except Exception as e:
            logger.error(f"ClosePersonEditingSession error: {e}")

    def get_unique_card_code(self, session_id: str) -> Optional[str]:
        try:
            client = self._ensure_client()
            if not client:
                return None
            result = client.service.GetUnique4bCardCode(session_id)
            if result and result.Result == 0:
                return result.Value
            return secrets.token_hex(4).upper()
        except Exception as e:
            logger.warning(f"GetUnique4bCardCode failed, using random: {e}")
            return secrets.token_hex(4).upper()

    def add_person_identifier(self, edit_session_id: str, person_id: str,
                               accgroup_id: str, identif_type: int = 0,
                               code: str = None, is_primary: bool = True,
                               name: str = "") -> bool:
        try:
            IdentifierType = self._get_type("Identifier")
            if IdentifierType is None:
                logger.error("Cannot resolve Identifier type from WSDL")
                return False
            if code is None:
                code = secrets.token_hex(4).upper()
            identifier = IdentifierType(
                CODE=code,
                PERSON_ID=person_id,
                IS_PRIMARY=is_primary,
                ACCGROUP_ID=accgroup_id,
                PRIVILEGE_MASK=0,
                IDENTIFTYPE=identif_type,
                NAME=name,
            )
            client = self._ensure_client()
            if not client:
                return False
            result = client.service.AddPersonIdentifier(edit_session_id, identifier)
            if result and result.Result == 0:
                logger.info(f"Identifier added: type={identif_type}, code={code}")
                return True
            if result:
                logger.error(f"AddPersonIdentifier failed: {getattr(result, 'ErrorMessage', 'unknown')}")
            return False
        except Exception as e:
            logger.error(f"AddPersonIdentifier error: {e}")
            return False

    def add_person_temp_identifier(self, edit_session_id: str, person_id: str,
                                    accgroup_id: str, valid_from: str,
                                    valid_to: str, identif_type: int = 0,
                                    code: str = None, is_primary: bool = True,
                                    name: str = "") -> bool:
        try:
            IdentifierTempType = self._get_type("IdentifierTemp")
            if IdentifierTempType is None:
                logger.warning("IdentifierTemp type not available, falling back to Identifier")
                return self.add_person_identifier(
                    edit_session_id, person_id, accgroup_id,
                    identif_type, code, is_primary, name,
                )
            if code is None:
                code = secrets.token_hex(4).upper()
            identifier = IdentifierTempType(
                CODE=code,
                PERSON_ID=person_id,
                IS_PRIMARY=is_primary,
                ACCGROUP_ID=accgroup_id,
                PRIVILEGE_MASK=0,
                IDENTIFTYPE=identif_type,
                NAME=name,
                VALID_FROM=valid_from,
                VALID_TO=valid_to,
            )
            client = self._ensure_client()
            if not client:
                return False
            result = client.service.AddPersonIdentifier(edit_session_id, identifier)
            if result and result.Result == 0:
                logger.info(f"Temp identifier added: type={identif_type}, code={code}, valid {valid_from}-{valid_to}")
                return True
            if result:
                logger.error(f"AddPersonIdentifier (temp) failed: {getattr(result, 'ErrorMessage', 'unknown')}")
            return False
        except Exception as e:
            logger.error(f"add_person_temp_identifier error: {e}")
            return False

    def delete_identifier(self, session_id: str, code: str) -> bool:
        try:
            client = self._ensure_client()
            if not client:
                return False
            result = client.service.DeleteIdentifier(session_id, code)
            if result and result.Result == 0:
                return True
            return False
        except Exception as e:
            logger.error(f"DeleteIdentifier error: {e}")
            return False

    def create_person(self, session_id: str, last_name: str, first_name: str,
                      middle_name: str = "", org_id: str = None) -> Optional[str]:
        try:
            client = self._ensure_client()
            if not client:
                return None
            person = {
                "ID": "00000000-0000-0000-0000-000000000000",
                "LAST_NAME": last_name,
                "FIRST_NAME": first_name,
                "MIDDLE_NAME": middle_name,
                "ORG_ID": org_id or (self._admin_session or self._bot_session or {}).get("root_org_unit_id", ""),
            }
            result = client.service.CreatePerson(session_id, person)
            if result and result.Result == 0:
                return str(result.Value)
            if result:
                logger.error(f"CreatePerson failed: {getattr(result, 'ErrorMessage', 'unknown')}")
            return None
        except Exception as e:
            logger.error(f"CreatePerson error: {e}")
            return None

    def create_vehicle(self, session_id: str, plate_number: str,
                       model: str = "", color: str = "",
                       org_id: str = None) -> Optional[str]:
        try:
            client = self._ensure_client()
            if not client:
                return None
            vehicle = {
                "ID": "00000000-0000-0000-0000-000000000000",
                "LAST_NAME": plate_number,
                "FIRST_NAME": model,
                "MIDDLE_NAME": color,
                "ORG_ID": org_id or (self._admin_session or self._bot_session or {}).get("root_org_unit_id", ""),
            }
            result = client.service.CreateVehicle(session_id, vehicle)
            if result and result.Result == 0:
                return str(result.Value)
            if result:
                logger.error(f"CreateVehicle failed: {getattr(result, 'ErrorMessage', 'unknown')}")
            return None
        except Exception as e:
            logger.error(f"CreateVehicle error: {e}")
            return None

    def add_vehicle_plate_identifier(self, session_id: str, vehicle_person_id: str,
                                      accgroup_id: str, plate_code: str,
                                      name: str = "",
                                      valid_from: str = None,
                                      valid_to: str = None) -> bool:
        edit_session_id = self.open_person_editing_session(session_id, vehicle_person_id)
        if not edit_session_id:
            return False
        try:
            if valid_from and valid_to:
                success = self.add_person_temp_identifier(
                    edit_session_id=edit_session_id,
                    person_id=vehicle_person_id,
                    accgroup_id=accgroup_id,
                    valid_from=valid_from,
                    valid_to=valid_to,
                    identif_type=1,
                    code=plate_code,
                    is_primary=True,
                    name=name,
                )
            else:
                success = self.add_person_identifier(
                    edit_session_id=edit_session_id,
                    person_id=vehicle_person_id,
                    accgroup_id=accgroup_id,
                    identif_type=1,
                    code=plate_code,
                    is_primary=True,
                    name=name,
                )
            return success
        except Exception as e:
            logger.error(f"add_vehicle_plate_identifier error: {e}")
            return False
        finally:
            self.close_person_editing_session(edit_session_id)

    def add_access_identifier(self, session_id: str, person_id: str,
                               accgroup_id: str, code: str = None,
                               name: str = "",
                               valid_from: str = None,
                               valid_to: str = None) -> bool:
        edit_session_id = self.open_person_editing_session(session_id, person_id)
        if not edit_session_id:
            return False
        try:
            if valid_from and valid_to:
                success = self.add_person_temp_identifier(
                    edit_session_id=edit_session_id,
                    person_id=person_id,
                    accgroup_id=accgroup_id,
                    valid_from=valid_from,
                    valid_to=valid_to,
                    identif_type=0,
                    code=code,
                    is_primary=True,
                    name=name,
                )
            else:
                success = self.add_person_identifier(
                    edit_session_id=edit_session_id,
                    person_id=person_id,
                    accgroup_id=accgroup_id,
                    identif_type=0,
                    code=code,
                    is_primary=True,
                    name=name,
                )
            return success
        except Exception as e:
            logger.error(f"add_access_identifier error: {e}")
            return False
        finally:
            self.close_person_editing_session(edit_session_id)

    def send_hardware_command(self, session_id: str, territory_id: str,
                               command: int = 1) -> bool:
        try:
            client = self._ensure_client()
            if not client:
                return False
            result = client.service.SendHardwareCommand(session_id, territory_id, command)
            if result and result.Result == 0:
                logger.info(f"Hardware command {command} sent to territory {territory_id}")
                return True
            if result:
                logger.error(f"SendHardwareCommand failed: {getattr(result, 'ErrorMessage', 'unknown')}")
            return False
        except Exception as e:
            logger.error(f"SendHardwareCommand error: {e}")
            return False

    def open_gate(self, session_id: str, territory_id: str) -> bool:
        return self.send_hardware_command(session_id, territory_id, command=1)

    def get_territories_hierarchy(self, session_id: str) -> List[Dict]:
        try:
            client = self._ensure_client()
            if not client:
                return []
            territories = client.service.GetTerritoriesHierarhy(session_id)
            if not territories:
                return []
            result = []
            for t in territories:
                entry = {
                    "id": str(t.ID),
                    "name": getattr(t, "NAME", ""),
                    "type": getattr(t, "TYPE", 0),
                    "desc": getattr(t, "DESC", ""),
                    "parent_id": str(getattr(t, "PARENT_ID", "")),
                }
                if hasattr(t, "COMPONENT_ID"):
                    entry["component_id"] = str(t.COMPONENT_ID)
                result.append(entry)
            return result
        except Exception as e:
            logger.error(f"GetTerritoriesHierarhy error: {e}")
            return []

    def get_root_territory(self, session_id: str) -> Optional[Dict]:
        try:
            client = self._ensure_client()
            if not client:
                return None
            t = client.service.GetRootTerritory(session_id)
            if not t:
                return None
            return {
                "id": str(t.ID),
                "name": getattr(t, "NAME", ""),
                "type": getattr(t, "TYPE", 0),
            }
        except Exception as e:
            logger.error(f"GetRootTerritory error: {e}")
            return None

    def get_territory_sub_items(self, session_id: str, territory_id: str) -> List[Dict]:
        try:
            client = self._ensure_client()
            if not client:
                return []
            items = client.service.GetTerritorySubItems(session_id, territory_id)
            if not items:
                return []
            result = []
            for t in items:
                entry = {
                    "id": str(t.ID),
                    "name": getattr(t, "NAME", ""),
                    "type": getattr(t, "TYPE", 0),
                    "desc": getattr(t, "DESC", ""),
                }
                if hasattr(t, "COMPONENT_ID"):
                    entry["component_id"] = str(t.COMPONENT_ID)
                result.append(entry)
            return result
        except Exception as e:
            logger.error(f"GetTerritorySubItems error: {e}")
            return []

    def get_events(self, session_id: str, query_params: Dict = None) -> List[Dict]:
        try:
            client = self._ensure_client()
            if not client:
                return []
            EventHistoryQueryParamsType = self._get_type("EventHistoryQueryParams")
            if EventHistoryQueryParamsType is None:
                logger.error("Cannot resolve EventHistoryQueryParams type")
                return []
            params = EventHistoryQueryParamsType()
            if query_params:
                if "start_date" in query_params:
                    params.StartDate = query_params["start_date"]
                if "end_date" in query_params:
                    params.EndDate = query_params["end_date"]
                if "territories" in query_params:
                    params.Territories = query_params["territories"]
                if "transaction_types" in query_params:
                    params.TransactionTypes = query_params["transaction_types"]
                if "max_result_size" in query_params:
                    params.MaxResultSize = query_params["max_result_size"]
            result_obj = client.service.GetEvents(session_id, params)
            if not result_obj or result_obj.Result == -1:
                return []
            events_history = result_obj.Value
            if not events_history or not events_history.Events:
                return []
            events = []
            for ev in events_history.Events:
                event_data = {
                    "date": str(ev.EventDate) if hasattr(ev, "EventDate") else "",
                    "type": ev.EventType if hasattr(ev, "EventType") else None,
                    "code": getattr(ev, "CODE", ""),
                    "person_index": getattr(ev, "EventPersonIndex", None),
                    "territory_index": getattr(ev, "EventTerritoryIndex", None),
                }
                if event_data["person_index"] is not None and events_history.PersonFullNames:
                    idx = event_data["person_index"]
                    if 0 <= idx < len(events_history.PersonFullNames):
                        event_data["person_name"] = events_history.PersonFullNames[idx]
                if event_data["territory_index"] is not None and events_history.TerritoryNames:
                    idx = event_data["territory_index"]
                    if 0 <= idx < len(events_history.TerritoryNames):
                        event_data["territory_name"] = events_history.TerritoryNames[idx]
                events.append(event_data)
            return events
        except Exception as e:
            logger.error(f"GetEvents error: {e}")
            return []

    def get_version(self) -> Optional[str]:
        try:
            client = self._ensure_client()
            if not client:
                return None
            return client.service.GetVersion()
        except Exception as e:
            logger.error(f"GetVersion error: {e}")
            return None

    # --- Новые методы для ТЗ пропускного режима ---

    def check_role(self, session_id: str, role_name: str) -> bool:
        """Проверка прав оператора. Роли: EmployeeReader, EmployeeWriter,
        HardwareControl, GuestReader, VisitorRequestCreator и др."""
        try:
            client = self._ensure_client()
            if not client:
                return False
            result = client.service.CheckRole(session_id, role_name)
            return result is not None and result.Result == 0
        except Exception as e:
            logger.error(f"CheckRole error: {e}")
            return False

    def block_person(self, session_id: str, person_id: str) -> bool:
        """Блокировка доступа (чёрный список)."""
        try:
            client = self._ensure_client()
            if not client:
                return False
            result = client.service.BlockPerson(session_id, person_id)
            if result and result.Result == 0:
                logger.info(f"Person {person_id} blocked")
                return True
            if result:
                logger.error(f"BlockPerson failed: {getattr(result, 'ErrorMessage', 'unknown')}")
            return False
        except Exception as e:
            logger.error(f"BlockPerson error: {e}")
            return False

    def unblock_person(self, session_id: str, person_id: str) -> bool:
        """Разблокировка доступа."""
        try:
            client = self._ensure_client()
            if not client:
                return False
            result = client.service.UnblockPerson(session_id, person_id)
            if result and result.Result == 0:
                logger.info(f"Person {person_id} unblocked")
                return True
            if result:
                logger.error(f"UnblockPerson failed: {getattr(result, 'ErrorMessage', 'unknown')}")
            return False
        except Exception as e:
            logger.error(f"UnblockPerson error: {e}")
            return False

    def find_person_by_identifier(self, session_id: str, code: str) -> Optional[Dict]:
        """Поиск человека по коду идентификатора (метки или номера)."""
        try:
            client = self._ensure_client()
            if not client:
                return None
            result = client.service.FindPersonByIdentifier(session_id, code)
            if not result or result.Result != 0:
                return None
            person = result.Value
            if not person:
                return None
            return {
                "id": str(person.ID),
                "last_name": getattr(person, "LAST_NAME", ""),
                "first_name": getattr(person, "FIRST_NAME", ""),
                "middle_name": getattr(person, "MIDDLE_NAME", ""),
                "tab_num": getattr(person, "TAB_NUM", ""),
                "org_id": str(getattr(person, "ORG_ID", "")),
            }
        except Exception as e:
            logger.error(f"FindPersonByIdentifier error: {e}")
            return None

    def send_plate_recognition(self, session_id: str, territory_id: str,
                                plate_number: str) -> bool:
        """Отправка распознанного номера в Parsec для идентификации.
        Parsec сам принимает решение о допуске на основе своей БД."""
        try:
            client = self._ensure_client()
            if not client:
                return False
            result = client.service.SendIdentificationCommand(
                session_id, territory_id, plate_number
            )
            if result and result.Result == 0:
                logger.info(f"Plate recognition sent: territory={territory_id}, plate={plate_number}")
                return True
            if result:
                logger.error(f"SendIdentificationCommand failed: {getattr(result, 'ErrorMessage', 'unknown')}")
            return False
        except Exception as e:
            logger.error(f"SendIdentificationCommand error: {e}")
            return False

    def send_verification_command(self, session_id: str, territory_id: str,
                                   person_id: str) -> bool:
        """Отправка команды верификации прохода (для GPU-камер, эмуляция считывания).
        Parsec сам принимает решение о допуске."""
        try:
            client = self._ensure_client()
            if not client:
                return False
            result = client.service.SendVerificationCommand(
                session_id, territory_id, person_id
            )
            if result and result.Result == 0:
                logger.info(f"Verification command sent: territory={territory_id}, person={person_id}")
                return True
            if result:
                logger.error(f"SendVerificationCommand failed: {getattr(result, 'ErrorMessage', 'unknown')}")
            return False
        except Exception as e:
            logger.error(f"SendVerificationCommand error: {e}")
            return False

    def get_hardware_events(self, session_id: str) -> List[Dict]:
        """Получение оперативных событий от контроллеров (для мониторинга штатных камер Parsec)."""
        try:
            client = self._ensure_client()
            if not client:
                return []
            events = client.service.GetHardwareEvents(session_id)
            if not events:
                return []
            result = []
            for ev in events:
                result.append({
                    "date": str(getattr(ev, "EventDate", "")),
                    "type": getattr(ev, "EventType", None),
                    "code": getattr(ev, "CODE", ""),
                    "person_index": getattr(ev, "EventPersonIndex", None),
                    "territory_index": getattr(ev, "EventTerritoryIndex", None),
                })
            return result
        except Exception as e:
            logger.error(f"GetHardwareEvents error: {e}")
            return []

    def open_event_history_session(self, session_id: str,
                                    start_date=None, end_date=None,
                                    territories: List[str] = None,
                                    transaction_types: List[int] = None,
                                    max_results: int = 5000) -> Optional[str]:
        """Открытие сессии истории событий для отчётов."""
        try:
            client = self._ensure_client()
            if not client:
                return None
            EventHistoryQueryParamsType = self._get_type("EventHistoryQueryParams")
            if EventHistoryQueryParamsType is None:
                return None
            params = EventHistoryQueryParamsType()
            if start_date:
                params.StartDate = start_date
            if end_date:
                params.EndDate = end_date
            if territories:
                params.Territories = territories
            if transaction_types:
                params.TransactionTypes = transaction_types
            params.MaxResultSize = max_results
            result = client.service.OpenEventHistorySession(session_id, params)
            if result and result.Result == 0:
                return str(result.Value)
            return None
        except Exception as e:
            logger.error(f"OpenEventHistorySession error: {e}")
            return None

    def get_event_history_result(self, history_session_id: str) -> List[Dict]:
        """Получение результатов из сессии истории событий."""
        try:
            client = self._ensure_client()
            if not client:
                return []
            result = client.service.GetEventHistoryResult(history_session_id)
            if not result or not hasattr(result, 'Value') or not result.Value:
                return []
            events = []
            for ev_obj in result.Value:
                values = getattr(ev_obj, 'Values', [])
                events.append({
                    "values": [str(v) for v in values] if values else [],
                })
            return events
        except Exception as e:
            logger.error(f"GetEventHistoryResult error: {e}")
            return []

    def get_event_history_result_count(self, history_session_id: str) -> int:
        """Количество событий в сессии истории."""
        try:
            client = self._ensure_client()
            if not client:
                return 0
            result = client.service.GetEventHistoryResultCount(history_session_id)
            if result and result.Result == 0:
                return result.Value or 0
            return 0
        except Exception as e:
            logger.error(f"GetEventHistoryResultCount error: {e}")
            return 0

    def close_event_history_session(self, history_session_id: str):
        """Закрытие сессии истории событий."""
        try:
            client = self._ensure_client()
            if client:
                client.service.CloseEventHistorySession(history_session_id)
        except Exception as e:
            logger.error(f"CloseEventHistorySession error: {e}")

    def create_visitor_request(self, session_id: str, org_unit_id: str,
                                person_id: str, purpose: str = "",
                                admit_start=None, admit_end=None) -> Optional[str]:
        """Создание заявки бюро пропусков (для гостевых пропусков)."""
        try:
            client = self._ensure_client()
            if not client:
                return None
            VisitorRequestType = self._get_type("VisitorRequest")
            if VisitorRequestType is None:
                logger.warning("VisitorRequest type not available")
                return None
            request = VisitorRequestType(
                ORGUNIT_ID=org_unit_id,
                PERSON_ID=person_id,
                PURPOSE=purpose,
            )
            if admit_start:
                request.ADMIT_START = admit_start
            if admit_end:
                request.ADMIT_END = admit_end
            result = client.service.CreateVisitorRequest(session_id, request)
            if result and result.Result == 0:
                return str(result.Value)
            if result:
                logger.error(f"CreateVisitorRequest failed: {getattr(result, 'ErrorMessage', 'unknown')}")
            return None
        except Exception as e:
            logger.error(f"CreateVisitorRequest error: {e}")
            return None

    def activate_visitor_request(self, session_id: str, request_id: str) -> bool:
        """Активация заявки бюро пропусков."""
        try:
            client = self._ensure_client()
            if not client:
                return False
            result = client.service.ActivateVisitorRequest(session_id, request_id)
            if result and result.Result == 0:
                return True
            return False
        except Exception as e:
            logger.error(f"ActivateVisitorRequest error: {e}")
            return False

    def check_connection(self) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((self.host, self.port))
            sock.close()
            return result == 0
        except Exception:
            return False
