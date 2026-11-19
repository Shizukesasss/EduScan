"""Private profile preferences for existing EduScan accounts."""

import base64
import binascii
import json
import re
from datetime import datetime
from io import BytesIO
from unicodedata import category

from fastapi import HTTPException
from PIL import Image, ImageOps
from sqlalchemy import case, delete, select
from sqlalchemy.orm import Session

from ..models import SystemSetting, User
from ..request_limits import MAX_PROFILE_PHOTO_BYTES
from .account_email import login_email
from .audit import add_audit
from .settings_store import upsert_value


def _name_key(user_id: int) -> str:
    return f"account.profile.name.{user_id}"


def _photo_key(user_id: int) -> str:
    return f"account.profile.photo.{user_id}"


def profile_summary(db: Session, user: User) -> dict:
    name_key, photo_key = _name_key(user.id), _photo_key(user.id)
    rows = db.execute(select(
        SystemSetting.key, case((SystemSetting.key == name_key, SystemSetting.value)).label("display_name"),
        SystemSetting.updated_at,
    ).where(SystemSetting.key.in_((name_key, photo_key))))
    display_name, photo_revision = user.full_name, None
    for row in rows:
        if row.key == name_key:
            display_name = row.display_name or user.full_name
        else:
            photo_revision = row.updated_at.isoformat(timespec="microseconds") + "Z"
    return {"display_name": display_name, "profile_photo_revision": photo_revision}


def profile_picture(db: Session, user: User) -> bytes:
    picture = db.scalar(select(SystemSetting.value).where(SystemSetting.key == _photo_key(user.id)))
    if picture:
        try:
            return base64.b64decode(picture, validate=True)
        except (ValueError, binascii.Error):
            pass
    raise HTTPException(404, "Profile picture is unavailable.")


def profile_contact(db: Session, user: User) -> dict:
    stored = db.scalar(select(SystemSetting.value).where(SystemSetting.key == f"account.profile.contact.{user.id}"))
    contact = json.loads(stored) if stored else {}
    return {
        "phone_number": contact.get("phone_number", ""),
        "emergency_name": contact.get("emergency_name", ""),
        "emergency_phone": contact.get("emergency_phone", ""),
    }


def profile_details(db: Session, user: User) -> dict:
    return {"id": user.id, "email": login_email(db, user), **profile_summary(db, user), **profile_contact(db, user)}


def _phone_number(value: str, label: str) -> str:
    value = value.strip()
    compact = re.sub(r"[\s().-]", "", value)
    if value and not re.fullmatch(r"\+?[0-9]{7,15}", compact):
        raise HTTPException(422, f"Enter a valid {label}.")
    return value


def validated_contact(phone_number: str, emergency_name: str, emergency_phone: str) -> dict:
    emergency_name = emergency_name.strip()
    if any(category(character) == "Cc" for character in emergency_name):
        raise HTTPException(422, "Enter a valid emergency contact name.")
    return {
        "phone_number": _phone_number(phone_number, "phone number"),
        "emergency_name": emergency_name, "emergency_phone": _phone_number(emergency_phone, "emergency contact number"),
    }


def normalize_picture(content: bytes) -> bytes:
    if len(content) > MAX_PROFILE_PHOTO_BYTES:
        raise HTTPException(413, "Choose a picture up to 5 MB.")
    try:
        with Image.open(BytesIO(content), formats=("JPEG", "PNG", "WEBP")) as image:
            if image.width * image.height > 20_000_000 or getattr(image, "n_frames", 1) != 1:
                raise HTTPException(422, "Choose a still image with at most 20 megapixels.")
            crop = ImageOps.fit(ImageOps.exif_transpose(image).convert("RGBA"), (384, 384), Image.Resampling.LANCZOS)
            avatar = Image.new("RGB", crop.size, "white")
            avatar.paste(crop, mask=crop.getchannel("A"))
    except (Image.DecompressionBombError, OSError, ValueError, SyntaxError) as exc:
        raise HTTPException(422, "Choose a valid JPEG, PNG, or WebP picture.") from exc
    output = BytesIO()
    avatar.save(output, format="JPEG", quality=88, optimize=True)
    return output.getvalue()


def save_profile(db: Session, user: User, name: str | None, photo: bytes | None, remove_picture: bool,
                 *, contact: dict | None = None) -> dict:
    if name is not None:
        name = name.strip()
        if not name or any(category(character) == "Cc" for character in name):
            raise HTTPException(422, "Enter a valid display name.")
    before = profile_summary(db, user)
    now = datetime.utcnow()
    if name is not None and name != before["display_name"]:
        upsert_value(db, _name_key(user.id), "" if name == user.full_name else name, now)
    if photo is not None:
        upsert_value(db, _photo_key(user.id), base64.b64encode(photo).decode("ascii"), now)
    elif remove_picture:
        db.execute(delete(SystemSetting).where(SystemSetting.key == _photo_key(user.id)))
    contact_changed = contact is not None and contact != profile_contact(db, user)
    if contact_changed:
        upsert_value(db, f"account.profile.contact.{user.id}", json.dumps(contact), now)
    after = profile_summary(db, user)
    if before != after or contact_changed:
        add_audit(db, user, "Update", "UserProfile", user.id, "User updated their profile",
                  before={"display_name": before["display_name"], "has_picture": bool(before["profile_photo_revision"])},
                  after={"display_name": after["display_name"], "has_picture": bool(after["profile_photo_revision"]),
                         "contact_details_updated": contact_changed})
    db.commit()
    return {"id": user.id, **after, **(contact if contact is not None else {})}
