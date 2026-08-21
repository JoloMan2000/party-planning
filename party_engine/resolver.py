"""
Freitext-Alias-Resolver
========================

Löst rohen Gästefreitext (z.B. "Voddi", "Jacky Cola", "Burger + Cheddar") in
ein ``ResolutionResult`` auf. Folgt strikt der in AUFGABE §26-28 vorgegebenen
Reihenfolge:

    1. Exact canonical match
    2. Exact alias match
    3. Normalisierte Schreibweise
    4. Brand-Erkennung
    5. Rezept + Modifier-Erkennung
    6. Fuzzy Matching (stdlib ``difflib``, keine neue Abhängigkeit)
    7. Unknown / Review

Confidence-Schwellen (siehe ``PartyConfig``):
    >= 0.90            automatisch übernehmen
    0.75 - 0.89        übernehmen + Hinweis (ReviewIssue)
    < 0.75             nicht automatisch übernehmen (bestbekannte Vermutung
                        wird trotzdem zurückgegeben, der Aufrufer entscheidet)

Wichtig: Diese Funktionen werfen NIE eine Exception für unbekannten Freitext.
Unbekannte Eingaben werden immer als ``target_type="unknown"`` zurückgegeben,
niemals stillschweigend verworfen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from party_engine.domain import Alias, CatalogItem, PartyCatalog, ResolutionResult

# ---------------------------------------------------------------------------
# Normalisierung
# ---------------------------------------------------------------------------

_PUNCT_RE = re.compile(r"[.,;:!?()\[\]{}\"“”„»«/]")
_WHITESPACE_RE = re.compile(r"\s+")
_UMLAUT_MAP = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}


def normalize_text(raw: str) -> str:
    """Schritt 1: trim/lowercase, Satzzeichen entfernen, Whitespace kollabieren."""
    text = (raw or "").strip().lower()
    text = _PUNCT_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


def fold_umlauts(text: str) -> str:
    """Diakritika-tolerante ASCII-Variante (z.B. für Tippen ohne dt. Tastatur)."""
    for umlaut, replacement in _UMLAUT_MAP.items():
        text = text.replace(umlaut, replacement)
    return text


def compact(text: str) -> str:
    """Entfernt sämtliche Leerzeichen/Bindestriche - für "Normalisierte Schreibweise"."""
    return re.sub(r"[\s\-']", "", text)


# ---------------------------------------------------------------------------
# Resolver-Index (einmalig pro Katalog vorberechnet, siehe AUFGABE §44)
# ---------------------------------------------------------------------------


@dataclass
class ResolverIndex:
    # normalisierter Name -> (target_type, target_id)
    canonical_index: dict[str, tuple[str, str]] = field(default_factory=dict)
    # normalisierter, leerzeichenfreier Name -> (target_type, target_id)
    compact_canonical_index: dict[str, tuple[str, str]] = field(default_factory=dict)
    # normalisierter alias_text -> [Alias, ...] (mehrere möglich)
    alias_index: dict[str, list[Alias]] = field(default_factory=dict)
    compact_alias_index: dict[str, list[Alias]] = field(default_factory=dict)
    # alle (normalisierter Text, target_type, target_id) für Fuzzy-Scan
    all_names: list[tuple[str, str, str]] = field(default_factory=list)
    # ingredient_id -> normalisierter Name (für Modifier-Matching)
    ingredient_name_by_id: dict[str, str] = field(default_factory=dict)
    # brand-Aliase separat für Schritt 4 (Substring-Scan)
    brand_aliases: list[Alias] = field(default_factory=list)


def _index_item(idx: ResolverIndex, item: CatalogItem, target_type: str) -> None:
    norm_id = normalize_text(item.id)
    norm_name = normalize_text(item.name)
    for key in {norm_id, norm_name}:
        if key and key not in idx.canonical_index:
            idx.canonical_index[key] = (target_type, item.id)
        if key:
            idx.all_names.append((key, target_type, item.id))
    ck = compact(norm_name)
    if ck and ck not in idx.compact_canonical_index:
        idx.compact_canonical_index[ck] = (target_type, item.id)


def build_resolver_index(catalog: PartyCatalog) -> ResolverIndex:
    idx = ResolverIndex()

    for item in catalog.direct_consumables.values():
        _index_item(idx, item, "direct_consumable")
    for item in catalog.recipes.values():
        _index_item(idx, item, "recipe")
    for item in catalog.ingredients.values():
        _index_item(idx, item, "ingredient")
        idx.ingredient_name_by_id[item.id] = normalize_text(item.name)

    for alias in catalog.aliases:
        key = normalize_text(alias.alias_text)
        folded = fold_umlauts(key)
        idx.alias_index.setdefault(key, []).append(alias)
        if folded != key:
            idx.alias_index.setdefault(folded, []).append(alias)
        ck = compact(key)
        idx.compact_alias_index.setdefault(ck, []).append(alias)
        if alias.brand:
            idx.brand_aliases.append(alias)

    # längste Alias-Texte zuerst -> bei Substring-Scan wird der spezifischste
    # (längste) Treffer bevorzugt.
    idx.brand_aliases.sort(key=lambda a: len(a.alias_text), reverse=True)

    return idx


_index_cache: dict[int, ResolverIndex] = {}


def get_resolver_index(catalog: PartyCatalog) -> ResolverIndex:
    """Gecachter Zugriff auf den Resolver-Index für eine gegebene ``PartyCatalog``-
    Instanz (identifiziert über ``id()`` - ``load_catalog`` liefert dank eigenem
    Cache ohnehin stabile Instanzen zurück, siehe ``party_engine/catalog.py``)."""
    key = id(catalog)
    if key not in _index_cache:
        _index_cache[key] = build_resolver_index(catalog)
    return _index_cache[key]


# ---------------------------------------------------------------------------
# Fuzzy-Scoring (stdlib difflib, kein neues Dependency)
# ---------------------------------------------------------------------------


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ratio = SequenceMatcher(None, a, b).ratio()
    if a in b or b in a:
        shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
        containment = len(shorter) / len(longer)
        ratio = max(ratio, 0.5 + 0.45 * containment)
    return ratio


# ---------------------------------------------------------------------------
# Schritte 1-3: canonical / alias / normalisiert (ohne Fuzzy)
# ---------------------------------------------------------------------------

_ALLOWED_BASE_TYPES = ("recipe", "direct_consumable")


def _lookup_exact(
    norm: str,
    idx: ResolverIndex,
    allowed_types: tuple[str, ...] | None = None,
) -> tuple[str, str, float, str, str] | None:
    """Versucht Schritte 1-3. Rückgabe: (target_type, target_id, confidence, method, brand)."""
    folded = fold_umlauts(norm)
    ck = compact(norm)

    for candidate in {norm, folded}:
        hit = idx.canonical_index.get(candidate)
        if hit and (allowed_types is None or hit[0] in allowed_types):
            return (hit[0], hit[1], 1.0, "exact_canonical", "")

    for candidate in {norm, folded}:
        aliases = idx.alias_index.get(candidate)
        if aliases:
            usable = [a for a in aliases if allowed_types is None or a.target_type in allowed_types]
            if usable:
                best = max(usable, key=lambda a: a.confidence)
                return (best.target_type, best.target_id, best.confidence, "exact_alias", best.brand)

    hit = idx.compact_canonical_index.get(ck)
    if hit and (allowed_types is None or hit[0] in allowed_types):
        return (hit[0], hit[1], 0.93, "normalized", "")

    aliases = idx.compact_alias_index.get(ck)
    if aliases:
        usable = [a for a in aliases if allowed_types is None or a.target_type in allowed_types]
        if usable:
            best = max(usable, key=lambda a: a.confidence)
            return (
                best.target_type,
                best.target_id,
                min(0.93, best.confidence),
                "normalized",
                best.brand,
            )

    return None


# ---------------------------------------------------------------------------
# Schritt 4: Brand-Erkennung als Substring innerhalb längeren Freitexts
# ---------------------------------------------------------------------------


def _detect_brand(norm: str, idx: ResolverIndex) -> ResolutionResult | None:
    padded = f" {norm} "
    for alias in idx.brand_aliases:
        alias_norm = normalize_text(alias.alias_text)
        if f" {alias_norm} " in padded:
            return ResolutionResult(
                raw_text=norm,
                target_type=alias.target_type,
                target_id=alias.target_id,
                confidence=round(min(0.9, alias.confidence), 3),
                method="brand",
                brand=alias.brand,
            )
    return None


# ---------------------------------------------------------------------------
# Schritt 5: Rezept + Modifier-Erkennung
# ---------------------------------------------------------------------------

_CONNECTOR_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("ohne", re.compile(r"^(?P<base>.+?)\s+ohne\s+(?P<mod>.+)$")),
    ("mit", re.compile(r"^(?P<base>.+?)\s+mit\s+(?P<mod>.+)$")),
    ("plus", re.compile(r"^(?P<base>.+?)\s*\+\s*(?P<mod>.+)$")),
    ("extra", re.compile(r"^(?P<base>.+?)\s+extra\s+(?P<mod>.+)$")),
]
_DOUBLE_PREFIX_RE = re.compile(r"^doppel(?:t|te)?\s*(?P<base>.+)$")

_EFFECTS_FOR_CONNECTOR: dict[str, tuple[str, ...]] = {
    "ohne": ("remove_component",),
    "mit": ("add_component", "set_brand_preference"),
    "plus": ("add_component",),
    "extra": ("add_component",),
}


def _resolve_base_phrase(
    phrase: str, catalog: PartyCatalog, idx: ResolverIndex
) -> tuple[str, str, float] | None:
    """Löst den "Grundbegriff" (z.B. "burger", "gin tonic", "steak") auf ein
    Recipe oder DirectConsumable auf. Kombiniert exakte/alias/normalisierte
    Treffer mit einer Kategorie-Heuristik und einem Fuzzy-Fallback."""
    phrase = phrase.strip()
    if not phrase:
        return None

    exact = _lookup_exact(phrase, idx, allowed_types=_ALLOWED_BASE_TYPES)
    if exact:
        target_type, target_id, confidence, _method, _brand = exact
        return (target_type, target_id, confidence)

    # Kategorie-Exakt-Treffer: z.B. "burger" == Recipe.category "burger".
    # Bevorzugt einen "popular"-markierten, sonst den kürzest benannten
    # Vertreter dieser Kategorie (nahe am Gattungsbegriff).
    category_matches: list[CatalogItem] = []
    for item in list(catalog.recipes.values()) + list(catalog.direct_consumables.values()):
        if normalize_text(item.category) == phrase:
            category_matches.append(item)
    if category_matches:
        category_matches.sort(key=lambda it: (not it.popular, len(it.name)))
        chosen = category_matches[0]
        target_type = "recipe" if chosen.id in catalog.recipes else "direct_consumable"
        return (target_type, chosen.id, 0.8)

    # Fuzzy-Fallback über alle Rezept-/DirectConsumable-Namen.
    best: tuple[str, str, float] | None = None
    for norm_name, target_type, target_id in idx.all_names:
        if target_type not in _ALLOWED_BASE_TYPES:
            continue
        score = _similarity(phrase, norm_name)
        if best is None or score > best[2]:
            best = (target_type, target_id, score)
    if best and best[2] >= 0.35:
        return best
    return None


def _strip_connector_from_name(name: str) -> str:
    norm = normalize_text(name)
    for prefix in ("ohne ", "mit ", "extra "):
        if norm.startswith(prefix):
            return norm[len(prefix) :]
    return norm


def _pick_modifier(
    catalog: PartyCatalog,
    idx: ResolverIndex,
    kind: str,
    mod_phrase_norm: str,
    category: str,
) -> tuple[str, str, float] | None:
    """Sucht den am besten passenden ``Modifier`` für eine Konnektor-Phrase.
    Rückgabe: (modifier_id, brand, score)."""
    allowed_effects = _EFFECTS_FOR_CONNECTOR.get(kind, ("add_component",))
    best: tuple[str, str, float] | None = None
    for modifier in catalog.modifiers.values():
        if modifier.effect_type not in allowed_effects:
            continue
        if "*" not in modifier.applies_to and category not in modifier.applies_to:
            continue
        candidate_texts = []
        if modifier.target_ingredient_id:
            candidate_texts.append(idx.ingredient_name_by_id.get(modifier.target_ingredient_id, ""))
        if modifier.brand:
            candidate_texts.append(normalize_text(modifier.brand))
        candidate_texts.append(_strip_connector_from_name(modifier.name))

        score = max((_similarity(mod_phrase_norm, fold_umlauts(t)) for t in candidate_texts if t), default=0.0)
        score = max(
            score,
            max((_similarity(fold_umlauts(mod_phrase_norm), fold_umlauts(t)) for t in candidate_texts if t), default=0.0),
        )
        if best is None or score > best[2]:
            brand = modifier.brand if modifier.effect_type == "set_brand_preference" else ""
            best = (modifier.id, brand, score)
    if best and best[2] >= 0.55:
        return best
    return None


def _pick_double_modifier(
    catalog: PartyCatalog, category: str
) -> tuple[str, float] | None:
    candidates = [
        m
        for m in catalog.modifiers.values()
        if normalize_text(m.name).startswith("doppel")
        and ("*" in m.applies_to or category in m.applies_to)
    ]
    if not candidates:
        return None
    # spezifischere (nicht "*") Treffer bevorzugen
    candidates.sort(key=lambda m: (m.applies_to == ["*"],))
    chosen = candidates[0]
    return (chosen.id, 0.85)


def _try_recipe_modifier(norm: str, catalog: PartyCatalog, idx: ResolverIndex) -> ResolutionResult | None:
    # "Doppelburger" etc. - Präfix ggf. ohne Leerzeichen angehängt.
    m = _DOUBLE_PREFIX_RE.match(norm)
    if m:
        base_phrase = m.group("base").strip()
        base_match = _resolve_base_phrase(base_phrase, catalog, idx) if base_phrase else None
        if base_match:
            target_type, target_id, base_conf = base_match
            item = catalog.get_item(target_id)
            category = getattr(item, "category", "") if item else ""
            dbl = _pick_double_modifier(catalog, category)
            if dbl:
                mod_id, mod_conf = dbl
                confidence = round(min(0.95, base_conf * mod_conf + 0.05), 3)
                return ResolutionResult(
                    raw_text=norm,
                    target_type=target_type,
                    target_id=target_id,
                    confidence=confidence,
                    method="recipe_modifier",
                    applied_modifiers=[mod_id],
                )

    for kind, pattern in _CONNECTOR_PATTERNS:
        mm = pattern.match(norm)
        if not mm:
            continue
        base_phrase = mm.group("base").strip()
        mod_phrase = mm.group("mod").strip()
        if not base_phrase or not mod_phrase:
            continue
        base_match = _resolve_base_phrase(base_phrase, catalog, idx)
        if not base_match:
            continue
        target_type, target_id, base_conf = base_match
        item = catalog.get_item(target_id)
        category = getattr(item, "category", "") if item else ""

        picked = _pick_modifier(catalog, idx, kind, mod_phrase, category)
        if not picked:
            continue
        mod_id, brand, mod_score = picked
        confidence = round(min(0.97, base_conf * (0.7 + 0.3 * mod_score)), 3)
        return ResolutionResult(
            raw_text=norm,
            target_type=target_type,
            target_id=target_id,
            confidence=confidence,
            method="recipe_modifier",
            brand=brand,
            applied_modifiers=[mod_id],
        )
    return None


# ---------------------------------------------------------------------------
# Schritt 6: Fuzzy Matching (letzter Versuch vor "unknown")
# ---------------------------------------------------------------------------


def _fuzzy_match(norm: str, idx: ResolverIndex) -> ResolutionResult | None:
    best_score = 0.0
    best: tuple[str, str, str] | None = None  # (type, id, brand)

    for norm_name, target_type, target_id in idx.all_names:
        score = _similarity(norm, norm_name)
        if score > best_score:
            best_score = score
            best = (target_type, target_id, "")

    for alias_text, aliases in idx.alias_index.items():
        score = _similarity(norm, alias_text)
        if score > best_score:
            for a in aliases:
                if score > best_score:
                    best_score = score
                    best = (a.target_type, a.target_id, a.brand)

    if best is None or best_score < 0.5:
        return None

    target_type, target_id, brand = best
    return ResolutionResult(
        raw_text=norm,
        target_type=target_type,
        target_id=target_id,
        confidence=round(best_score, 3),
        method="fuzzy",
        brand=brand,
    )


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------


def resolve(raw_text: str, catalog: PartyCatalog, index: ResolverIndex | None = None) -> ResolutionResult:
    """Löst ein einzelnes Freitext-Item auf. Wirft NIE eine Exception."""
    try:
        idx = index or get_resolver_index(catalog)
        norm = normalize_text(raw_text)
        if not norm:
            return ResolutionResult(raw_text=raw_text, target_type="unknown", confidence=0.0, method="unknown")

        # Schritte 1-3
        exact = _lookup_exact(norm, idx)
        if exact:
            target_type, target_id, confidence, method, brand = exact
            return ResolutionResult(
                raw_text=raw_text,
                target_type=target_type,
                target_id=target_id,
                confidence=round(confidence, 3),
                method=method,
                brand=brand,
            )

        # Designentscheidung: Schritt 5 (Rezept + Modifier) wird VOR Schritt 4
        # (freier Brand-Substring-Scan) versucht, obwohl die Spezifikation sie
        # in der Reihenfolge 4 vor 5 auflistet. Begründung: Phrasen wie
        # "Gin Tonic mit Hendrick's" enthalten sowohl eine erkennbare
        # Markenerwähnung ("Hendrick's") als auch ein vollständiges Rezept
        # ("Gin Tonic"); ein bedingungsloser Brand-Substring-Treffer würde hier
        # fälschlich nur noch die pure Spirituose statt "Gin Tonic + Marken-
        # präferenz" liefern. Die Rezept+Modifier-Erkennung deckt die Brand-
        # Erkennung für diese Fälle vollständig ab (siehe set_brand_preference-
        # Modifier-Zweig). Schritt 4 bleibt als eigenständiger Fallback für
        # freistehende Markennennungen (z.B. "gerne einen Jägermeister") erhalten.
        recipe_mod_hit = _try_recipe_modifier(norm, catalog, idx)
        if recipe_mod_hit:
            recipe_mod_hit.raw_text = raw_text
            return recipe_mod_hit

        # Schritt 4: Brand-Substring-Erkennung (z.B. "gerne einen Jägermeister")
        brand_hit = _detect_brand(norm, idx)
        if brand_hit:
            brand_hit.raw_text = raw_text
            return brand_hit

        # Schritt 6: Fuzzy Matching
        fuzzy_hit = _fuzzy_match(norm, idx)
        if fuzzy_hit:
            fuzzy_hit.raw_text = raw_text
            return fuzzy_hit

        # Schritt 7: Unknown / Review - niemals verwerfen.
        return ResolutionResult(raw_text=raw_text, target_type="unknown", confidence=0.0, method="unknown")
    except Exception:
        # Sicherheitsnetz: der Resolver darf die Anwendung niemals zum
        # Absturz bringen, egal wie kaputt/unerwartet der Freitext ist.
        return ResolutionResult(raw_text=raw_text, target_type="unknown", confidence=0.0, method="unknown")


def split_freetext(freetext: str) -> list[str]:
    """Zerlegt ein kommagetrenntes Freitextfeld in einzelne Items."""
    if not freetext:
        return []
    return [part.strip() for part in freetext.split(",") if part.strip()]


def resolve_freetext_field(
    freetext: str, catalog: PartyCatalog, index: ResolverIndex | None = None
) -> list[ResolutionResult]:
    idx = index or get_resolver_index(catalog)
    return [resolve(item, catalog, idx) for item in split_freetext(freetext)]
