import socket
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class ParsecAPI:
    def __init__(self, domain: str, port: int = 10101,
                 bot_username: str = "", bot_password: str = "",
                 admin_username: str = "", admin_password: str = ""):
        self.domain = domain
        self.port = port
        self.bot_username = bot_username
        self.bot_password = bot_password
        self.admin_username = admin_username
        self.admin_password = admin_password
        self.wsdl_url = f"http://{domain}:{port}/IntegrationService/IntegrationService.asmx?WSDL"
        self.soap_client = None
        self.bot_session_id = None
        self.admin_session_id = None
        logger.info(f"ParsecAPI initialized with WSDL: {self.wsdl_url}")

    def _ensure_client(self):
        if self.soap_client is None:
            self._create_client()
        return self.soap_client

    def _create_client(self):
        try:
            import zeep
            from zeep.transports import Transport
            import requests

            session = requests.Session()
            session.trust_env = False
            transport = Transport(session=session, timeout=10)
            self.soap_client = zeep.Client(wsdl=self.wsdl_url, transport=transport)
            logger.info("SOAP client created successfully")
        except Exception as e:
            logger.error(f"Failed to create SOAP client: {e}")
            self.soap_client = None

    def open_session(self, domain: str, username: str, password: str) -> Optional[str]:
        try:
            client = self._ensure_client()
            if not client:
                return None
            result = client.service.OpenSession(domain, username, password)
            if result and hasattr(result, "Value"):
                session_id = str(result.Value)
                logger.info(f"Session opened for {username}")
                return session_id
            if result and hasattr(result, "SessionID"):
                return str(result.SessionID)
            if result:
                return str(result)
            return None
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

    def open_bot_session(self) -> Optional[str]:
        self.bot_session_id = self.open_session(
            "SYSTEM", self.bot_username, self.bot_password
        )
        return self.bot_session_id

    def open_admin_session(self) -> Optional[str]:
        self.admin_session_id = self.open_session(
            "SYSTEM", self.admin_username, self.admin_password
        )
        return self.admin_session_id

    def find_person_by_phone(self, session_id: str, phone: str) -> Optional[Dict]:
        try:
            client = self._ensure_client()
            if not client:
                return None
            phone_clean = phone.replace("+", "").replace(" ", "").replace("-", "")
            persons = client.service.FindPersons(session_id, phone_clean)
            if persons:
                for p in persons:
                    return {
                        "id": str(p.ID) if hasattr(p, "ID") else str(p),
                        "first_name": getattr(p, "FIRST_NAME", ""),
                        "last_name": getattr(p, "LAST_NAME", ""),
                        "middle_name": getattr(p, "MIDDLE_NAME", ""),
                        "phone": phone,
                        "tab_number": getattr(p, "TAB_NUMBER", ""),
                    }
            return None
        except Exception as e:
            logger.error(f"Failed to find person by phone {phone}: {e}")
            return None

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
                    "id": str(g.ID) if hasattr(g, "ID") else str(g),
                    "name": getattr(g, "NAME", "Unknown"),
                })
            return result
        except Exception as e:
            logger.error(f"Failed to get access groups: {e}")
            return []

    def get_territories(self, session_id: str) -> List[Dict]:
        try:
            client = self._ensure_client()
            if not client:
                return []
            territories = client.service.GetTerritories(session_id)
            if not territories:
                return []
            return [{"id": str(t.ID), "name": getattr(t, "NAME", "")} for t in territories]
        except Exception as e:
            logger.error(f"Failed to get territories: {e}")
            return []

    def get_person_access_groups(self, session_id: str, person_id: str) -> List[Dict]:
        try:
            client = self._ensure_client()
            if not client:
                return []
            groups = client.service.GetPersonAccessGroups(session_id, person_id)
            if not groups:
                return []
            return [{"id": str(g.ID), "name": getattr(g, "NAME", "")} for g in groups]
        except Exception as e:
            logger.error(f"Failed to get person access groups: {e}")
            return []

    def create_pass(self, session_id: str, person_id: str, access_group_id: str,
                    valid_from: str, valid_to: str, description: str = "") -> Optional[str]:
        try:
            client = self._ensure_client()
            if not client:
                return None
            result = client.service.CreatePass(
                session_id, person_id, access_group_id, valid_from, valid_to, description
            )
            if result and hasattr(result, "Value"):
                return str(result.Value)
            return str(result) if result else None
        except Exception as e:
            logger.error(f"Failed to create pass: {e}")
            return None

    def delete_pass(self, session_id: str, pass_id: str) -> bool:
        try:
            client = self._ensure_client()
            if not client:
                return False
            result = client.service.DeletePass(session_id, pass_id)
            return bool(result)
        except Exception as e:
            logger.error(f"Failed to delete pass: {e}")
            return False

    def open_door(self, session_id: str, device_id: str) -> bool:
        try:
            client = self._ensure_client()
            if not client:
                return False
            result = client.service.OpenDoor(session_id, device_id)
            logger.info(f"Open door {device_id}: {result}")
            return bool(result)
        except Exception as e:
            logger.error(f"Failed to open door {device_id}: {e}")
            return False

    def get_events(self, session_id: str, from_date: str = None,
                   to_date: str = None) -> List[Dict]:
        try:
            client = self._ensure_client()
            if not client:
                return []
            if not from_date:
                from_date = datetime.now().strftime("%Y-%m-%d 00:00:00")
            if not to_date:
                to_date = datetime.now().strftime("%Y-%m-%d 23:59:59")
            events = client.service.GetEvents(session_id, from_date, to_date)
            if not events:
                return []
            return [{"id": str(e.ID), "time": str(e.TIME), "type": str(e.TYPE)} for e in events]
        except Exception as e:
            logger.error(f"Failed to get events: {e}")
            return []

    def check_connection(self) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((self.domain, self.port))
            sock.close()
            return result == 0
        except Exception:
            return False
