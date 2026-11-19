from ipaddress import ip_address, ip_network

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .settings_store import get_json


class GateNetworkSettings(BaseModel):
    restricted: bool = False
    allowed_networks: list[str] = Field(default_factory=list, max_length=64)
    privacy_contact: str = Field(default="", max_length=200)


def gate_network_settings(db: Session) -> GateNetworkSettings:
    return GateNetworkSettings.model_validate(get_json(db, "gate.network", {}))


def normalized_network_settings(payload: GateNetworkSettings) -> GateNetworkSettings:
    try:
        ranges = list(dict.fromkeys(str(ip_network(value.strip(), strict=False)) for value in payload.allowed_networks))
    except ValueError as error:
        raise HTTPException(422, "Enter a valid IP address or CIDR range on each line.") from error
    if payload.restricted and not ranges:
        raise HTTPException(422, "Add at least one school address or network to enable restrictions.")
    return payload.model_copy(update={"allowed_networks": ranges, "privacy_contact": payload.privacy_contact.strip()})


def enforce_gate_network(policy: GateNetworkSettings, request: Request) -> None:
    if not policy.restricted:
        return
    try:
        address = ip_address(request.client.host) if request.client else None
        address = getattr(address, "ipv4_mapped", None) or address
    except ValueError:
        address = None
    if address and not address.is_loopback and any(address in ip_network(network) for network in policy.allowed_networks):
        return
    raise HTTPException(403, detail={"code": "gate_network_denied",
                                     "message": "Connect this gate station to an approved school network."})
