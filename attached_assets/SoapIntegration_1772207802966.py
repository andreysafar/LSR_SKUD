#!/usr/bin/env python3
import zeep
import secrets

#%% Connect to IntegrationService
credentials = ("SYSTEM","parsec","parsec")
client = zeep.Client("http://127.0.0.1:10101/IntegrationService/IntegrationService.asmx?WSDL")
print(client.service.GetVersion())
session = client.service.OpenSession(*credentials)
sessionId = session.Value.SessionID

#%% CreatePerson
person = {
    "ID": "00000000-0000-0000-0000-000000000000",
    "LAST_NAME": "Иванов",
    "FIRST_NAME": "Иван",
    "MIDDLE_NAME": "Иванович",
    "ORG_ID": session.Value.RootOrgUnitID
    }
personId = client.service.CreatePerson(sessionId,person).Value

#%% AddPersonIdentifier
AccGroups = client.service.GetAccessGroups(sessionId)
namespace = ""
for key, value in client.namespaces.items():
    if value == "http://parsec.ru/Parsec3IntergationService":
        namespace = key
personEditSessionId = client.service.OpenPersonEditingSession(sessionId, personId)
IdentifierType = client.get_type(f"{namespace}:Identifier")
Identifier = IdentifierType(CODE=secrets.token_hex(4), IS_PRIMARY=True, PERSON_ID=personId,
                            ACCGROUP_ID=AccGroups[0].ID, PRIVILEGE_MASK=0, IDENTIFTYPE=0,NAME="")
result = client.service.AddPersonIdentifier(personEditSessionId.Value,Identifier)
client.service.ClosePersonEditingSession(personEditSessionId.Value)