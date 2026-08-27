from __future__ import annotations

import re
import unicodedata


def professional_key(value) -> str:
    """Cria uma identidade estável, ignorando acentos e diferenças de espaçamento."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^A-Za-z0-9]+", " ", text).strip().upper()
    return re.sub(r"\s+", " ", text)


def art_number_key(value) -> str:
    """Normaliza o número apenas para prevenir cadastros duplicados."""
    return re.sub(r"[^A-Za-z0-9]+", "", str(value or "")).upper()


def professional_profiles(rows) -> list[dict]:
    """Consolida os profissionais já usados, preservando a ordem do primeiro cadastro.

    Os dados não vazios do registro mais recente prevalecem, permitindo corrigir título,
    nome ou registro profissional sem perder a posição histórica do profissional.
    """
    profiles: dict[str, dict] = {}
    for position, raw in enumerate(rows):
        item = dict(raw)
        key = professional_key(item.get("professional_name"))
        if not key:
            continue
        art_id = int(item.get("id") or position + 1)
        if key not in profiles:
            profiles[key] = {
                "key": key,
                "professional_name": str(item.get("professional_name") or "").strip(),
                "professional_title": str(item.get("professional_title") or "").strip(),
                "professional_registration": str(
                    item.get("professional_registration") or ""
                ).strip(),
                "first_art_id": art_id,
                "last_art_id": art_id,
            }
            continue
        profile = profiles[key]
        profile["first_art_id"] = min(profile["first_art_id"], art_id)
        if art_id >= profile["last_art_id"]:
            profile["last_art_id"] = art_id
            for field in (
                "professional_name",
                "professional_title",
                "professional_registration",
            ):
                value = str(item.get(field) or "").strip()
                if value:
                    profile[field] = value
    return sorted(profiles.values(), key=lambda item: (item["first_art_id"], item["key"]))


def organize_art_rows(rows) -> list[dict]:
    """Agrupa ARTs pelo profissional e mantém a ordem de cadastro dentro do grupo."""
    source = [dict(row) for row in rows]
    profiles = professional_profiles(source)
    profile_by_key = {item["key"]: item for item in profiles}
    group_order = {item["key"]: index for index, item in enumerate(profiles)}
    organized = []
    for position, item in enumerate(source):
        key = professional_key(item.get("professional_name"))
        profile = profile_by_key.get(key, {})
        item["professional_key"] = key
        item["professional_display_name"] = (
            profile.get("professional_name") or item.get("professional_name") or ""
        )
        item["professional_group_order"] = group_order.get(key, len(group_order))
        item["art_registration_order"] = int(item.get("id") or position + 1)
        organized.append(item)
    return sorted(
        organized,
        key=lambda item: (
            item["professional_group_order"],
            item["art_registration_order"],
        ),
    )
